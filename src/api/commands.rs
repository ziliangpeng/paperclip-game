//! Strict command transport and process-lifetime retry coordination.

use crate::game::conversion::ConversionError;
use crate::game::economy::EconomyError;
use crate::game::evaluator::EvaluatorError;
use crate::runtime::{
    Command, CommandId, CommandRejection, PendingCommand, RuntimeHandle, SubmitError,
};
use axum::body::{Body, Bytes};
use axum::extract::State;
use axum::extract::rejection::BytesRejection;
use axum::http::{Response, StatusCode, header};
use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::fmt;
use std::sync::{Arc, Mutex};
use tokio::sync::watch;
use tokio::task::JoinSet;

/// Corruption/allocation guards, not gameplay-value limits.
pub const MAX_COMMAND_BODY_BYTES: usize = 4 * 1024;
pub const MAX_COMMAND_ID_BYTES: usize = 128;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct StoredResponse {
    status: StatusCode,
    body: Arc<Vec<u8>>,
}

impl StoredResponse {
    fn new(status: StatusCode, payload: ResponsePayload) -> Self {
        let body = serde_json::to_vec(&payload)
            .expect("a static API response with bounded integers must serialize");
        Self {
            status,
            body: Arc::new(body),
        }
    }

    fn into_http(self) -> Response<Body> {
        Response::builder()
            .status(self.status)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(self.body.as_ref().clone()))
            .expect("static API response headers are valid")
    }
}

#[derive(Serialize)]
#[serde(tag = "status", rename_all = "snake_case")]
enum ResponsePayload {
    Applied { revision: u64 },
    RuleRejected { revision: u64, reason: &'static str },
    UnknownCommand,
    Conflict,
    SchemaError { reason: &'static str },
    Unavailable { reason: &'static str },
}

fn schema_error(reason: &'static str) -> StoredResponse {
    StoredResponse::new(
        StatusCode::BAD_REQUEST,
        ResponsePayload::SchemaError { reason },
    )
}

fn unavailable(reason: &'static str) -> StoredResponse {
    StoredResponse::new(
        StatusCode::SERVICE_UNAVAILABLE,
        ResponsePayload::Unavailable { reason },
    )
}

fn submit_error(error: SubmitError) -> StoredResponse {
    match error {
        SubmitError::QueueFull => unavailable("queue_full"),
        SubmitError::RuntimeClosed => unavailable("runtime_closed"),
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum NormalizedPayload {
    MakePaperclip,
    BuyWire,
    LowerPrice,
    RaisePrice,
    BuyMarketing,
    BuyAutoClipper,
    AddProcessor,
    AddMemory,
    // Unknown actions remain fully normalized for conflict checks, but can
    // never become an executable runtime intent.
    Unsupported {
        action_type: String,
        arguments: StrictValue,
    },
}

impl NormalizedPayload {
    fn runtime_command(&self, id: CommandId) -> Option<Command> {
        match self {
            Self::MakePaperclip => Some(Command::make_paperclip(id)),
            Self::BuyWire => Some(Command::buy_wire(id)),
            Self::LowerPrice => Some(Command::lower_price(id)),
            Self::RaisePrice => Some(Command::raise_price(id)),
            Self::BuyMarketing => Some(Command::buy_marketing(id)),
            Self::BuyAutoClipper => Some(Command::buy_auto_clipper(id)),
            Self::AddProcessor => Some(Command::add_processor(id)),
            Self::AddMemory => Some(Command::add_memory(id)),
            Self::Unsupported { .. } => None,
        }
    }
}

#[derive(Debug)]
struct NormalizedCommand {
    id: String,
    payload: NormalizedPayload,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CommandEnvelope {
    command_id: String,
    #[serde(rename = "type")]
    action_type: String,
    arguments: StrictValue,
}

fn decode_command(bytes: &[u8]) -> Result<NormalizedCommand, StoredResponse> {
    std::str::from_utf8(bytes).map_err(|_| schema_error("invalid_utf8"))?;
    let envelope: CommandEnvelope =
        serde_json::from_slice(bytes).map_err(|_| schema_error("invalid_command_structure"))?;
    if envelope.command_id.is_empty()
        || envelope.command_id.len() > MAX_COMMAND_ID_BYTES
        || envelope.command_id.chars().any(char::is_control)
    {
        return Err(schema_error("invalid_command_id"));
    }
    let StrictValue::Object(arguments) = &envelope.arguments else {
        return Err(schema_error("invalid_arguments"));
    };
    let payload = match envelope.action_type.as_str() {
        "make_paperclip" | "buy_wire" | "lower_price" | "raise_price" | "buy_marketing"
        | "buy_auto_clipper" | "add_processor" | "add_memory"
            if arguments.is_empty() =>
        {
            match envelope.action_type.as_str() {
                "make_paperclip" => NormalizedPayload::MakePaperclip,
                "buy_wire" => NormalizedPayload::BuyWire,
                "lower_price" => NormalizedPayload::LowerPrice,
                "raise_price" => NormalizedPayload::RaisePrice,
                "buy_marketing" => NormalizedPayload::BuyMarketing,
                "buy_auto_clipper" => NormalizedPayload::BuyAutoClipper,
                "add_processor" => NormalizedPayload::AddProcessor,
                "add_memory" => NormalizedPayload::AddMemory,
                _ => unreachable!(),
            }
        }
        "make_paperclip" | "buy_wire" | "lower_price" | "raise_price" | "buy_marketing"
        | "buy_auto_clipper" | "add_processor" | "add_memory" => {
            return Err(schema_error("invalid_arguments"));
        }
        _ => NormalizedPayload::Unsupported {
            action_type: envelope.action_type,
            arguments: envelope.arguments,
        },
    };
    Ok(NormalizedCommand {
        id: envelope.command_id,
        payload,
    })
}

/// A recursively duplicate-key-sensitive JSON value used only to normalize an
/// unsupported action for safe conflict handling. It never reaches game state.
#[derive(Clone, Debug, Eq, PartialEq)]
enum StrictValue {
    Null,
    Bool(bool),
    Number(StrictNumber),
    String(String),
    Array(Vec<Self>),
    Object(BTreeMap<String, Self>),
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum StrictNumber {
    Signed(i64),
    Unsigned(u64),
    // Separate from every Amount and executable integer control.
    Decimal(String),
}

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct StrictValueVisitor;

        impl<'de> Visitor<'de> for StrictValueVisitor {
            type Value = StrictValue;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a JSON value with unique object keys")
            }

            fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue::Bool(value))
            }

            fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue::Number(StrictNumber::Signed(value)))
            }

            fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictValue::Number(StrictNumber::Unsigned(value)))
            }

            fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                if !value.is_finite() {
                    return Err(E::custom("non-finite numbers are not JSON"));
                }
                let text = serde_json::to_string(&value).map_err(E::custom)?;
                Ok(StrictValue::Number(StrictNumber::Decimal(text)))
            }

            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue::String(value.to_owned()))
            }

            fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue::String(value))
            }

            fn visit_none<E>(self) -> Result<Self::Value, E> {
                Ok(StrictValue::Null)
            }

            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(StrictValue::Null)
            }

            fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
            where
                D: Deserializer<'de>,
            {
                Self::Value::deserialize(deserializer)
            }

            fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
            where
                A: serde::de::SeqAccess<'de>,
            {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(StrictValue::Array(values))
            }

            fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut values = BTreeMap::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate object key"));
                    }
                    let value = map.next_value()?;
                    values.insert(key, value);
                }
                Ok(StrictValue::Object(values))
            }
        }

        deserializer.deserialize_any(StrictValueVisitor)
    }
}

struct RetryEntry {
    payload: NormalizedPayload,
    completion: watch::Sender<Option<StoredResponse>>,
}

impl RetryEntry {
    fn new(payload: NormalizedPayload) -> Self {
        let (completion, _) = watch::channel(None);
        Self {
            payload,
            completion,
        }
    }

    fn complete(&self, response: StoredResponse) {
        // Exactly one accepted owner can publish this transition. Existing
        // entries are never rebound or overwritten by a later command.
        self.completion.send_replace(Some(response));
    }

    async fn wait(&self) -> StoredResponse {
        let mut completion = self.completion.subscribe();
        loop {
            if let Some(response) = completion.borrow_and_update().clone() {
                return response;
            }
            if completion.changed().await.is_err() {
                return unavailable("runtime_closed");
            }
        }
    }
}

#[derive(Default)]
struct RetryState {
    entries: HashMap<String, Arc<RetryEntry>>,
    next_internal_id: u64,
}

/// Public opaque keys are exact map keys. Internal numeric IDs are allocated
/// once, checked, and never formed by truncating a hash of client input.
#[derive(Clone)]
pub(crate) struct RetryCoordinator {
    state: Arc<Mutex<RetryState>>,
    accepted_tasks: Arc<Mutex<JoinSet<()>>>,
}

impl Default for RetryCoordinator {
    fn default() -> Self {
        Self {
            state: Arc::new(Mutex::new(RetryState::default())),
            accepted_tasks: Arc::new(Mutex::new(JoinSet::new())),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct CompletionFailure;

enum Registration {
    Existing(Arc<RetryEntry>),
    New {
        entry: Arc<RetryEntry>,
        pending: PendingCommand,
    },
    Unknown,
    Conflict,
    Unavailable(SubmitError),
}

impl RetryCoordinator {
    fn register(&self, command: NormalizedCommand, runtime: &RuntimeHandle) -> Registration {
        let mut state = self.state.lock().expect("retry registry lock");
        if let Some(entry) = state.entries.get(&command.id) {
            // A valid existing binding takes precedence over the unknown-action
            // result. This yields 409 without executing or accepting the new
            // payload. Structurally invalid JSON was rejected before this point.
            if entry.payload != command.payload {
                return Registration::Conflict;
            }
            return Registration::Existing(entry.clone());
        }
        if matches!(command.payload, NormalizedPayload::Unsupported { .. }) {
            return Registration::Unknown;
        }
        let Some(internal_id) = allocate_internal_id(&mut state) else {
            return Registration::Unavailable(SubmitError::RuntimeClosed);
        };
        let Some(runtime_command) = command.payload.runtime_command(internal_id) else {
            unreachable!("unsupported payloads returned before internal ID allocation");
        };
        let pending = match runtime.try_submit(runtime_command) {
            Ok(pending) => pending,
            Err(error) => return Registration::Unavailable(error),
        };
        let entry = Arc::new(RetryEntry::new(command.payload));
        state.entries.insert(command.id, Arc::clone(&entry));
        drop(state);
        Registration::New { entry, pending }
    }

    fn track_accepted(&self, entry: Arc<RetryEntry>, pending: PendingCommand) {
        // No await occurs between accepted registration and task ownership.
        // A caller disconnect therefore cannot detach this work from serving.
        self.accepted_tasks
            .lock()
            .expect("accepted task tracker lock")
            .spawn(complete_accepted(entry, pending));
    }

    pub(crate) async fn join_accepted(&self) -> Result<(), CompletionFailure> {
        // serve calls this only after Axum has finished all request handlers,
        // so no new accepted task can be registered concurrently. Move the set
        // out of its short synchronous lock before awaiting any task.
        let mut tasks = {
            let mut accepted = self
                .accepted_tasks
                .lock()
                .expect("accepted task tracker lock");
            std::mem::replace(&mut *accepted, JoinSet::new())
        };
        let mut failed = false;
        while let Some(result) = tasks.join_next().await {
            // Observe every task even after a failure so no accepted wait is
            // silently dropped. The caller maps this to a sanitized error.
            failed |= result.is_err();
        }
        if failed {
            Err(CompletionFailure)
        } else {
            Ok(())
        }
    }

    #[cfg(test)]
    pub(crate) fn registered_count(&self) -> usize {
        self.state
            .lock()
            .expect("retry registry lock")
            .entries
            .len()
    }

    #[cfg(test)]
    pub(crate) fn tracked_count(&self) -> usize {
        self.accepted_tasks
            .lock()
            .expect("accepted task tracker lock")
            .len()
    }

    #[cfg(test)]
    pub(crate) fn terminal_status_body(&self, id: &str) -> Option<(u16, Vec<u8>)> {
        let entry = self
            .state
            .lock()
            .expect("retry registry lock")
            .entries
            .get(id)?
            .clone();
        entry
            .completion
            .subscribe()
            .borrow()
            .clone()
            .map(|response| (response.status.as_u16(), response.body.as_ref().clone()))
    }
}

fn allocate_internal_id(state: &mut RetryState) -> Option<CommandId> {
    let id = CommandId::new(state.next_internal_id).ok()?;
    state.next_internal_id = state.next_internal_id.checked_add(1)?;
    Some(id)
}

async fn complete_accepted(entry: Arc<RetryEntry>, pending: PendingCommand) {
    let response = match pending.wait().await {
        Ok(receipt) => match receipt.result {
            Ok(()) => StoredResponse::new(
                StatusCode::OK,
                ResponsePayload::Applied {
                    revision: receipt.revision,
                },
            ),
            Err(rejection) => StoredResponse::new(
                StatusCode::UNPROCESSABLE_ENTITY,
                ResponsePayload::RuleRejected {
                    revision: receipt.revision,
                    reason: rejection_reason(rejection),
                },
            ),
        },
        Err(error) => submit_error(error),
    };
    entry.complete(response);
}

fn rejection_reason(rejection: CommandRejection) -> &'static str {
    match rejection {
        CommandRejection::Conversion(ConversionError::InsufficientWire) => "insufficient_wire",
        CommandRejection::Conversion(_) => "conversion_rejected",
        CommandRejection::Economy(EconomyError::InsufficientFunds) => "insufficient_funds",
        CommandRejection::Economy(EconomyError::PriceAtMinimum) => "price_at_minimum",
        CommandRejection::Economy(EconomyError::CounterLimit) => "counter_limit",
        CommandRejection::Economy(EconomyError::TrustCapacityFull) => "trust_capacity_full",
        CommandRejection::Economy(EconomyError::ComputationLocked) => "computation_locked",
        CommandRejection::Economy(EconomyError::ProcessorEvaluatorDomain) => {
            "processor_evaluator_domain"
        }
        CommandRejection::Economy(EconomyError::Evaluator(
            EvaluatorError::OutsideDecisionDomain,
        )) => "numeric_decision_domain",
        CommandRejection::Economy(EconomyError::Evaluator(_)) => "numeric_evaluation_rejected",
        CommandRejection::Economy(EconomyError::ExponentResourceLimit) => "resource_limit",
        CommandRejection::Economy(EconomyError::InvalidState) => "invalid_state",
        CommandRejection::ConflictingRetry => "conflicting_retry",
    }
}

pub(crate) async fn post_command(
    State(state): State<crate::api::ApiState>,
    body: Result<Bytes, BytesRejection>,
) -> Response<Body> {
    let body = match body {
        Ok(body) => body,
        Err(_) => {
            return StoredResponse::new(
                StatusCode::PAYLOAD_TOO_LARGE,
                ResponsePayload::SchemaError {
                    reason: "body_too_large",
                },
            )
            .into_http();
        }
    };
    let command = match decode_command(&body) {
        Ok(command) => command,
        Err(response) => return response.into_http(),
    };
    match state.retry.register(command, &state.runtime) {
        Registration::Unknown => {
            StoredResponse::new(StatusCode::NOT_FOUND, ResponsePayload::UnknownCommand).into_http()
        }
        Registration::Conflict => {
            StoredResponse::new(StatusCode::CONFLICT, ResponsePayload::Conflict).into_http()
        }
        Registration::Unavailable(error) => submit_error(error).into_http(),
        Registration::Existing(entry) => entry.wait().await.into_http(),
        Registration::New { entry, pending } => {
            // Submission to the bounded runtime queue has succeeded. Give the
            // accepted publication wait to the shared lifecycle tracker before
            // the first response await. Disconnect cannot cancel acceptance or
            // turn a retry into a second write.
            state.retry.track_accepted(Arc::clone(&entry), pending);
            entry.wait().await.into_http()
        }
    }
}

#[cfg(test)]
mod completion_lifetime_tests {
    use super::*;
    use crate::runtime::CommandReceipt;
    use tokio::sync::oneshot;
    use tokio::time::{Duration, timeout};

    #[tokio::test]
    async fn join_accepted_waits_for_terminal_publication_without_a_client_waiter() {
        let retry = RetryCoordinator::default();
        let entry = Arc::new(RetryEntry::new(NormalizedPayload::MakePaperclip));
        let (sender, receiver) = oneshot::channel();
        let pending = PendingCommand::from_test_receiver(receiver);
        retry.track_accepted(Arc::clone(&entry), pending);

        let joining = {
            let retry = retry.clone();
            tokio::spawn(async move { retry.join_accepted().await })
        };
        tokio::task::yield_now().await;
        assert!(
            !joining.is_finished(),
            "join must wait for the accepted task, not only an idle map"
        );
        assert!(entry.completion.subscribe().borrow().is_none());

        sender
            .send(CommandReceipt {
                revision: 7,
                result: Ok(()),
            })
            .expect("receipt responder remains available");
        timeout(Duration::from_secs(3), joining)
            .await
            .expect("bounded publication join")
            .expect("publication join task does not panic")
            .expect("no publication task failed");

        let first = entry.completion.subscribe().borrow().clone().unwrap();
        assert_eq!(first.status, StatusCode::OK);
        assert_eq!(
            first.body.as_ref(),
            b"{\"status\":\"applied\",\"revision\":7}"
        );
        let replay = entry.wait().await;
        assert_eq!(
            replay, first,
            "join leaves the immutable terminal replay intact"
        );
        assert_eq!(retry.tracked_count(), 0, "joined tasks are reaped");
    }
}
