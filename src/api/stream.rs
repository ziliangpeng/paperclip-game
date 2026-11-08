//! Full-view Server-Sent Events and the native browser synchronizer asset.

use super::{ApiState, ErrorPayload, response};
use crate::view_broadcast::PublishedView;
use axum::body::Body;
use axum::extract::State;
use axum::http::{HeaderValue, Response, StatusCode, header};
use axum::response::sse::Event;
use axum::response::{IntoResponse, Sse};
use std::convert::Infallible;
use tokio_stream::StreamExt;
use tokio_stream::wrappers::ReceiverStream;

pub(super) async fn get_stream(State(state): State<ApiState>) -> Response<Body> {
    let connection = match state.views.connect() {
        Ok(connection) => connection,
        Err(_) => {
            return response(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorPayload {
                    status: "view_unavailable",
                },
            );
        }
    };
    let updates = ReceiverStream::new(connection.updates);
    let guard = connection.guard;
    let stream = tokio_stream::once(connection.initial)
        .chain(updates)
        .map(move |view| {
            // Keeping the guard in this adapter ties observer accounting to the
            // actual HTTP stream lifetime, including early client disconnect.
            let _keep_connection = &guard;
            Ok::<Event, Infallible>(event(view))
        });
    let mut response = Sse::new(stream).into_response();
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-store, no-transform"),
    );
    response
}

fn event(view: PublishedView) -> Event {
    Event::default()
        .event("game_view")
        .id(view.event_id())
        .data(view.json.as_ref())
}

pub(super) async fn browser_synchronizer() -> Response<Body> {
    let mut response = include_str!("../../static/stream.js").into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/javascript; charset=utf-8"),
    );
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    response
}
