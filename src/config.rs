//! Typed, side-effect-free process configuration for the bootstrap host.

use std::error::Error;
use std::ffi::OsString;
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};

/// Loopback-only default; no external interface is exposed implicitly.
pub const DEFAULT_LISTEN_ADDR: SocketAddr = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 3000);
/// Working-directory-relative default; later persistence owns safe database initialization.
pub const DEFAULT_DATABASE_PATH: &str = "data/paperclip.sqlite3";

const LISTEN_OPTION: &str = "--listen-addr";
const DATABASE_OPTION: &str = "--database-path";

/// A validated process configuration with no gameplay or operator controls.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Config {
    listen_addr: SocketAddr,
    database_path: PathBuf,
}

impl Config {
    /// Parse only the two explicit process overrides.
    ///
    /// The input excludes the executable name. No filesystem, network, database,
    /// or process-environment access occurs while parsing.
    pub fn parse_from<I, S>(arguments: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = S>,
        S: Into<OsString>,
    {
        let arguments = arguments
            .into_iter()
            .map(|argument| {
                argument
                    .into()
                    .into_string()
                    .map_err(|_| ConfigError::NonUnicodeInput)
            })
            .collect::<Result<Vec<_>, _>>()?;

        let mut listen_addr = None;
        let mut database_path = None;
        let mut index = 0;
        while index < arguments.len() {
            let option = match arguments[index].as_str() {
                LISTEN_OPTION => ConfigOption::ListenAddr,
                DATABASE_OPTION => ConfigOption::DatabasePath,
                _ => return Err(ConfigError::UnknownArgument),
            };
            let value = arguments
                .get(index + 1)
                .filter(|value| !value.starts_with("--"))
                .ok_or(ConfigError::MissingValue(option))?;

            match option {
                ConfigOption::ListenAddr => {
                    if listen_addr.is_some() {
                        return Err(ConfigError::DuplicateOption(option));
                    }
                    listen_addr = Some(
                        value
                            .parse()
                            .map_err(|_| ConfigError::InvalidValue(ConfigOption::ListenAddr))?,
                    );
                }
                ConfigOption::DatabasePath => {
                    if database_path.is_some() {
                        return Err(ConfigError::DuplicateOption(option));
                    }
                    if value.is_empty() || value.contains('\0') {
                        return Err(ConfigError::InvalidValue(ConfigOption::DatabasePath));
                    }
                    database_path = Some(PathBuf::from(value));
                }
            }
            index += 2;
        }

        Ok(Self {
            listen_addr: listen_addr.unwrap_or(DEFAULT_LISTEN_ADDR),
            database_path: database_path.unwrap_or_else(|| PathBuf::from(DEFAULT_DATABASE_PATH)),
        })
    }

    pub fn listen_addr(&self) -> SocketAddr {
        self.listen_addr
    }

    pub fn database_path(&self) -> &Path {
        &self.database_path
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            listen_addr: DEFAULT_LISTEN_ADDR,
            database_path: PathBuf::from(DEFAULT_DATABASE_PATH),
        }
    }
}

/// The only recognized process options, also used for sanitized diagnostics.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConfigOption {
    ListenAddr,
    DatabasePath,
}

impl ConfigOption {
    fn as_str(self) -> &'static str {
        match self {
            Self::ListenAddr => LISTEN_OPTION,
            Self::DatabasePath => DATABASE_OPTION,
        }
    }
}

/// Configuration failures deliberately do not retain attacker/user-supplied values.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConfigError {
    MissingValue(ConfigOption),
    InvalidValue(ConfigOption),
    DuplicateOption(ConfigOption),
    UnknownArgument,
    NonUnicodeInput,
}

impl fmt::Display for ConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingValue(option) => {
                write!(formatter, "missing value for {}", option.as_str())
            }
            Self::InvalidValue(ConfigOption::ListenAddr) => write!(
                formatter,
                "invalid value for --listen-addr; expected a numeric IP address and port"
            ),
            Self::InvalidValue(ConfigOption::DatabasePath) => write!(
                formatter,
                "invalid value for --database-path; expected a nonempty UTF-8 path"
            ),
            Self::DuplicateOption(option) => {
                write!(formatter, "duplicate option {}", option.as_str())
            }
            Self::UnknownArgument => write!(
                formatter,
                "unknown or forbidden argument; only --listen-addr and --database-path are supported"
            ),
            Self::NonUnicodeInput => write!(formatter, "arguments must be valid UTF-8"),
        }
    }
}

impl Error for ConfigError {}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "paperclip-game-config-test-{}-{sequence}",
                std::process::id()
            ));
            fs::create_dir(&path).expect("create isolated test directory");
            Self(path)
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn sentinel(name: &str) -> (TestDirectory, PathBuf) {
        let directory = TestDirectory::new();
        let path = directory.0.join(name);
        fs::write(&path, b"original-database-bytes").expect("write database sentinel");
        (directory, path)
    }

    fn assert_sentinel_unchanged(path: &Path) {
        assert_eq!(
            fs::read(path).expect("read database sentinel"),
            b"original-database-bytes"
        );
    }

    #[test]
    fn defaults_match_the_source_contract() {
        assert_eq!(DEFAULT_LISTEN_ADDR, "127.0.0.1:3000".parse().unwrap());
        assert_eq!(DEFAULT_DATABASE_PATH, "data/paperclip.sqlite3");

        let config = Config::parse_from(std::iter::empty::<&str>()).expect("default config");
        assert_eq!(config, Config::default());
        assert_eq!(config.listen_addr(), DEFAULT_LISTEN_ADDR);
        assert_eq!(config.database_path(), Path::new(DEFAULT_DATABASE_PATH));
        assert!(config.database_path().is_relative());
    }

    #[test]
    fn explicit_overrides_are_typed_and_do_not_create_a_database() {
        let directory = TestDirectory::new();
        let database = directory.0.join("override.sqlite3");
        let config = Config::parse_from([
            "--database-path",
            database.to_str().expect("UTF-8 test path"),
            "--listen-addr",
            "0.0.0.0:3100",
        ])
        .expect("valid overrides");

        assert_eq!(config.listen_addr(), "0.0.0.0:3100".parse().unwrap());
        assert_eq!(config.database_path(), database);
        assert!(!database.exists(), "configuration must not create data");
    }

    #[test]
    fn a_relative_database_override_stays_relative() {
        let config = Config::parse_from([
            "--database-path",
            "alternate/state.sqlite3",
            "--listen-addr",
            "[::1]:3001",
        ])
        .expect("valid IPv6 and relative path");
        assert_eq!(config.listen_addr(), "[::1]:3001".parse().unwrap());
        assert_eq!(config.database_path(), Path::new("alternate/state.sqlite3"));
    }

    #[test]
    fn malformed_listener_values_fail_before_data_mutation() {
        let (_directory, database) = sentinel("listener sentinel");
        let database = database.to_str().expect("UTF-8 test path");
        for invalid in [
            "localhost:3000",
            "127.0.0.1",
            "127.0.0.1:not-a-port",
            "127.0.0.1:70000",
            "3000",
        ] {
            let error = Config::parse_from(["--database-path", database, "--listen-addr", invalid])
                .expect_err("malformed listener must fail");
            assert_eq!(error, ConfigError::InvalidValue(ConfigOption::ListenAddr));
            assert_sentinel_unchanged(Path::new(database));
        }
    }

    #[test]
    fn malformed_database_and_missing_values_fail_before_data_mutation() {
        let (_directory, database) = sentinel("configuration-sentinel");
        let database = database.to_str().expect("UTF-8 test path");
        for arguments in [
            vec!["--database-path", ""],
            vec!["--database-path", "bad\0path"],
            vec!["--database-path"],
            vec!["--listen-addr"],
            vec!["--database-path", "--pause"],
        ] {
            assert!(Config::parse_from(arguments).is_err());
            assert_sentinel_unchanged(Path::new(database));
        }

        let error = Config::parse_from(["--database-path", database, "unexpected"])
            .expect_err("positional input must fail");
        assert_eq!(error, ConfigError::UnknownArgument);
        assert_sentinel_unchanged(Path::new(database));
    }

    #[test]
    fn forbidden_and_unknown_controls_are_not_recognized() {
        let (_directory, database) = sentinel("forbidden-configuration-sentinel");
        let database_argument = database.to_str().expect("UTF-8 test path");
        for forbidden in [
            "--actor",
            "--world",
            "--game-id",
            "--instance",
            "--set-funds",
            "--set-clips",
            "--resource-total",
            "--pause",
            "--step",
            "--reset",
            "--offline-catchup",
            "--debug",
            "--unknown",
        ] {
            let error = Config::parse_from(["--database-path", database_argument, forbidden, "1"])
                .expect_err("forbidden control must fail");
            assert_eq!(error, ConfigError::UnknownArgument);
            assert_sentinel_unchanged(&database);
        }
    }

    #[test]
    fn duplicate_options_are_rejected_instead_of_ambiguously_overriding() {
        for arguments in [
            vec![
                "--listen-addr",
                "127.0.0.1:3000",
                "--listen-addr",
                "127.0.0.1:3001",
            ],
            vec![
                "--database-path",
                "first sqlite3",
                "--database-path",
                "second.sqlite3",
            ],
        ] {
            assert!(matches!(
                Config::parse_from(arguments),
                Err(ConfigError::DuplicateOption(_))
            ));
        }
    }

    #[test]
    fn diagnostics_do_not_echo_supplied_values() {
        let supplied = "do-not-echo-this-value";
        let invalid_value = Config::parse_from(["--listen-addr", supplied])
            .expect_err("invalid value")
            .to_string();
        let unknown_argument = Config::parse_from([supplied])
            .expect_err("unknown argument")
            .to_string();
        for diagnostic in [invalid_value, unknown_argument] {
            assert!(!diagnostic.contains(supplied));
            assert!(!diagnostic.contains("3000:secret"));
        }
    }
}
