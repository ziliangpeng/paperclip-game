//! Compile-time, allowlisted native browser assets; no public filesystem root.

use axum::body::Body;
use axum::http::{HeaderValue, Response, header};

fn asset(body: &'static str, content_type: &'static str) -> Response<Body> {
    let mut response = Response::new(Body::from(body));
    response
        .headers_mut()
        .insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    response
}

fn javascript(source: &'static str) -> Response<Body> {
    asset(source, "text/javascript; charset=utf-8")
}

pub(super) async fn index() -> Response<Body> {
    asset(
        include_str!("../../static/index.html"),
        "text/html; charset=utf-8",
    )
}

pub(super) async fn styles() -> Response<Body> {
    asset(
        include_str!("../../static/styles.css"),
        "text/css; charset=utf-8",
    )
}

pub(super) async fn app() -> Response<Body> {
    javascript(include_str!("../../static/app.js"))
}

pub(super) async fn view_model() -> Response<Body> {
    javascript(include_str!("../../static/view-model.js"))
}

pub(super) async fn commands() -> Response<Body> {
    javascript(include_str!("../../static/commands.js"))
}
