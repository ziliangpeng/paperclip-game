use paperclip_game::config::Config;
use std::ffi::OsString;
use std::io::{self, Write};
use std::process::ExitCode;

const NOT_INITIALIZED_EXIT: u8 = 1;
const CONFIGURATION_ERROR_EXIT: u8 = 2;
const NOT_INITIALIZED_MESSAGE: &str =
    "paperclip-game: not-yet-initialized: gameplay runtime and HTTP service are not implemented";

fn run<I, S, W>(arguments: I, diagnostics: &mut W) -> io::Result<u8>
where
    I: IntoIterator<Item = S>,
    S: Into<OsString>,
    W: Write,
{
    match Config::parse_from(arguments) {
        Ok(_) => {
            writeln!(diagnostics, "{NOT_INITIALIZED_MESSAGE}")?;
            Ok(NOT_INITIALIZED_EXIT)
        }
        Err(error) => {
            writeln!(diagnostics, "paperclip-game: configuration error: {error}")?;
            Ok(CONFIGURATION_ERROR_EXIT)
        }
    }
}

fn main() -> ExitCode {
    let mut diagnostics = io::stderr().lock();
    match run(std::env::args_os().skip(1), &mut diagnostics) {
        Ok(status) => ExitCode::from(status),
        Err(_) => ExitCode::FAILURE,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn isolated_database(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "paperclip-game-{name}-{}.sqlite3",
            std::process::id()
        ))
    }

    #[test]
    fn valid_host_explicitly_exits_not_initialized_without_creating_data() {
        let database = isolated_database("not-initialized");
        let _ = fs::remove_file(&database);
        let mut diagnostics = Vec::new();
        let status = run(
            [
                "--database-path",
                database.to_str().expect("UTF-8 test path"),
            ],
            &mut diagnostics,
        )
        .expect("write diagnostics");

        assert_eq!(status, NOT_INITIALIZED_EXIT);
        assert_eq!(
            String::from_utf8(diagnostics).expect("UTF-8 diagnostics"),
            format!("{NOT_INITIALIZED_MESSAGE}\n")
        );
        assert!(!database.exists(), "the bootstrap must not create data");
    }

    #[test]
    fn invalid_host_leaves_existing_data_unchanged() {
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
        )
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

    #[test]
    fn configuration_diagnostics_are_sanitized() {
        let supplied = "do-not-print-this-configuration-value";
        let mut diagnostics = Vec::new();
        let status = run(["--listen-addr", supplied], &mut diagnostics).expect("write diagnostics");

        assert_eq!(status, CONFIGURATION_ERROR_EXIT);
        let diagnostics = String::from_utf8(diagnostics).expect("UTF-8 diagnostics");
        assert!(!diagnostics.contains(supplied));
        assert!(diagnostics.contains("configuration error"));
    }
}
