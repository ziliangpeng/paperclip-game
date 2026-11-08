use paperclip_game::api::{self, serve};
use paperclip_game::config::Config;
use paperclip_game::runtime::GameRuntime;
use std::ffi::OsString;
use std::future::Future;
use std::io::{self, Write};
use std::process::ExitCode;
use tokio::net::TcpListener;

const RUNTIME_ERROR_EXIT: u8 = 1;
const CONFIGURATION_ERROR_EXIT: u8 = 2;

async fn run<I, S, W, F>(arguments: I, diagnostics: &mut W, shutdown: F) -> io::Result<u8>
where
    I: IntoIterator<Item = S>,
    S: Into<OsString>,
    W: Write,
    F: Future<Output = ()> + Send + 'static,
{
    let config = match Config::parse_from(arguments) {
        Ok(config) => config,
        Err(error) => {
            writeln!(diagnostics, "paperclip-game: configuration error: {error}")?;
            return Ok(CONFIGURATION_ERROR_EXIT);
        }
    };
    let runtime = match GameRuntime::start() {
        Ok(runtime) => runtime,
        Err(_) => {
            writeln!(diagnostics, "paperclip-game: runtime initialization failed")?;
            return Ok(RUNTIME_ERROR_EXIT);
        }
    };
    let listener = match TcpListener::bind(config.listen_addr()).await {
        Ok(listener) => listener,
        Err(_) => {
            writeln!(
                diagnostics,
                "paperclip-game: listener initialization failed"
            )?;
            let _ = runtime.shutdown().await;
            return Ok(RUNTIME_ERROR_EXIT);
        }
    };
    let local_addr = match listener.local_addr() {
        Ok(address) => address,
        Err(_) => {
            writeln!(
                diagnostics,
                "paperclip-game: listener initialization failed"
            )?;
            let _ = runtime.shutdown().await;
            return Ok(RUNTIME_ERROR_EXIT);
        }
    };
    writeln!(diagnostics, "{}", api::startup_message(local_addr))?;
    match serve(listener, runtime, shutdown).await {
        Ok(()) => Ok(0),
        Err(_) => {
            writeln!(
                diagnostics,
                "paperclip-game: service terminated with an error"
            )?;
            Ok(RUNTIME_ERROR_EXIT)
        }
    }
}

#[cfg(unix)]
async fn shutdown_signal() {
    let mut terminate =
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(signal) => signal,
            Err(_) => return,
        };
    tokio::select! {
        _ = tokio::signal::ctrl_c() => {}
        _ = terminate.recv() => {}
    }
}

#[cfg(not(unix))]
async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

#[tokio::main]
async fn main() -> ExitCode {
    let mut diagnostics = io::stderr().lock();
    match run(
        std::env::args_os().skip(1),
        &mut diagnostics,
        shutdown_signal(),
    )
    .await
    {
        Ok(status) => ExitCode::from(status),
        Err(_) => ExitCode::FAILURE,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use tokio::sync::oneshot;

    fn isolated_database(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "paperclip-game-{name}-{}.sqlite3",
            std::process::id()
        ))
    }

    #[tokio::test]
    async fn valid_host_starts_and_stops_without_creating_data() {
        let database = isolated_database("initialized");
        let _ = fs::remove_file(&database);
        let mut diagnostics = Vec::new();
        let (stop, stopped) = oneshot::channel();
        stop.send(()).expect("test shutdown receiver lives");
        let status = run(
            [
                "--listen-addr",
                "127.0.0.1:0",
                "--database-path",
                database.to_str().expect("UTF-8 test path"),
            ],
            &mut diagnostics,
            async {
                let _ = stopped.await;
            },
        )
        .await
        .expect("write diagnostics");

        assert_eq!(status, 0);
        assert!(
            String::from_utf8(diagnostics)
                .expect("UTF-8 diagnostics")
                .contains("paperclip-game: listening on http://127.0.0.1:")
        );
        assert!(!database.exists(), "the API must not create Issue #10 data");
    }

    #[tokio::test]
    async fn invalid_host_leaves_existing_data_unchanged() {
        let database = isolated_database("invalid-configuration");
        fs::write(&database, b"original-database-bytes").expect("write database sentinel");
        let mut diagnostics = Vec::new();
        let status = run(
            [
                "--database-path",
                database.to_str().expect("UTF-8 test path"),
                "--pause",
                "1",
            ],
            &mut diagnostics,
            std::future::pending(),
        )
        .await
        .expect("write diagnostics");

        assert_eq!(status, CONFIGURATION_ERROR_EXIT);
        assert_eq!(
            fs::read(&database).expect("read database sentinel"),
            b"original-database-bytes"
        );
        assert!(
            String::from_utf8(diagnostics)
                .expect("UTF-8 diagnostics")
                .contains("unknown or forbidden argument")
        );
        fs::remove_file(database).expect("remove database sentinel");
    }

    #[tokio::test]
    async fn configuration_diagnostics_are_sanitized() {
        let supplied = "do-not-print-this-configuration-value";
        let mut diagnostics = Vec::new();
        let status = run(
            ["--listen-addr", supplied],
            &mut diagnostics,
            std::future::pending(),
        )
        .await
        .expect("write diagnostics");

        assert_eq!(status, CONFIGURATION_ERROR_EXIT);
        let diagnostics = String::from_utf8(diagnostics).expect("UTF-8 diagnostics");
        assert!(!diagnostics.contains(supplied));
        assert!(diagnostics.contains("configuration error"));
    }
}
