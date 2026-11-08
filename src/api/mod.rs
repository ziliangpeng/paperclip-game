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

pub fn router(runtime: RuntimeHandle) -> Router {
    Router::new()
        .route("/api/game/view", get(get_view))
        .route("/api/game/commands", post(commands::post_command))
        .layer(DefaultBodyLimit::max(MAX_COMMAND_BODY_BYTES))
        .with_state(ApiState::new(runtime))
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

/// Serve one process-lifetime runtime until shutdown, then stop its writer.
/// No database or snapshot I/O occurs here; persistence belongs to Issue #10.
pub async fn serve<F>(
    listener: TcpListener,
    runtime: GameRuntime,
    shutdown: F,
) -> Result<(), ServerError>
where
    F: Future<Output = ()> + Send + 'static,
{
    let serving = axum::serve(listener, router(runtime.handle()))
        .with_graceful_shutdown(shutdown)
        .await;
    let stopped = runtime.shutdown().await;
    match (serving, stopped) {
        (Ok(()), Ok(())) => Ok(()),
        (Err(error), _) => Err(ServerError::Http(error)),
        (Ok(()), Err(error)) => Err(ServerError::Runtime(error)),
    }
}

#[derive(Debug)]
pub enum ServerError {
    Http(io::Error),
    Runtime(RuntimeShutdownError),
}

impl fmt::Display for ServerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(_) => formatter.write_str("HTTP listener failed"),
            Self::Runtime(_) => formatter.write_str("game runtime shutdown failed"),
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
