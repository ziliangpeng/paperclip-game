//! One authoritative writer for logical updates and closed player intents.

use crate::game::amount::{BoundedIntegerError, MAX_SAFE_JSON_INTEGER};
use crate::game::clock::{ClockError, UPDATE_QUANTUM_NANOS};
use crate::game::conversion::{ConversionError, convert_one_wire};
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

#[derive(Clone, Debug, Eq, PartialEq)]
enum Intent {
    MakePaperclip,
}

impl Command {
    /// The sole M1 player intent: exactly one Wire, with no amount argument.
    pub fn make_paperclip(id: CommandId) -> Self {
        Self {
            id,
            intent: Intent::MakePaperclip,
        }
    }

    pub fn id(&self) -> CommandId {
        self.id
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CommandRejection {
    Conversion(ConversionError),
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

    pub fn handle(&self) -> RuntimeHandle {
        self.handle.clone()
    }

    fn start_with_clock<C>(clock: C, state: GameState) -> Result<Self, RuntimeStartError>
    where
        C: MonotonicClock,
    {
        let runtime =
            tokio::runtime::Handle::try_current().map_err(|_| RuntimeStartError::NoRuntime)?;
        let run_id = fresh_run_id().map_err(RuntimeStartError::Entropy)?;
        let writer = Writer::new(clock, state, run_id);
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

    pub async fn shutdown(mut self) -> Result<(), RuntimeShutdownError> {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
        let writer = self.writer.take().expect("shutdown consumes a live writer");
        match writer.await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => Err(RuntimeShutdownError::Writer(error)),
            Err(_) => Err(RuntimeShutdownError::WriterTaskEnded),
        }
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
    Entropy(getrandom::Error),
}

impl fmt::Display for RuntimeStartError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NoRuntime => formatter.write_str("GameRuntime must start inside a Tokio runtime"),
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
}

impl fmt::Display for RuntimeFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::CounterLimit => formatter.write_str("checked runtime counter limit reached"),
            Self::LogicalClock(_) => formatter.write_str("checked logical clock limit reached"),
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

trait MonotonicClock: Send + Sync + 'static {
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
    state: GameState,
    revision: u64,
    run_id: String,
    retries: HashMap<CommandId, RetryRecord>,
    status: ProcessStatus,
    last_observation: Instant,
    lag_debt_nanos: u128,
}

impl<C: MonotonicClock> Writer<C> {
    fn new(clock: C, state: GameState, run_id: String) -> Self {
        let last_observation = clock.now();
        Self {
            clock,
            state,
            revision: 0,
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
        self.state
            .clock
            .advance()
            .map_err(RuntimeFailure::LogicalClock)?;
        self.revision = next_revision;
        self.lag_debt_nanos -= UPDATE_QUANTUM_NANOS;
        Ok(())
    }

    fn execute_new(&mut self, command: Command) -> Result<CommandReceipt, RuntimeFailure> {
        let next_revision = next_revision(self.revision)?;
        let outcome = match command.intent {
            Intent::MakePaperclip => convert_one_wire(&mut self.state.pro),
        };
        let result = match outcome {
            Ok(_) => {
                self.revision = next_revision;
                increment(&mut self.status.applied_commands)?;
                Ok(())
            }
            Err(error) => {
                increment(&mut self.status.rejected_commands)?;
                Err(CommandRejection::Conversion(error))
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

    fn turn(
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
    loop {
        match shutdown.try_recv() {
            Ok(()) | Err(oneshot::error::TryRecvError::Closed) => break,
            Err(oneshot::error::TryRecvError::Empty) => {}
        }
        writer.turn(&mut receiver, &mut pending)?;
        let _ = views.send(writer.view());

        if writer.lag_debt_nanos >= UPDATE_QUANTUM_NANOS || pending.is_some() {
            continue;
        }
        let remaining = UPDATE_QUANTUM_NANOS - writer.lag_debt_nanos;
        let deadline = writer.last_observation + Duration::from_nanos(remaining as u64);
        tokio::select! {
            biased;
            _ = &mut shutdown => break,
            received = receiver.recv() => {
                match received {
                    Some(command) => pending = Some(command),
                    None => break,
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
    use crate::game::amount::Amount;
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

    #[tokio::test]
    async fn manual_command_is_conserved_and_below_one_rejection_is_atomic() {
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
        let before = handle.view().game.pro.clone();
        let receipt = handle.execute(command(2)).await.unwrap();
        assert_eq!(receipt.revision, 0);
        assert_eq!(
            receipt.result,
            Err(CommandRejection::Conversion(
                ConversionError::InsufficientWire
            ))
        );
        assert_eq!(handle.view().game.pro, before);
        assert_eq!(handle.view().revision, 0);
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
        let rejected = handle.execute(command(5)).await.unwrap();
        assert!(rejected.result.is_err());
        assert_eq!(handle.view().revision, 1);
        runtime.shutdown().await.unwrap();
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
    async fn bounded_queue_and_cancellation_have_explicit_results() {
        let (runtime, handle, _clock) = test_runtime();
        let mut pending = Vec::new();
        for id in 0..COMMAND_QUEUE_CAPACITY {
            pending.push(handle.try_submit(command(id as u64)).unwrap());
        }
        assert!(matches!(
            handle.try_submit(command(999)),
            Err(SubmitError::QueueFull)
        ));
        runtime.shutdown().await.unwrap();
        for item in pending {
            assert_eq!(item.wait().await, Err(SubmitError::RuntimeClosed));
        }
        assert_eq!(
            handle.execute(command(1_000)).await,
            Err(SubmitError::RuntimeClosed)
        );
        assert_eq!(handle.view().revision, 0);
        assert_eq!(handle.view().game.pro.wire.to_string(), "1000");
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
        assert_eq!(view.game.pro, ProState::fresh());
        assert_eq!(view.game.rng_state_hex(), initial_rng);
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
