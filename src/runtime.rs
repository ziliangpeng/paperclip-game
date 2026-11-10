//! One authoritative writer for logical updates and closed player intents.

use crate::game::amount::{BoundedIntegerError, MAX_SAFE_JSON_INTEGER};
use crate::game::clock::{ClockError, UPDATE_QUANTUM_NANOS};
use crate::game::conversion::{ConversionError, convert_one_wire};
use crate::game::economy::{self, EconomyError};
use crate::game::rng::GameRng;
use crate::game::state::GameState;
use std::collections::HashMap;
use std::error::Error;
use std::fmt;
use std::future::Future;
use std::pin::Pin;
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, oneshot, watch};
use tokio::task::JoinHandle;

pub const COMMAND_QUEUE_CAPACITY: usize = 64;
pub const MAX_UPDATES_PER_TURN: u8 = 10;
pub const MAX_COMMANDS_PER_TURN: usize = 16;
pub const HOST_DISCONTINUITY: Duration = Duration::from_secs(60);

#[cfg(test)]
type TestGate = Option<std::sync::Arc<CommandTestGate>>;
#[cfg(not(test))]
type TestGate = ();

/// Test-only admission gate at the real writer execution boundary. It is not
/// compiled into production and is never reachable from configuration or HTTP.
#[cfg(test)]
pub(crate) struct CommandTestGate {
    entered: watch::Sender<usize>,
    released: watch::Sender<bool>,
}

#[cfg(test)]
impl Default for CommandTestGate {
    fn default() -> Self {
        let (entered, _) = watch::channel(0);
        let (released, _) = watch::channel(false);
        Self { entered, released }
    }
}

#[cfg(test)]
impl CommandTestGate {
    async fn wait(&self) {
        self.entered.send_modify(|entered| *entered += 1);
        let mut released = self.released.subscribe();
        while !*released.borrow_and_update() {
            released.changed().await.expect("test release sender lives");
        }
    }

    pub(crate) async fn wait_entered(&self, expected: usize) {
        let mut entered = self.entered.subscribe();
        while *entered.borrow_and_update() < expected {
            entered.changed().await.expect("test entry sender lives");
        }
    }

    pub(crate) fn release(&self) {
        self.released.send_replace(true);
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct CommandId(u64);

impl CommandId {
    pub fn new(value: u64) -> Result<Self, BoundedIntegerError> {
        if value <= MAX_SAFE_JSON_INTEGER {
            Ok(Self(value))
        } else {
            Err(BoundedIntegerError::AboveJsonSafeRange)
        }
    }

    pub fn get(self) -> u64 {
        self.0
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Command {
    id: CommandId,
    intent: Intent,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Intent {
    MakePaperclip,
    BuyWire,
    LowerPrice,
    RaisePrice,
    BuyMarketing,
    BuyAutoClipper,
}

impl Command {
    /// The manual M1 intent: exactly one Wire, with no amount argument.
    pub fn make_paperclip(id: CommandId) -> Self {
        Self {
            id,
            intent: Intent::MakePaperclip,
        }
    }

    pub fn buy_wire(id: CommandId) -> Self {
        Self::intent(id, Intent::BuyWire)
    }

    pub fn lower_price(id: CommandId) -> Self {
        Self::intent(id, Intent::LowerPrice)
    }

    pub fn raise_price(id: CommandId) -> Self {
        Self::intent(id, Intent::RaisePrice)
    }

    pub fn buy_marketing(id: CommandId) -> Self {
        Self::intent(id, Intent::BuyMarketing)
    }

    pub fn buy_auto_clipper(id: CommandId) -> Self {
        Self::intent(id, Intent::BuyAutoClipper)
    }

    fn intent(id: CommandId, intent: Intent) -> Self {
        Self { id, intent }
    }

    pub fn id(&self) -> CommandId {
        self.id
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CommandRejection {
    Conversion(ConversionError),
    Economy(EconomyError),
    ConflictingRetry,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommandReceipt {
    pub revision: u64,
    pub result: Result<(), CommandRejection>,
}

#[derive(Debug)]
pub struct PendingCommand {
    receiver: oneshot::Receiver<CommandReceipt>,
}

impl PendingCommand {
    pub async fn wait(self) -> Result<CommandReceipt, SubmitError> {
        self.receiver.await.map_err(|_| SubmitError::RuntimeClosed)
    }

    #[cfg(test)]
    pub(crate) fn from_test_receiver(receiver: oneshot::Receiver<CommandReceipt>) -> Self {
        Self { receiver }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubmitError {
    QueueFull,
    RuntimeClosed,
}

impl fmt::Display for SubmitError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::QueueFull => formatter.write_str("bounded command queue is full"),
            Self::RuntimeClosed => formatter.write_str("game runtime is closed"),
        }
    }
}

impl Error for SubmitError {}

struct QueuedCommand {
    command: Command,
    response: oneshot::Sender<CommandReceipt>,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ProcessStatus {
    pub lag_debt_nanos: u128,
    pub degraded: bool,
    pub discontinuity_events: u64,
    pub nonmonotonic_events: u64,
    pub overload_turns: u64,
    pub writer_turns: u64,
    pub lag_batches: u64,
    pub full_lag_batches: u64,
    pub command_batches: u64,
    pub max_updates_in_turn: u8,
    pub max_commands_in_turn: usize,
    pub applied_commands: u64,
    pub rejected_commands: u64,
    pub retry_hits: u64,
}

#[derive(Clone, Debug)]
pub struct RuntimeView {
    pub game: GameState,
    pub revision: u64,
    pub run_id: String,
    pub process: ProcessStatus,
}

#[derive(Clone)]
pub struct RuntimeHandle {
    sender: mpsc::Sender<QueuedCommand>,
    views: watch::Receiver<RuntimeView>,
}

impl RuntimeHandle {
    pub fn view(&self) -> RuntimeView {
        self.views.borrow().clone()
    }

    pub fn subscribe(&self) -> watch::Receiver<RuntimeView> {
        self.views.clone()
    }

    pub fn try_submit(&self, command: Command) -> Result<PendingCommand, SubmitError> {
        let (response, receiver) = oneshot::channel();
        self.sender
            .try_send(QueuedCommand { command, response })
            .map_err(|error| match error {
                mpsc::error::TrySendError::Full(_) => SubmitError::QueueFull,
                mpsc::error::TrySendError::Closed(_) => SubmitError::RuntimeClosed,
            })?;
        Ok(PendingCommand { receiver })
    }

    pub async fn execute(&self, command: Command) -> Result<CommandReceipt, SubmitError> {
        let (response, receiver) = oneshot::channel();
        self.sender
            .send(QueuedCommand { command, response })
            .await
            .map_err(|_| SubmitError::RuntimeClosed)?;
        PendingCommand { receiver }.wait().await
    }
}

/// Supervisor for the one writer task. Dropping it signals bounded termination.
pub struct GameRuntime {
    handle: RuntimeHandle,
    shutdown: Option<oneshot::Sender<()>>,
    writer: Option<JoinHandle<Result<(), RuntimeFailure>>>,
}

impl GameRuntime {
    pub fn start() -> Result<Self, RuntimeStartError> {
        let state = GameState::fresh(GameRng::from_entropy().map_err(RuntimeStartError::Entropy)?);
        Self::start_with_clock(RealClock::new(), state)
    }

    /// Start a new process identity over a fully validated logical snapshot.
    /// Process-local retry records, lag debt and wall-clock baselines stay fresh.
    pub fn start_from_snapshot(state: GameState, revision: u64) -> Result<Self, RuntimeStartError> {
        if revision > MAX_SAFE_JSON_INTEGER {
            return Err(RuntimeStartError::RevisionOutOfRange);
        }
        Self::start_with_clock_at_revision(RealClock::new(), state, revision)
    }

    pub fn handle(&self) -> RuntimeHandle {
        self.handle.clone()
    }

    fn start_with_clock<C>(clock: C, state: GameState) -> Result<Self, RuntimeStartError>
    where
        C: MonotonicClock,
    {
        Self::start_with_clock_at_revision(clock, state, 0)
    }

    fn start_with_clock_at_revision<C>(
        clock: C,
        state: GameState,
        revision: u64,
    ) -> Result<Self, RuntimeStartError>
    where
        C: MonotonicClock,
    {
        if revision > MAX_SAFE_JSON_INTEGER {
            return Err(RuntimeStartError::RevisionOutOfRange);
        }
        #[cfg(not(test))]
        {
            Self::start_with_gate(clock, state, revision, ())
        }
        #[cfg(test)]
        {
            Self::start_with_gate(clock, state, revision, None)
        }
    }

    #[cfg(test)]
    pub(crate) fn start_with_test_gate<C>(
        clock: C,
        state: GameState,
        gate: std::sync::Arc<CommandTestGate>,
    ) -> Result<Self, RuntimeStartError>
    where
        C: MonotonicClock,
    {
        Self::start_with_gate(clock, state, 0, Some(gate))
    }

    fn start_with_gate<C>(
        clock: C,
        state: GameState,
        revision: u64,
        test_gate: TestGate,
    ) -> Result<Self, RuntimeStartError>
    where
        C: MonotonicClock,
    {
        let runtime =
            tokio::runtime::Handle::try_current().map_err(|_| RuntimeStartError::NoRuntime)?;
        let run_id = fresh_run_id().map_err(RuntimeStartError::Entropy)?;
        let writer = Writer::new(clock, state, run_id, revision, test_gate);
        let (sender, receiver) = mpsc::channel(COMMAND_QUEUE_CAPACITY);
        let initial = writer.view();
        let (view_sender, views) = watch::channel(initial);
        let handle = RuntimeHandle { sender, views };
        let (shutdown, shutdown_receiver) = oneshot::channel();
        let writer_task =
            runtime.spawn(run_writer(writer, receiver, shutdown_receiver, view_sender));
        Ok(Self {
            handle,
            shutdown: Some(shutdown),
            writer: Some(writer_task),
        })
    }

    /// Request graceful termination. The writer closes admission when it
    /// observes this signal, then drains everything already accepted.
    pub(crate) fn request_shutdown(&mut self) {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
    }

    /// Wait for bounded accepted-queue drain and final publication of the
    /// runtime view. This never implements crash persistence.
    pub(crate) async fn wait_for_writer(mut self) -> Result<(), RuntimeShutdownError> {
        let writer = self.writer.take().expect("shutdown consumes a live writer");
        match writer.await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => Err(RuntimeShutdownError::Writer(error)),
            Err(_) => Err(RuntimeShutdownError::WriterTaskEnded),
        }
    }

    pub async fn shutdown(mut self) -> Result<(), RuntimeShutdownError> {
        self.request_shutdown();
        self.wait_for_writer().await
    }
}

impl Drop for GameRuntime {
    fn drop(&mut self) {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
    }
}

#[derive(Debug)]
pub enum RuntimeStartError {
    NoRuntime,
    RevisionOutOfRange,
    Entropy(getrandom::Error),
}

impl fmt::Display for RuntimeStartError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NoRuntime => formatter.write_str("GameRuntime must start inside a Tokio runtime"),
            Self::RevisionOutOfRange => {
                formatter.write_str("restored revision exceeds the safe JSON range")
            }
            Self::Entropy(_) => formatter.write_str("operating-system entropy is unavailable"),
        }
    }
}

impl Error for RuntimeStartError {}

#[derive(Debug)]
pub enum RuntimeShutdownError {
    WriterTaskEnded,
    Writer(RuntimeFailure),
}

impl fmt::Display for RuntimeShutdownError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::WriterTaskEnded => formatter.write_str("game writer task ended unexpectedly"),
            Self::Writer(_) => {
                formatter.write_str("game writer stopped on a checked runtime failure")
            }
        }
    }
}

impl Error for RuntimeShutdownError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeFailure {
    CounterLimit,
    LogicalClock(ClockError),
    Economy(EconomyError),
}

impl fmt::Display for RuntimeFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::CounterLimit => formatter.write_str("checked runtime counter limit reached"),
            Self::LogicalClock(_) => formatter.write_str("checked logical clock limit reached"),
            Self::Economy(_) => {
                formatter.write_str("economy evaluation failed without a partial commit")
            }
        }
    }
}

impl Error for RuntimeFailure {}

fn fresh_run_id() -> Result<String, getrandom::Error> {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes)?;
    let mut output = String::with_capacity(32);
    for byte in bytes {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    Ok(output)
}

pub(crate) trait MonotonicClock: Send + Sync + 'static {
    fn now(&self) -> Instant;
    fn wait_until(&self, deadline: Instant) -> Pin<Box<dyn Future<Output = ()> + Send + '_>>;
}

struct RealClock;

impl RealClock {
    fn new() -> Self {
        Self
    }
}

impl MonotonicClock for RealClock {
    fn now(&self) -> Instant {
        Instant::now()
    }

    fn wait_until(&self, deadline: Instant) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
        Box::pin(tokio::time::sleep_until(tokio::time::Instant::from_std(
            deadline,
        )))
    }
}

struct RetryRecord {
    command: Command,
    receipt: CommandReceipt,
}

struct Writer<C> {
    clock: C,
    #[cfg(test)]
    test_gate: TestGate,
    state: GameState,
    revision: u64,
    run_id: String,
    retries: HashMap<CommandId, RetryRecord>,
    status: ProcessStatus,
    last_observation: Instant,
    lag_debt_nanos: u128,
}

impl<C: MonotonicClock> Writer<C> {
    fn new(
        clock: C,
        state: GameState,
        run_id: String,
        revision: u64,
        _test_gate: TestGate,
    ) -> Self {
        let last_observation = clock.now();
        Self {
            clock,
            #[cfg(test)]
            test_gate: _test_gate,
            state,
            revision,
            run_id,
            retries: HashMap::new(),
            status: ProcessStatus::default(),
            last_observation,
            lag_debt_nanos: 0,
        }
    }

    fn view(&self) -> RuntimeView {
        RuntimeView {
            game: self.state.clone(),
            revision: self.revision,
            run_id: self.run_id.clone(),
            process: self.status.clone(),
        }
    }

    fn observe_clock(&mut self) -> Result<Instant, RuntimeFailure> {
        let now = self.clock.now();
        let elapsed = now.checked_duration_since(self.last_observation);
        self.last_observation = now;
        match elapsed {
            None => {
                self.lag_debt_nanos = 0;
                increment(&mut self.status.nonmonotonic_events)?;
                self.status.degraded = true;
            }
            Some(gap) if gap >= HOST_DISCONTINUITY => {
                self.lag_debt_nanos = 0;
                increment(&mut self.status.discontinuity_events)?;
                self.status.degraded = true;
            }
            Some(gap) => {
                self.lag_debt_nanos = self
                    .lag_debt_nanos
                    .checked_add(gap.as_nanos())
                    .ok_or(RuntimeFailure::CounterLimit)?;
            }
        }
        self.status.lag_debt_nanos = self.lag_debt_nanos;
        Ok(now)
    }

    fn advance_tick(&mut self) -> Result<(), RuntimeFailure> {
        let next_revision = next_revision(self.revision)?;
        let mut candidate = self.state.clone();
        let cadence = candidate
            .clock
            .advance()
            .map_err(RuntimeFailure::LogicalClock)?;
        if cadence.fast_due {
            economy::advance_fast_phase(&mut candidate).map_err(RuntimeFailure::Economy)?;
            economy::observe_auto_clipper_reveal(&mut candidate.pro);
        }
        economy::advance_auto_clippers(&mut candidate, cadence.second_due)
            .map_err(RuntimeFailure::Economy)?;
        economy::observe_computational_resources(&mut candidate.pro);
        self.state = candidate;
        self.revision = next_revision;
        self.lag_debt_nanos -= UPDATE_QUANTUM_NANOS;
        Ok(())
    }

    fn execute_new(&mut self, command: Command) -> Result<CommandReceipt, RuntimeFailure> {
        let next_revision = next_revision(self.revision)?;
        let mut candidate = self.state.clone();
        let outcome = match command.intent {
            Intent::MakePaperclip => convert_one_wire(&mut candidate.pro)
                .map(|_| ())
                .map_err(CommandRejection::Conversion),
            Intent::BuyWire => {
                economy::buy_wire(&mut candidate.pro).map_err(CommandRejection::Economy)
            }
            Intent::LowerPrice => {
                economy::lower_price(&mut candidate.pro).map_err(CommandRejection::Economy)
            }
            Intent::RaisePrice => {
                economy::raise_price(&mut candidate.pro).map_err(CommandRejection::Economy)
            }
            Intent::BuyMarketing => {
                economy::buy_marketing(&mut candidate.pro).map_err(CommandRejection::Economy)
            }
            Intent::BuyAutoClipper => {
                economy::buy_auto_clipper(&mut candidate.pro).map_err(CommandRejection::Economy)
            }
        };
        if outcome.is_ok() {
            match command.intent {
                Intent::BuyWire => {
                    let message = format!("Wire spool purchased at ${}.", candidate.pro.wire_quote);
                    economy::push_console_message(&mut candidate.pro, message);
                }
                Intent::BuyMarketing => {
                    let message = format!(
                        "Marketing level {} purchased.",
                        candidate.pro.marketing_level
                    );
                    economy::push_console_message(&mut candidate.pro, message);
                }
                _ => {}
            }
            economy::observe_auto_clipper_reveal(&mut candidate.pro);
            economy::observe_computational_resources(&mut candidate.pro);
        }
        let result = match outcome {
            Ok(()) => {
                self.state = candidate;
                self.revision = next_revision;
                increment(&mut self.status.applied_commands)?;
                Ok(())
            }
            Err(error) => {
                increment(&mut self.status.rejected_commands)?;
                Err(error)
            }
        };
        let receipt = CommandReceipt {
            revision: self.revision,
            result,
        };
        self.retries.insert(
            command.id,
            RetryRecord {
                command: command.clone(),
                receipt: receipt.clone(),
            },
        );
        Ok(receipt)
    }

    fn execute(&mut self, command: Command) -> Result<CommandReceipt, RuntimeFailure> {
        if let Some(record) = self.retries.get(&command.id) {
            if record.command == command {
                increment(&mut self.status.retry_hits)?;
                return Ok(record.receipt.clone());
            }
            increment(&mut self.status.rejected_commands)?;
            return Ok(CommandReceipt {
                revision: self.revision,
                result: Err(CommandRejection::ConflictingRetry),
            });
        }
        self.execute_new(command)
    }

    async fn turn(
        &mut self,
        receiver: &mut mpsc::Receiver<QueuedCommand>,
        pending: &mut Option<QueuedCommand>,
    ) -> Result<(), RuntimeFailure> {
        self.observe_clock()?;
        increment(&mut self.status.writer_turns)?;
        let mut updates = 0u8;
        while updates < MAX_UPDATES_PER_TURN && self.lag_debt_nanos >= UPDATE_QUANTUM_NANOS {
            self.advance_tick()?;
            updates += 1;
        }
        if updates > 0 {
            increment(&mut self.status.lag_batches)?;
            if updates == MAX_UPDATES_PER_TURN {
                increment(&mut self.status.full_lag_batches)?;
            }
        }
        self.status.max_updates_in_turn = self.status.max_updates_in_turn.max(updates);

        let mut commands = 0usize;
        while commands < MAX_COMMANDS_PER_TURN {
            let queued = match pending.take() {
                Some(command) => Some(command),
                None => receiver.try_recv().ok(),
            };
            let Some(queued) = queued else { break };
            #[cfg(test)]
            if let Some(gate) = &self.test_gate {
                gate.wait().await;
            }
            let receipt = self.execute(queued.command)?;
            let _ = queued.response.send(receipt);
            commands += 1;
        }
        if commands > 0 {
            increment(&mut self.status.command_batches)?;
        }
        self.status.max_commands_in_turn = self.status.max_commands_in_turn.max(commands);
        self.status.lag_debt_nanos = self.lag_debt_nanos;
        if self.lag_debt_nanos >= UPDATE_QUANTUM_NANOS {
            increment(&mut self.status.overload_turns)?;
            self.status.degraded = true;
        }
        Ok(())
    }
}

fn increment(counter: &mut u64) -> Result<(), RuntimeFailure> {
    *counter = counter.checked_add(1).ok_or(RuntimeFailure::CounterLimit)?;
    Ok(())
}

fn next_revision(revision: u64) -> Result<u64, RuntimeFailure> {
    revision
        .checked_add(1)
        .filter(|value| *value <= MAX_SAFE_JSON_INTEGER)
        .ok_or(RuntimeFailure::CounterLimit)
}

async fn run_writer<C: MonotonicClock>(
    mut writer: Writer<C>,
    mut receiver: mpsc::Receiver<QueuedCommand>,
    mut shutdown: oneshot::Receiver<()>,
    views: watch::Sender<RuntimeView>,
) -> Result<(), RuntimeFailure> {
    let mut pending = None;
    let mut draining = false;
    loop {
        if !draining {
            match shutdown.try_recv() {
                Ok(()) | Err(oneshot::error::TryRecvError::Closed) => {
                    // This is the admission linearization point. try_send
                    // succeeds only before close; every success before it is
                    // retained by mpsc for the bounded turns below.
                    receiver.close();
                    draining = true;
                }
                Err(oneshot::error::TryRecvError::Empty) => {}
            }
        }
        if draining && pending.is_none() && receiver.is_empty() {
            break;
        }
        writer.turn(&mut receiver, &mut pending).await?;
        let _ = views.send(writer.view());
        if draining {
            continue;
        }

        if writer.lag_debt_nanos >= UPDATE_QUANTUM_NANOS || pending.is_some() {
            continue;
        }
        let remaining = UPDATE_QUANTUM_NANOS - writer.lag_debt_nanos;
        let deadline = writer.last_observation + Duration::from_nanos(remaining as u64);
        tokio::select! {
            biased;
            _ = &mut shutdown => {
                receiver.close();
                draining = true;
            },
            received = receiver.recv() => {
                match received {
                    Some(command) => pending = Some(command),
                    None => {
                        receiver.close();
                        draining = true;
                    },
                }
            }
            _ = writer.clock.wait_until(deadline) => {}
        }
    }
    receiver.close();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::amount::{Amount, NonNegativeAmount};
    use crate::game::economy::{demand_ratio, refresh_demand};
    use crate::game::evaluator::{DECISION_LIMIT, sale_request};
    use crate::game::state::ProState;
    use std::sync::{Arc, Mutex};
    use tokio::sync::Notify;
    use tokio::time::timeout;

    struct FakeClock {
        origin: Instant,
        now: Mutex<Instant>,
        wake: Notify,
    }

    impl FakeClock {
        fn new() -> Self {
            let origin = Instant::now();
            Self {
                origin,
                now: Mutex::new(origin),
                wake: Notify::new(),
            }
        }

        fn set_elapsed(&self, elapsed: Duration) {
            *self.now.lock().expect("fake clock lock") =
                self.origin.checked_add(elapsed).expect("bounded fake time");
            self.wake.notify_one();
        }

        fn advance(&self, amount: Duration) {
            let mut now = self.now.lock().expect("fake clock lock");
            *now = now.checked_add(amount).expect("bounded fake time");
            drop(now);
            self.wake.notify_one();
        }
    }

    impl MonotonicClock for Arc<FakeClock> {
        fn now(&self) -> Instant {
            *self.now.lock().expect("fake clock lock")
        }

        fn wait_until(&self, _deadline: Instant) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
            Box::pin(self.wake.notified())
        }
    }

    fn test_runtime() -> (GameRuntime, RuntimeHandle, Arc<FakeClock>) {
        test_runtime_with_state(GameState::fresh(GameRng::from_test_seed([9u8; 32])))
    }

    fn test_runtime_with_wire(wire: &str) -> (GameRuntime, RuntimeHandle, Arc<FakeClock>) {
        let mut state = GameState::fresh(GameRng::from_test_seed([9u8; 32]));
        state.pro.wire = Amount::parse(wire).unwrap().nonnegative().unwrap();
        test_runtime_with_state(state)
    }

    fn test_runtime_with_state(state: GameState) -> (GameRuntime, RuntimeHandle, Arc<FakeClock>) {
        let clock = Arc::new(FakeClock::new());
        let runtime = GameRuntime::start_with_clock(clock.clone(), state).unwrap();
        let handle = runtime.handle();
        (runtime, handle, clock)
    }

    fn command(id: u64) -> Command {
        Command::make_paperclip(CommandId::new(id).unwrap())
    }

    async fn wait_for(
        handle: &RuntimeHandle,
        predicate: impl Fn(&RuntimeView) -> bool,
    ) -> RuntimeView {
        let mut views = handle.subscribe();
        timeout(Duration::from_secs(3), async move {
            loop {
                let current = views.borrow().clone();
                if predicate(&current) {
                    return current;
                }
                views.changed().await.expect("writer remains observable");
            }
        })
        .await
        .expect("bounded fake-clock progress")
    }

    struct RuntimeDatabase(std::path::PathBuf);

    impl RuntimeDatabase {
        fn new(label: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "paperclip-game-runtime-persistence-{label}-{}.sqlite3",
                std::process::id()
            ));
            let fixture = Self(path);
            fixture.remove_files();
            fixture
        }

        fn remove_files(&self) {
            for suffix in ["", "-journal", "-shm", "-wal"] {
                let _ = std::fs::remove_file(format!("{}{suffix}", self.0.display()));
            }
        }
    }

    impl Drop for RuntimeDatabase {
        fn drop(&mut self) {
            self.remove_files();
        }
    }

    fn persistent_runtime(
        label: &str,
    ) -> (
        GameRuntime,
        RuntimeHandle,
        crate::persistence::RuntimePersistence,
        Arc<FakeClock>,
        RuntimeDatabase,
    ) {
        persistent_runtime_with_producers(label, 0)
    }

    fn persistent_runtime_with_producers(
        label: &str,
        producers: i128,
    ) -> (
        GameRuntime,
        RuntimeHandle,
        crate::persistence::RuntimePersistence,
        Arc<FakeClock>,
        RuntimeDatabase,
    ) {
        use crate::persistence::{RuntimePersistence, SnapshotStore};
        use crate::snapshot::Snapshot;

        let database = RuntimeDatabase::new(label);
        let mut state = GameState::fresh(GameRng::from_test_seed([23_u8; 32]));
        state.pro.wire = Amount::parse("100").unwrap().nonnegative().unwrap();
        state.pro.auto_clippers = crate::game::amount::IntegralAmount::from_i128(producers);
        state.pro.auto_clipper_revealed = producers > 0;
        let initial = Snapshot::capture(&state, 0).unwrap();
        let (store, stored) = SnapshotStore::open_or_initialize(&database.0, &initial).unwrap();
        let clock = Arc::new(FakeClock::new());
        let runtime = GameRuntime::start_with_clock_at_revision(clock.clone(), state, 0).unwrap();
        let handle = runtime.handle();
        let persistence =
            RuntimePersistence::start(&handle, store, 0, stored.capture_sequence).unwrap();
        (runtime, handle, persistence, clock, database)
    }

    async fn wait_for_health(
        persistence: &crate::persistence::RuntimePersistence,
        predicate: impl Fn(&crate::health::HealthSnapshot) -> bool,
    ) -> crate::health::HealthSnapshot {
        timeout(Duration::from_secs(3), async {
            loop {
                let health = persistence.health().snapshot();
                if predicate(&health) {
                    return health;
                }
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap_or_else(|_| {
            panic!(
                "bounded persistence health transition: {:?}",
                persistence.health().snapshot()
            )
        })
    }

    fn restore_database(path: &std::path::Path) -> (u64, u64, GameState) {
        use crate::persistence::SnapshotStore;
        use crate::snapshot::Snapshot;

        let candidate = GameState::fresh(GameRng::from_test_seed([24_u8; 32]));
        let candidate = Snapshot::capture(&candidate, 0).unwrap();
        let (_store, stored) = SnapshotStore::open_or_initialize(path, &candidate).unwrap();
        let restored = stored.snapshot.restore().unwrap();
        (restored.revision, stored.capture_sequence, restored.state)
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn persistence_publisher_observes_29999_and_30000_millisecond_boundary() {
        use crate::health::PersistencePhase;

        let (runtime, handle, persistence, clock, database) = persistent_runtime("cadence");
        clock.advance(Duration::from_millis(29_999));
        let before = wait_for(&handle, |view| view.game.clock.update_count() == 2_999).await;
        assert_eq!(before.revision, 2_999);
        let no_early_commit = timeout(Duration::from_millis(25), async {
            loop {
                if persistence.health().snapshot().last_committed_sequence > Some(0) {
                    return;
                }
                tokio::task::yield_now().await;
            }
        })
        .await;
        assert!(no_early_commit.is_err(), "no snapshot before 30 seconds");

        clock.advance(Duration::from_millis(1));
        let saved = wait_for_health(&persistence, |health| {
            health.last_committed_revision == Some(3_000)
        })
        .await;
        assert_eq!(saved.last_committed_sequence, Some(1));
        assert_eq!(saved.latest_captured_revision, Some(3_000));
        assert_eq!(saved.phase, PersistencePhase::Ready);

        let final_view = handle.view();
        runtime.shutdown().await.unwrap();
        let stopped = persistence.shutdown(final_view).await.unwrap();
        assert_eq!(stopped.phase, PersistencePhase::Stopped);
        assert_eq!(stopped.last_committed_revision, Some(3_000));
        let (revision, sequence, restored) = restore_database(&database.0);
        assert_eq!(revision, 3_000);
        assert_eq!(
            sequence, 2,
            "normal shutdown saves the final view once more"
        );
        assert_eq!(restored.clock.update_count(), 3_000);
        assert_eq!(restored.rng_state_hex(), handle.view().game.rng_state_hex());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn persistence_blocking_does_not_stop_runtime_and_valid_commit_recovers_health() {
        use crate::health::{PersistenceFailure, PersistencePhase};

        let (runtime, handle, persistence, clock, database) =
            persistent_runtime_with_producers("blocking", 1);
        let blocker = rusqlite::Connection::open(&database.0).unwrap();
        blocker.execute_batch("BEGIN IMMEDIATE").unwrap();
        clock.advance(Duration::from_secs(30));
        let degraded = wait_for_health(&persistence, |health| {
            health.last_failure == Some(PersistenceFailure::DatabaseBusy) && !health.ready
        })
        .await;
        assert!(degraded.live);
        assert!(degraded.last_committed_revision == Some(0));
        assert!(matches!(
            degraded.phase,
            PersistencePhase::Retrying | PersistencePhase::Degraded
        ));

        let receipt = handle.execute(command(7_777)).await.unwrap();
        assert_eq!(receipt.result, Ok(()));
        clock.advance(Duration::from_millis(10));
        let live = wait_for(&handle, |view| view.game.clock.update_count() == 3_001).await;
        assert!(live.revision > receipt.revision);
        assert_eq!(live.game.pro.wire.to_string(), "68.99");
        assert_eq!(live.game.pro.lifetime_clips.to_string(), "31.01");
        assert_eq!(live.game.pro.auto_clippers.to_string(), "1");
        assert_eq!(live.game.pro.auto_clipper_rate.to_string(), "1");
        eprintln!(
            "G03/PERSIST-SNAPSHOT-30S-NONBLOCK: one producer continued through real SQLite busy capture; 30.01 automatic + one manual clip reaches exact update 3,001"
        );
        clock.advance(Duration::from_secs(30));
        let still_degraded = wait_for_health(&persistence, |health| {
            health.latest_captured_revision >= Some(6_000)
        })
        .await;
        assert!(still_degraded.latest_captured_revision > still_degraded.last_committed_revision);
        assert!(!still_degraded.ready);
        assert!(still_degraded.live);

        blocker.execute_batch("ROLLBACK").unwrap();
        // One further capture opportunity proves recovery even if the blocked
        // attempt already exhausted its bounded retries while fake time advanced.
        clock.advance(Duration::from_secs(30));
        let recovered = wait_for_health(&persistence, |health| {
            health.ready && health.last_committed_revision >= Some(9_000)
        })
        .await;
        assert_eq!(recovered.current_attempt, 0);
        assert_eq!(recovered.consecutive_failures, 0);
        assert_eq!(recovered.last_failure, None);

        let final_view = handle.view();
        runtime.shutdown().await.unwrap();
        persistence.shutdown(final_view).await.unwrap();
        let (revision, _sequence, restored) = restore_database(&database.0);
        assert_eq!(revision, handle.view().revision);
        assert_eq!(restored.clock, handle.view().game.clock);
        assert_eq!(restored.pro, handle.view().game.pro);
        assert_eq!(restored.rng_state_hex(), handle.view().game.rng_state_hex());
    }

    #[tokio::test]
    async fn negative_table_manual_command_and_below_one_rejection_are_atomic() {
        let (runtime, handle, _clock) = test_runtime();
        let initial = handle.view();
        assert_eq!(initial.process.lag_debt_nanos, 0);
        assert_eq!(initial.game.pro, ProState::fresh());
        assert_eq!(initial.game.rng_state_hex().len(), 114);

        let receipt = handle.execute(command(1)).await.unwrap();
        assert_eq!(
            receipt,
            CommandReceipt {
                revision: 1,
                result: Ok(())
            }
        );
        let view = handle.view();
        assert_eq!(view.game.pro.wire.to_string(), "999");
        assert_eq!(view.game.pro.lifetime_clips.to_string(), "1");
        assert_eq!(view.game.pro.unsold_clips.to_string(), "1");
        assert_eq!(view.game.pro.unused_clips.to_string(), "1");
        runtime.shutdown().await.unwrap();

        let (runtime, handle, _clock) = test_runtime_with_wire("0.5");
        let before = handle.view().game.clone();
        let receipt = handle.execute(command(2)).await.unwrap();
        assert_eq!(receipt.revision, 0);
        assert_eq!(
            receipt.result,
            Err(CommandRejection::Conversion(
                ConversionError::InsufficientWire
            ))
        );
        assert_eq!(handle.view().game.pro, before.pro);
        assert_eq!(handle.view().game.clock, before.clock);
        assert_eq!(handle.view().game.rng_state_hex(), before.rng_state_hex());
        assert_eq!(handle.view().revision, 0);
        eprintln!("below-one Wire: InsufficientWire; full game state and revision unchanged");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn computational_unlock_commits_once_at_exact_2000_across_retry_rejection_and_tick() {
        let mut state = GameState::fresh(GameRng::from_test_seed([42_u8; 32]));
        state.pro.lifetime_clips = NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.unsold_clips = NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.unused_clips = NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.wire = NonNegativeAmount::from_i128(1).unwrap();
        state.pro.funds = Amount::from_i128(100);
        let (runtime, handle, clock) = test_runtime_with_state(state);
        assert!(handle.view().game.pro.computing_hidden);
        assert!(handle.view().game.pro.projects_hidden);

        let applied = handle.execute(command(42_000)).await.unwrap();
        assert_eq!(applied.revision, 1);
        assert_eq!(applied.result, Ok(()));
        let unlocked = handle.view();
        assert_eq!(unlocked.game.pro.lifetime_clips.to_string(), "2000");
        assert_eq!(unlocked.game.pro.wire, NonNegativeAmount::zero());
        assert!(!unlocked.game.pro.computing_hidden);
        assert!(!unlocked.game.pro.projects_hidden);
        assert_eq!(unlocked.game.pro.trust.to_string(), "2");
        assert_eq!(unlocked.game.pro.processors.to_string(), "1");
        assert_eq!(unlocked.game.pro.memory.to_string(), "1");
        assert_eq!(
            unlocked
                .game
                .pro
                .console_messages
                .iter()
                .filter(|message| *message == economy::COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE)
                .count(),
            1
        );

        let replay = handle.execute(command(42_000)).await.unwrap();
        assert_eq!(replay, applied);
        assert_eq!(handle.view().game.pro, unlocked.game.pro);
        let rejected = handle.execute(command(42_001)).await.unwrap();
        assert_eq!(rejected.revision, 1);
        assert_eq!(
            rejected.result,
            Err(CommandRejection::Conversion(
                ConversionError::InsufficientWire
            ))
        );
        assert_eq!(handle.view().game.pro, unlocked.game.pro);

        clock.advance(Duration::from_millis(10));
        let after_tick = wait_for(&handle, |view| view.game.clock.update_count() == 1).await;
        assert_eq!(after_tick.game.pro, unlocked.game.pro);
        assert_eq!(
            after_tick
                .game
                .pro
                .console_messages
                .iter()
                .filter(|message| *message == economy::COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE)
                .count(),
            1
        );
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn stranded_rejection_has_no_partial_unlock_then_successful_tick_latches_once() {
        let mut state = GameState::fresh(GameRng::from_test_seed([43_u8; 32]));
        state.pro.wire = NonNegativeAmount::zero();
        let (runtime, handle, clock) = test_runtime_with_state(state);
        assert!(economy::computational_resources_unlock_condition(
            &handle.view().game.pro
        ));
        let before = handle.view();

        let rejected = handle.execute(command(43_000)).await.unwrap();
        assert_eq!(rejected.revision, 0);
        assert_eq!(
            rejected.result,
            Err(CommandRejection::Conversion(
                ConversionError::InsufficientWire
            ))
        );
        assert_eq!(handle.view().game.pro, before.game.pro);
        assert!(handle.view().game.pro.computing_hidden);
        assert!(handle.view().game.pro.projects_hidden);
        assert_eq!(
            handle.view().game.pro.console_messages,
            before.game.pro.console_messages
        );

        clock.advance(Duration::from_millis(10));
        let unlocked = wait_for(&handle, |view| view.game.clock.update_count() == 1).await;
        assert!(!unlocked.game.pro.computing_hidden);
        assert!(!unlocked.game.pro.projects_hidden);
        assert_eq!(unlocked.game.pro.trust.to_string(), "2");
        assert_eq!(unlocked.game.pro.processors.to_string(), "1");
        assert_eq!(unlocked.game.pro.memory.to_string(), "1");
        assert_eq!(
            unlocked.game.pro.console_messages[4],
            economy::COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE
        );
        let latched_messages = unlocked.game.pro.console_messages.clone();

        clock.advance(Duration::from_millis(90));
        let repeated = wait_for(&handle, |view| view.game.clock.update_count() == 10).await;
        assert!(!repeated.game.pro.computing_hidden);
        assert!(!repeated.game.pro.projects_hidden);
        assert_eq!(repeated.game.pro.console_messages, latched_messages);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn concurrent_legal_commands_and_final_stock_contention_are_serial() {
        let (runtime, handle, _clock) = test_runtime_with_wire("2");
        let (a, b) = tokio::join!(handle.execute(command(1)), handle.execute(command(2)));
        assert_eq!(a.unwrap().result, Ok(()));
        assert_eq!(b.unwrap().result, Ok(()));
        assert_eq!(handle.view().game.pro.wire.to_string(), "0");
        assert_eq!(handle.view().game.pro.lifetime_clips.to_string(), "2");
        assert_eq!(handle.view().revision, 2);
        runtime.shutdown().await.unwrap();

        let (runtime, handle, _clock) = test_runtime_with_wire("1");
        let (a, b) = tokio::join!(handle.execute(command(3)), handle.execute(command(4)));
        let receipts = [a.unwrap(), b.unwrap()];
        assert_eq!(
            receipts
                .iter()
                .filter(|receipt| receipt.result == Ok(()))
                .count(),
            1
        );
        assert_eq!(
            receipts
                .iter()
                .filter(|receipt| receipt.result
                    == Err(CommandRejection::Conversion(
                        ConversionError::InsufficientWire
                    )))
                .count(),
            1
        );
        let view = handle.view();
        assert_eq!(view.game.pro.wire.to_string(), "0");
        assert_eq!(view.game.pro.lifetime_clips.to_string(), "1");
        assert_eq!(view.game.pro.unsold_clips.to_string(), "1");
        assert_eq!(view.game.pro.unused_clips.to_string(), "1");
        assert_eq!(view.revision, 1);
        let before_rejected = handle.view().game.clone();
        let rejected = handle.execute(command(5)).await.unwrap();
        assert_eq!(
            rejected.result,
            Err(CommandRejection::Conversion(
                ConversionError::InsufficientWire
            ))
        );
        assert_eq!(handle.view().game.pro, before_rejected.pro);
        assert_eq!(handle.view().game.clock, before_rejected.clock);
        assert_eq!(
            handle.view().game.rng_state_hex(),
            before_rejected.rng_state_hex()
        );
        assert_eq!(handle.view().revision, 1);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn r1_update_90_purchase_accrues_only_owned_ticks_and_full_later_second() {
        let mut state = GameState::fresh(GameRng::from_test_seed([90u8; 32]));
        state.clock =
            crate::game::clock::ClockState::from_snapshot_parts(90, 0, 90, 90, 4_000_000, 56)
                .unwrap();
        state.pro.funds = Amount::from_i128(5);
        state.pro.auto_clipper_revealed = true;
        state.pro.wire = Amount::parse("100").unwrap().nonnegative().unwrap();
        let (runtime, handle, clock) = test_runtime_with_state(state);
        let receipt = handle
            .execute(Command::buy_auto_clipper(CommandId::new(9_090).unwrap()))
            .await
            .unwrap();
        assert_eq!(receipt.result, Ok(()));
        let purchased = wait_for(&handle, |view| view.process.applied_commands == 1).await;
        assert_eq!(purchased.game.clock.update_count(), 90);
        assert_eq!(purchased.game.pro.lifetime_clips.to_string(), "0");
        assert_eq!(purchased.game.pro.auto_clipper_rate.to_string(), "0");

        clock.advance(Duration::from_millis(100));
        let boundary = wait_for(&handle, |view| view.game.clock.update_count() == 100).await;
        eprintln!(
            "R1 update 90 -> 100 ownership=10 ticks: lifetime={} wire={} rate={}",
            boundary.game.pro.lifetime_clips,
            boundary.game.pro.wire,
            boundary.game.pro.auto_clipper_rate
        );
        assert_eq!(boundary.game.pro.lifetime_clips.to_string(), "0.1");
        assert_eq!(boundary.game.pro.wire.to_string(), "99.9");
        assert_eq!(boundary.game.pro.auto_clipper_rate.to_string(), "0.1");
        for ledger in [
            &boundary.game.pro.lifetime_clips,
            &boundary.game.pro.unsold_clips,
            &boundary.game.pro.unused_clips,
        ] {
            assert_eq!(ledger.to_string(), "0.1");
        }

        // The following complete owned second contributes exactly one more clip.
        clock.advance(Duration::from_secs(1));
        let full_second = wait_for(&handle, |view| view.game.clock.update_count() == 200).await;
        assert_eq!(full_second.game.pro.lifetime_clips.to_string(), "1.1");
        assert_eq!(full_second.game.pro.wire.to_string(), "98.9");
        assert_eq!(full_second.game.pro.auto_clipper_rate.to_string(), "1");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn r1_lagged_command_starts_production_only_after_its_writer_execution_tick() {
        let mut state = GameState::fresh(GameRng::from_test_seed([91u8; 32]));
        state.pro.funds = Amount::from_i128(5);
        state.pro.auto_clipper_revealed = true;
        state.pro.wire = Amount::parse("100").unwrap().nonnegative().unwrap();
        let (runtime, handle, clock) = test_runtime_with_state(state);
        // Prove the idle writer is waiting, then make the command pending before
        // the one-second gap. The ordinary turn processes ten updates first.
        wait_for(&handle, |view| view.process.writer_turns >= 1).await;
        let pending = handle
            .try_submit(Command::buy_auto_clipper(CommandId::new(9_091).unwrap()))
            .unwrap();
        clock.advance(Duration::from_secs(1));
        let receipt = pending.wait().await.unwrap();
        assert_eq!(receipt.result, Ok(()));
        assert_eq!(
            receipt.revision, 11,
            "the lag turn executes ten updates before this one purchase"
        );
        // The writer may have drained the rest of the gap when this future is
        // scheduled again; the latest watch value is not the execution-time View.
        let boundary = wait_for(&handle, |view| view.game.clock.update_count() == 100).await;
        eprintln!(
            "R1 lagged purchase update=10 -> 100 ownership=90 ticks: lifetime={} wire={} rate={}",
            boundary.game.pro.lifetime_clips,
            boundary.game.pro.wire,
            boundary.game.pro.auto_clipper_rate
        );
        assert_eq!(boundary.game.pro.lifetime_clips.to_string(), "0.9");
        assert_eq!(boundary.game.pro.wire.to_string(), "99.1");
        assert_eq!(boundary.game.pro.auto_clipper_rate.to_string(), "0.9");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn r1_restore_preserves_partial_second_production_without_offline_backfill() {
        let mut state = GameState::fresh(GameRng::from_test_seed([93u8; 32]));
        state.clock =
            crate::game::clock::ClockState::from_snapshot_parts(90, 0, 90, 90, 4_000_000, 56)
                .unwrap();
        state.pro.funds = Amount::from_i128(5);
        state.pro.auto_clipper_revealed = true;
        state.pro.wire = Amount::parse("100").unwrap().nonnegative().unwrap();
        let (runtime, handle, clock) = test_runtime_with_state(state);
        assert_eq!(
            handle
                .execute(Command::buy_auto_clipper(CommandId::new(9_093).unwrap()))
                .await
                .unwrap()
                .result,
            Ok(())
        );
        clock.advance(Duration::from_millis(400));
        let saved = wait_for(&handle, |view| view.game.clock.update_count() == 130).await;
        assert_eq!(saved.game.pro.lifetime_clips.to_string(), "0.4");
        assert_eq!(saved.game.pro.auto_clipper_rate.to_string(), "0.1");
        assert_eq!(
            saved
                .game
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0.3"
        );
        let snapshot = crate::snapshot::Snapshot::capture(&saved.game, saved.revision).unwrap();
        let restored = crate::snapshot::Snapshot::from_canonical_bytes(
            &snapshot.to_canonical_bytes().unwrap(),
        )
        .unwrap()
        .restore()
        .unwrap();
        assert_eq!(restored.state.pro, saved.game.pro);
        runtime.shutdown().await.unwrap();

        let (resumed, resumed_handle, resumed_clock) = test_runtime_with_state(restored.state);
        let initial = resumed_handle.view();
        assert_eq!(initial.game.clock.update_count(), 130);
        assert_eq!(initial.game.pro.lifetime_clips.to_string(), "0.4");
        assert_eq!(
            initial
                .game
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0.3"
        );
        assert_eq!(initial.process.lag_debt_nanos, 0);
        assert_ne!(initial.run_id, saved.run_id);

        resumed_clock.advance(Duration::from_millis(70));
        let partial = wait_for(&resumed_handle, |view| {
            view.game.clock.update_count() == 137
        })
        .await;
        assert_eq!(partial.game.pro.lifetime_clips.to_string(), "0.47");
        assert_eq!(partial.game.pro.auto_clipper_rate.to_string(), "0.1");
        assert_eq!(
            partial
                .game
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0.37"
        );
        resumed_clock.advance(Duration::from_millis(630));
        let complete = wait_for(&resumed_handle, |view| {
            view.game.clock.update_count() == 200
        })
        .await;
        assert_eq!(complete.game.pro.lifetime_clips.to_string(), "1.1");
        assert_eq!(complete.game.pro.auto_clipper_rate.to_string(), "1");
        assert_eq!(
            complete
                .game
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0"
        );
        eprintln!(
            "R1 mid-window restore: update 130 lifetime 0.4/accumulator 0.3 resumed to 0.47 at 137 and 1.1/rate 1 at 200; zero startup backfill"
        );
        resumed.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn auto_clipper_writer_execution_and_same_id_replay_preserve_stored_costs() {
        let mut first = GameState::fresh(GameRng::from_test_seed([43u8; 32]));
        first.pro.funds = Amount::from_i128(5);
        first.pro.auto_clipper_revealed = true;
        let (runtime, handle, _clock) = test_runtime_with_state(first);
        let first_command = Command::buy_auto_clipper(CommandId::new(501).unwrap());
        let receipt = handle.execute(first_command.clone()).await.unwrap();
        assert_eq!(receipt.revision, 1);
        assert_eq!(receipt.result, Ok(()));
        let bought = handle.view();
        assert_eq!(bought.game.pro.funds, Amount::zero());
        assert_eq!(bought.game.pro.auto_clippers.to_string(), "1");
        assert_eq!(bought.game.pro.auto_clipper_cost.to_string(), "6.1");

        let before_rejection = bought.game.clone();
        let insufficient = handle
            .execute(Command::buy_auto_clipper(CommandId::new(502).unwrap()))
            .await
            .unwrap();
        assert_eq!(insufficient.revision, 1);
        assert_eq!(
            insufficient.result,
            Err(CommandRejection::Economy(EconomyError::InsufficientFunds))
        );
        assert_eq!(handle.view().game.pro, before_rejection.pro);
        assert_eq!(handle.view().revision, 1);

        // Let later logical state advance before replay: the stored receipt is
        // still the first terminal result and cannot buy another producer.
        _clock.advance(Duration::from_millis(10));
        wait_for(&handle, |view| view.game.clock.update_count() == 1).await;
        let replay = handle.execute(first_command).await.unwrap();
        assert_eq!(replay, receipt);
        let after_replay = handle.view();
        assert_eq!(after_replay.game.pro.auto_clippers.to_string(), "1");
        assert_eq!(after_replay.game.pro.auto_clipper_cost.to_string(), "6.1");
        runtime.shutdown().await.unwrap();

        let mut second = GameState::fresh(GameRng::from_test_seed([44u8; 32]));
        second.pro.funds = Amount::from_i128(20);
        second.pro.auto_clipper_revealed = true;
        second.pro.auto_clippers = crate::game::amount::IntegralAmount::from_i128(1);
        second.pro.auto_clipper_cost = Amount::parse("6.1").unwrap();
        let (runtime, handle, _clock) = test_runtime_with_state(second);
        let successor = handle
            .execute(Command::buy_auto_clipper(CommandId::new(503).unwrap()))
            .await
            .unwrap();
        assert_eq!(successor.result, Ok(()));
        assert_eq!(handle.view().game.pro.funds.to_string(), "13.9");
        assert_eq!(handle.view().game.pro.auto_clippers.to_string(), "2");
        assert_eq!(handle.view().game.pro.auto_clipper_cost.to_string(), "6.21");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn concurrent_wire_purchases_share_one_funds_balance_atomically() {
        let mut state = GameState::fresh(GameRng::from_test_seed([91u8; 32]));
        state.pro.funds = Amount::parse("20").unwrap();
        let (runtime, handle, _clock) = test_runtime_with_state(state);
        let before = handle.view().game.clone();
        let (first, second) = tokio::join!(
            handle.execute(Command::buy_wire(CommandId::new(10_001).unwrap())),
            handle.execute(Command::buy_wire(CommandId::new(10_002).unwrap()))
        );
        let receipts = [first.unwrap(), second.unwrap()];
        assert_eq!(receipts.iter().filter(|r| r.result == Ok(())).count(), 1);
        assert_eq!(
            receipts
                .iter()
                .filter(
                    |r| r.result == Err(CommandRejection::Economy(EconomyError::InsufficientFunds))
                )
                .count(),
            1
        );
        let winner = receipts.iter().find(|r| r.result == Ok(())).unwrap();
        let loser = receipts.iter().find(|r| r.result.is_err()).unwrap();
        let view = handle.view();
        assert_eq!(view.game.pro.funds, Amount::zero());
        assert_eq!(view.game.pro.wire.to_string(), "2000");
        assert_eq!(view.game.pro.wire_quote.to_string(), "20");
        assert_eq!(view.game.pro.wire_base_price.to_string(), "20.05");
        assert_eq!(view.game.pro.wire_purchase_count.get(), 1);
        assert_eq!(view.game.pro.wire_price_counter.get(), 0);
        assert_eq!(view.game.pro.wire_inactivity_ticks.get(), 0);
        assert_eq!(view.game.pro.demand, before.pro.demand);
        assert_eq!(view.game.clock, before.clock);
        assert_eq!(view.game.rng_state_hex(), before.rng_state_hex());
        assert_eq!(view.revision, 1);
        for receipt in &receipts {
            assert_eq!(receipt.revision, winner.revision.min(loser.revision));
        }
        runtime.shutdown().await.unwrap();
        eprintln!(
            "one-Funds concurrent Wire purchases: one applied, one typed insufficient_funds; one spool, one $20 charge and $.05 base increment"
        );
    }

    #[tokio::test]
    async fn concurrent_business_families_are_serial_and_rejection_does_not_replace_state() {
        let mut state = GameState::fresh(GameRng::from_test_seed([92u8; 32]));
        state.pro.funds = Amount::parse("1000").unwrap();
        let (runtime, handle, _clock) = test_runtime_with_state(state);
        let (wire, marketing) = tokio::join!(
            handle.execute(Command::buy_wire(CommandId::new(10_010).unwrap())),
            handle.execute(Command::buy_marketing(CommandId::new(10_011).unwrap()))
        );
        assert_eq!(wire.unwrap().result, Ok(()));
        assert_eq!(marketing.unwrap().result, Ok(()));
        let view = handle.view();
        assert_eq!(view.game.pro.funds.to_string(), "880");
        assert_eq!(view.game.pro.wire.to_string(), "2000");
        assert_eq!(view.game.pro.wire_base_price.to_string(), "20.05");
        assert_eq!(view.game.pro.marketing_level.to_string(), "2");
        assert_eq!(view.game.pro.marketing_cost().unwrap().to_string(), "200");
        assert_eq!(view.game.pro.demand.to_string(), "3.52");
        assert_eq!(view.revision, 2);
        runtime.shutdown().await.unwrap();

        let mut state = GameState::fresh(GameRng::from_test_seed([93u8; 32]));
        state.pro.price_per_clip = Amount::parse("0.02").unwrap();
        refresh_demand(&mut state.pro).unwrap();
        let (runtime, handle, _clock) = test_runtime_with_state(state);
        let (_, _) = tokio::join!(
            handle.execute(Command::lower_price(CommandId::new(10_020).unwrap())),
            handle.execute(Command::lower_price(CommandId::new(10_021).unwrap()))
        );
        let floor = handle.view();
        assert_eq!(floor.game.pro.price_per_clip.to_string(), "0.01");
        assert_eq!(floor.game.pro.demand.to_string(), "80");
        assert_eq!(floor.revision, 1);
        let retry = handle
            .execute(Command::lower_price(CommandId::new(10_022).unwrap()))
            .await
            .unwrap();
        assert_eq!(
            retry.result,
            Err(CommandRejection::Economy(EconomyError::PriceAtMinimum))
        );
        assert_eq!(retry.revision, floor.revision);
        assert_eq!(handle.view().game.pro, floor.game.pro);
        runtime.shutdown().await.unwrap();
        eprintln!(
            "legal concurrent Wire + Marketing charges total $120; successive lower-price commands reach $.01 exactly and return price_at_minimum without mutation"
        );
    }

    #[tokio::test]
    async fn product_sales_preserve_large_exact_quantities_and_decision_cutoff_is_atomic() {
        let mut accepted = GameState::fresh(GameRng::from_test_seed([94u8; 32]));
        let stock = NonNegativeAmount::from_i128(1_125_899_906_842_624).unwrap();
        accepted.pro.lifetime_clips = stock.clone();
        accepted.pro.unsold_clips = stock.clone();
        accepted.pro.unused_clips = stock;
        accepted.pro.demand_boost = Amount::parse("3125000000000").unwrap();
        refresh_demand(&mut accepted.pro).unwrap();
        let (runtime, handle, clock) = test_runtime_with_state(accepted);
        clock.advance(Duration::from_millis(100));
        let view = wait_for(&handle, |view| view.game.clock.update_count() >= 10).await;
        assert_eq!(view.game.pro.demand.to_string(), "10000000000000");
        let expected = sale_request(&demand_ratio(&view.game.pro).unwrap()).unwrap();
        assert!(expected > 0 && expected < DECISION_LIMIT as u64);
        assert_eq!(
            view.game.pro.clips_sold,
            NonNegativeAmount::from_i128(i128::from(expected)).unwrap()
        );
        assert!(view.game.pro.funds > Amount::zero());
        assert!(view.game.pro.income > Amount::zero());
        let expected_revenue = Amount::quantize_ratio(
            &(num_bigint::BigInt::from(expected) * 25u8),
            &num_bigint::BigInt::from(100u8),
        )
        .unwrap();
        assert_eq!(view.game.pro.funds, expected_revenue);
        assert_eq!(view.game.pro.income, expected_revenue);
        assert_eq!(view.game.pro.last_sale_revenue, expected_revenue);
        eprintln!(
            "large full-product sale: D=10000000000000, request={expected}, sold={}, funds={}, income={}, all exact decimal Amount strings",
            view.game.pro.clips_sold, view.game.pro.funds, view.game.pro.income
        );
        runtime.shutdown().await.unwrap();

        let mut rejected = GameState::fresh(GameRng::from_test_seed([95u8; 32]));
        rejected.pro.demand_boost = Amount::parse("351562500000000").unwrap();
        refresh_demand(&mut rejected.pro).unwrap();
        let (runtime, handle, clock) = test_runtime_with_state(rejected);
        let before = handle.view();
        clock.advance(Duration::from_millis(100));
        let result = timeout(Duration::from_secs(3), runtime.wait_for_writer())
            .await
            .expect(
                "bounded numeric rejection terminates the writer without shutdown winning the race",
            );
        assert!(matches!(
            result,
            Err(RuntimeShutdownError::Writer(RuntimeFailure::Economy(
                EconomyError::Evaluator(
                    crate::game::evaluator::EvaluatorError::OutsideDecisionDomain
                )
            )))
        ));
        let after = handle.view();
        assert_eq!(after.game.pro, before.game.pro);
        assert_eq!(after.game.clock, before.game.clock);
        assert_eq!(after.game.rng_state_hex(), before.game.rng_state_hex());
        assert_eq!(after.revision, before.revision);
        eprintln!(
            "full-product decision cutoff: sale request >= 2^50 returns typed evaluator failure; no partial state, clock or RNG commit"
        );
    }
    #[tokio::test]
    async fn concurrent_retries_share_the_first_terminal_result() {
        let (runtime, handle, clock) = test_runtime_with_wire("1");
        let (a, b) = tokio::join!(handle.execute(command(44)), handle.execute(command(44)));
        assert_eq!(a.unwrap(), b.unwrap());
        assert_eq!(handle.view().game.pro.lifetime_clips.to_string(), "1");
        assert_eq!(handle.view().revision, 1);
        assert_eq!(handle.view().process.retry_hits, 1);
        clock.advance(Duration::from_millis(10));
        wait_for(&handle, |view| view.game.clock.update_count() == 1).await;
        let after_tick = handle.execute(command(44)).await.unwrap();
        assert_eq!(after_tick.revision, 1);
        assert_eq!(handle.view().revision, 2);
        assert_eq!(handle.view().game.pro.lifetime_clips.to_string(), "1");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn negative_table_bounded_queue_and_graceful_drain_have_explicit_results() {
        let (runtime, handle, _clock) = test_runtime();
        let before = handle.view().game.clone();
        let mut pending = Vec::new();
        for id in 0..COMMAND_QUEUE_CAPACITY {
            pending.push(handle.try_submit(command(id as u64)).unwrap());
        }
        assert!(matches!(
            handle.try_submit(command(999)),
            Err(SubmitError::QueueFull)
        ));
        runtime.shutdown().await.unwrap();
        for (index, item) in pending.into_iter().enumerate() {
            let receipt = item.wait().await.expect("accepted command drains");
            assert_eq!(receipt.revision, index as u64 + 1);
            assert_eq!(receipt.result, Ok(()));
        }
        assert_eq!(
            handle.execute(command(1_000)).await,
            Err(SubmitError::RuntimeClosed)
        );
        let view = handle.view();
        assert_eq!(view.revision, COMMAND_QUEUE_CAPACITY as u64);
        assert_eq!(view.game.pro.wire.to_string(), "936");
        assert_eq!(view.game.pro.lifetime_clips.to_string(), "64");
        assert_eq!(view.game.pro.unsold_clips.to_string(), "64");
        assert_eq!(view.game.pro.unused_clips.to_string(), "64");
        assert_eq!(view.game.clock, before.clock);
        assert_eq!(view.game.rng_state_hex(), before.rng_state_hex());
        eprintln!("full queue/closed runtime: pre-close commands drain; later commands are closed");
    }

    #[tokio::test]
    async fn graceful_shutdown_drains_local_pending_and_more_than_one_batch() {
        let state = GameState::fresh(GameRng::from_test_seed([17u8; 32]));
        let clock = Arc::new(FakeClock::new());
        let gate = Arc::new(CommandTestGate::default());
        let mut runtime =
            GameRuntime::start_with_test_gate(clock, state, Arc::clone(&gate)).unwrap();
        let handle = runtime.handle();
        let pending: Vec<_> = (0..21)
            .map(|id| handle.try_submit(command(id)).unwrap())
            .collect();
        timeout(Duration::from_secs(3), gate.wait_entered(1))
            .await
            .expect("first accepted command is local writer pending");

        runtime.request_shutdown();
        gate.release();
        for (index, item) in pending.into_iter().enumerate() {
            let receipt = item
                .wait()
                .await
                .expect("every accepted receipt survives shutdown");
            assert_eq!(receipt.result, Ok(()));
            assert_eq!(receipt.revision, index as u64 + 1);
        }
        let view = wait_for(&handle, |view| view.revision == 21).await;
        runtime.wait_for_writer().await.unwrap();
        assert_eq!(view.game.pro.wire.to_string(), "979");
        assert_eq!(view.game.pro.lifetime_clips.to_string(), "21");
        assert_eq!(view.game.pro.unsold_clips.to_string(), "21");
        assert_eq!(view.game.pro.unused_clips.to_string(), "21");
        assert_eq!(view.process.applied_commands, 21);
        assert!(view.process.command_batches >= 2);
        assert_eq!(view.process.max_commands_in_turn, MAX_COMMANDS_PER_TURN);
        assert_eq!(
            handle.execute(command(100)).await,
            Err(SubmitError::RuntimeClosed)
        );
    }

    #[tokio::test]
    async fn generated_command_tick_interleavings_match_a_serial_reference() {
        let (runtime, handle, clock) = test_runtime_with_wire("24");
        let mut seed = 0x9e37_79b9u32;
        let mut ticks = 0u64;
        let mut successes = 0u64;
        for id in 0..96u64 {
            seed = seed.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
            if seed.is_multiple_of(3) {
                clock.advance(Duration::from_millis(10));
                ticks += 1;
                wait_for(&handle, |view| view.game.clock.update_count() == ticks).await;
            } else {
                let receipt = handle.execute(command(id)).await.unwrap();
                if receipt.result == Ok(()) {
                    successes += 1;
                }
                assert_eq!(receipt.revision, ticks + successes);
            }
        }
        let view = handle.view();
        assert_eq!(view.game.clock.update_count(), ticks);
        assert_eq!(
            view.game.pro.lifetime_clips,
            Amount::from_i128(i128::from(successes))
                .nonnegative()
                .unwrap()
        );
        assert_eq!(view.game.pro.unsold_clips, view.game.pro.lifetime_clips);
        assert_eq!(view.game.pro.unused_clips, view.game.pro.lifetime_clips);
        assert_eq!(view.game.pro.wire.to_string(), (24 - successes).to_string());
        assert_eq!(view.revision, ticks + successes);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn ordinary_30004ms_drives_real_writer_dispatch_without_client_commands() {
        let (runtime, handle, clock) = test_runtime();
        let initial_rng = handle.view().game.rng_state_hex();
        clock.advance(Duration::new(30, 4_000_000));
        let view = wait_for(&handle, |view| view.game.clock.update_count() == 3_000).await;
        assert_eq!(view.revision, 3_000);
        assert_eq!(view.process.lag_debt_nanos, 4_000_000);
        assert!(view.process.full_lag_batches >= 299);
        assert_eq!(view.process.max_updates_in_turn, MAX_UPDATES_PER_TURN);
        assert_eq!(view.game.clock.fast_phase(), 0);
        assert_eq!(view.game.clock.second_phase(), 0);
        assert_eq!(view.game.clock.slow_phase(), 0);
        assert_eq!(view.game.clock.combat_pulses(), 1_875);
        assert_eq!(view.game.clock.combat_remainder_nanos(), 0);
        // Empty production preserves every non-economy ledger. The seeded Wire
        // stream and inactivity counters nevertheless advance exactly 300 times.
        assert_eq!(view.game.pro.lifetime_clips, NonNegativeAmount::zero());
        assert_eq!(view.game.pro.unsold_clips, NonNegativeAmount::zero());
        assert_eq!(view.game.pro.unused_clips, NonNegativeAmount::zero());
        assert_eq!(view.game.pro.clips_sold, NonNegativeAmount::zero());
        assert_eq!(
            view.game.pro.wire,
            NonNegativeAmount::from_i128(1000).unwrap()
        );
        assert_eq!(view.game.pro.funds, Amount::zero());
        assert_eq!(
            view.game.pro.wire_base_price,
            Amount::parse("19.98").unwrap()
        );
        assert_eq!(view.game.pro.wire_inactivity_ticks.get(), 49);
        assert_ne!(view.game.pro.wire_price_counter.get(), 0);
        assert_ne!(view.game.rng_state_hex(), initial_rng);
        assert!(view.process.degraded);
        assert!(view.process.overload_turns > 0);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn lag_batches_and_command_flood_receive_bounded_fair_service() {
        let (runtime, handle, clock) = test_runtime();
        let mut pending = Vec::new();
        for id in 0..48u64 {
            pending.push(handle.try_submit(command(id)).unwrap());
        }
        clock.advance(Duration::from_millis(250));
        for item in pending {
            assert_eq!(item.wait().await.unwrap().result, Ok(()));
        }
        let view = wait_for(&handle, |view| {
            view.game.clock.update_count() == 25 && view.process.applied_commands == 48
        })
        .await;
        assert_eq!(view.revision, 73);
        assert_eq!(view.process.lag_debt_nanos, 0);
        assert!(view.process.full_lag_batches >= 2);
        assert!(view.process.command_batches >= 3);
        assert_eq!(view.process.max_updates_in_turn, 10);
        assert_eq!(view.process.max_commands_in_turn, MAX_COMMANDS_PER_TURN);
        assert_eq!(view.game.pro.wire.to_string(), "952");
        assert_eq!(view.game.pro.lifetime_clips.to_string(), "48");
        assert_eq!(view.game.pro.unsold_clips.to_string(), "48");
        assert_eq!(view.game.pro.unused_clips.to_string(), "48");
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn discontinuity_bound_checks_both_sides_and_never_backfills() {
        let (runtime, handle, clock) = test_runtime();
        clock.advance(HOST_DISCONTINUITY - Duration::from_nanos(1));
        let view = wait_for(&handle, |view| view.game.clock.update_count() == 5_999).await;
        assert_eq!(view.process.lag_debt_nanos, 9_999_999);
        assert_eq!(view.process.discontinuity_events, 0);
        runtime.shutdown().await.unwrap();

        for gap in [
            HOST_DISCONTINUITY,
            HOST_DISCONTINUITY + Duration::from_nanos(1),
        ] {
            let (runtime, handle, clock) = test_runtime();
            clock.advance(gap);
            let view = wait_for(&handle, |view| view.process.discontinuity_events == 1).await;
            assert_eq!(view.game.clock.update_count(), 0);
            assert_eq!(view.revision, 0);
            assert_eq!(view.process.lag_debt_nanos, 0);
            assert!(view.process.degraded);
            assert_eq!(view.game.pro, ProState::fresh());
            runtime.shutdown().await.unwrap();
        }
    }

    #[tokio::test]
    async fn nonmonotonic_input_rebases_with_checked_duration_and_no_catchup() {
        let (runtime, handle, clock) = test_runtime();
        clock.advance(Duration::from_millis(20));
        wait_for(&handle, |view| view.game.clock.update_count() == 2).await;
        clock.set_elapsed(Duration::from_millis(5));
        let view = wait_for(&handle, |view| view.process.nonmonotonic_events == 1).await;
        assert_eq!(view.game.clock.update_count(), 2);
        assert_eq!(view.revision, 2);
        assert_eq!(view.process.lag_debt_nanos, 0);
        assert!(view.process.degraded);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn restart_begins_with_zero_process_debt_and_views_do_not_draw_rng() {
        let (runtime, handle, clock) = test_runtime();
        let initial_run = handle.view().run_id.clone();
        let initial_rng = handle.view().game.rng_state_hex();
        for _ in 0..4 {
            assert_eq!(handle.view().game.rng_state_hex(), initial_rng);
        }
        assert_eq!(handle.execute(command(77)).await.unwrap().result, Ok(()));
        clock.advance(Duration::from_millis(30));
        let before = wait_for(&handle, |view| view.game.clock.update_count() == 3).await;
        assert_eq!(before.game.rng_state_hex(), initial_rng);
        let snapshot = before.game.clone();
        runtime.shutdown().await.unwrap();

        let (runtime, handle, _clock) = test_runtime_with_state(snapshot);
        let restarted = handle.view();
        assert_eq!(restarted.process.lag_debt_nanos, 0);
        assert_eq!(restarted.revision, 0);
        assert_eq!(restarted.game.clock.update_count(), 3);
        assert_eq!(restarted.game.rng_state_hex(), initial_rng);
        assert_ne!(restarted.run_id, initial_run);
        // Process retry records are not part of the logical snapshot.
        assert_eq!(handle.execute(command(77)).await.unwrap().result, Ok(()));
        assert_eq!(handle.view().game.pro.lifetime_clips.to_string(), "2");
        assert_eq!(handle.view().revision, 1);
        runtime.shutdown().await.unwrap();
    }
}
