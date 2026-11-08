//! Strict command transport and process-lifetime retry coordination.

use crate::game::conversion::ConversionError;
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
    let payload = if envelope.action_type == "make_paperclip" {
        if !arguments.is_empty() {
            return Err(schema_error("invalid_arguments"));
        }
        NormalizedPayload::MakePaperclip
    } else {
        NormalizedPayload::Unsupported {
            action_type: envelope.action_type,
            arguments: envelope.arguments,
        }
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
#[derive(Clone, Default)]
pub(crate) struct RetryCoordinator {
    state: Arc<Mutex<RetryState>>,
}

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
            // Submission to the bounded runtime queue has succeeded. Complete
            // the writer wait independently of this HTTP future so disconnect
            // cannot cancel acceptance or turn a retry into a second write.
            tokio::spawn(complete_accepted(Arc::clone(&entry), pending));
            entry.wait().await.into_http()
        }
    }
}
