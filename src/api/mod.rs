//! Axum transport for the authoritative runtime.

mod commands;
mod view;

use crate::runtime::{GameRuntime, RuntimeHandle, RuntimeShutdownError};
use axum::Router;
use axum::body::Body;
use axum::extract::{DefaultBodyLimit, State};
use axum::http::{Response, StatusCode, header};
use axum::response::IntoResponse;
use axum::routing::{get, post};
use commands::RetryCoordinator;
use serde::Serialize;
use std::error::Error;
use std::fmt;
use std::future::Future;
use std::io;
use std::net::SocketAddr;
use tokio::net::TcpListener;

pub use commands::{MAX_COMMAND_BODY_BYTES, MAX_COMMAND_ID_BYTES};
pub use view::GameView;

#[derive(Clone)]
pub(crate) struct ApiState {
    runtime: RuntimeHandle,
    retry: RetryCoordinator,
}

impl ApiState {
    fn new(runtime: RuntimeHandle) -> Self {
        Self {
            runtime,
            retry: RetryCoordinator::default(),
        }
    }
}

fn router_with_state(state: ApiState) -> Router {
    Router::new()
        .route("/api/game/view", get(get_view))
        .route("/api/game/commands", post(commands::post_command))
        .layer(DefaultBodyLimit::max(MAX_COMMAND_BODY_BYTES))
        .with_state(state)
}

pub fn router(runtime: RuntimeHandle) -> Router {
    router_with_state(ApiState::new(runtime))
}

async fn get_view(State(state): State<ApiState>) -> Response<Body> {
    match GameView::from_runtime(&state.runtime.view()) {
        Ok(view) => axum::Json(view).into_response(),
        Err(_) => response(
            StatusCode::INTERNAL_SERVER_ERROR,
            ErrorPayload {
                status: "view_unavailable",
            },
        ),
    }
}

#[derive(Serialize)]
struct ErrorPayload {
    status: &'static str,
}

fn response(status: StatusCode, payload: impl Serialize) -> Response<Body> {
    let body = serde_json::to_vec(&payload).expect("static error response serializes");
    Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from(body))
        .expect("static response headers are valid")
}

#[cfg(not(test))]
type ShutdownTestSignal = ();
#[cfg(test)]
type ShutdownTestSignal = Option<tokio::sync::oneshot::Sender<()>>;

/// Serve one shared state through the complete production lifecycle.
/// Accepted writer/publication work is drained during graceful stop; this is
/// not crash persistence and performs no database or snapshot I/O.
pub async fn serve<F>(
    listener: TcpListener,
    runtime: GameRuntime,
    shutdown: F,
) -> Result<(), ServerError>
where
    F: Future<Output = ()> + Send + 'static,
{
    let state = ApiState::new(runtime.handle());
    #[cfg(not(test))]
    {
        serve_with_state(listener, runtime, state, shutdown, ()).await
    }
    #[cfg(test)]
    {
        serve_with_state(listener, runtime, state, shutdown, None).await
    }
}

async fn serve_with_state<F>(
    listener: TcpListener,
    mut runtime: GameRuntime,
    state: ApiState,
    shutdown: F,
    _shutdown_test_signal: ShutdownTestSignal,
) -> Result<(), ServerError>
where
    F: Future<Output = ()> + Send + 'static,
{
    let serving = axum::serve(listener, router_with_state(state.clone()))
        .with_graceful_shutdown(shutdown)
        .await;
    runtime.request_shutdown();
    #[cfg(test)]
    if let Some(signal) = _shutdown_test_signal {
        let _ = signal.send(());
    }
    let stopped = runtime.wait_for_writer().await;
    let published = state.retry.join_accepted().await;
    match (serving, stopped, published) {
        (Err(error), _, _) => Err(ServerError::Http(error)),
        (_, Err(error), _) => Err(ServerError::Runtime(error)),
        (_, _, Err(_)) => Err(ServerError::AcceptedPublicationFailed),
        (Ok(()), Ok(()), Ok(())) => Ok(()),
    }
}

#[derive(Debug)]
pub enum ServerError {
    Http(io::Error),
    Runtime(RuntimeShutdownError),
    AcceptedPublicationFailed,
}

impl fmt::Display for ServerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(_) => formatter.write_str("HTTP listener failed"),
            Self::Runtime(_) => formatter.write_str("game runtime shutdown failed"),
            Self::AcceptedPublicationFailed => {
                formatter.write_str("accepted command publication failed")
            }
        }
    }
}

impl Error for ServerError {}

/// Numeric startup diagnostics expose only the actual bound numeric address.
pub fn startup_message(local_addr: SocketAddr) -> String {
    format!("paperclip-game: listening on http://{local_addr}")
}

#[cfg(test)]
mod tests;
