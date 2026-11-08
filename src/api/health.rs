//! Read-only persistence liveness/readiness, independent of game mutation.

use super::view::HealthView;
use super::{ApiState, response};
use axum::Json;
use axum::body::Body;
use axum::extract::State;
use axum::http::{Response, StatusCode};
use serde::Serialize;

#[derive(Serialize)]
pub(super) struct LiveResponse {
    status: &'static str,
}

pub(super) async fn live() -> Json<LiveResponse> {
    Json(LiveResponse { status: "ok" })
}

pub(super) async fn ready(State(state): State<ApiState>) -> Response<Body> {
    match HealthView::try_from(state.health.snapshot()) {
        Ok(health) => {
            let status = if health.ready {
                StatusCode::OK
            } else {
                StatusCode::SERVICE_UNAVAILABLE
            };
            response(status, health)
        }
        Err(_) => response(
            StatusCode::INTERNAL_SERVER_ERROR,
            super::ErrorPayload {
                status: "health_unavailable",
            },
        ),
    }
}
