use super::{BASE_HEAD, Result};
use std::{
    fs::OpenOptions,
    io::{self, Write},
    path::{Path, PathBuf},
    process::Command,
};

/// Small JSON serializer for a fixed schema. Strings are escaped; nonfinite
/// floats are errors. No dependency or Cargo manifest changes are needed.
#[derive(Clone)]
pub enum Json {
    String(String),
    Unsigned(u64),
    Float(f64),
    Bool(bool),
    Array(Vec<Self>),
    Object(Vec<(&'static str, Self)>),
}

impl Json {
    pub fn s(value: impl Into<String>) -> Self {
        Self::String(value.into())
    }
    pub const fn u(value: u64) -> Self {
        Self::Unsigned(value)
    }
    pub const fn f(value: f64) -> Self {
        Self::Float(value)
    }
    pub const fn b(value: bool) -> Self {
        Self::Bool(value)
    }
    pub fn array(value: Vec<Self>) -> Self {
        Self::Array(value)
    }
    pub fn object(value: Vec<(&'static str, Self)>) -> Self {
        Self::Object(value)
    }

    pub fn write(&self, out: &mut impl Write) -> io::Result<()> {
        match self {
            Self::String(value) => write_string(out, value),
            Self::Unsigned(value) => write!(out, "{value}"),
            Self::Float(value) => {
                if !value.is_finite() {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "nonfinite JSON number",
                    ));
                }
                write!(out, "{value}")
            }
            Self::Bool(value) => write!(out, "{value}"),
            Self::Array(values) => {
                write!(out, "[")?;
                for (i, value) in values.iter().enumerate() {
                    if i > 0 {
                        write!(out, ",")?;
                    }
                    value.write(out)?;
                }
                write!(out, "]")
            }
            Self::Object(values) => {
                write!(out, "{{")?;
                for (i, (key, value)) in values.iter().enumerate() {
                    if i > 0 {
                        write!(out, ",")?;
                    }
                    write_string(out, key)?;
                    write!(out, ":")?;
                    value.write(out)?;
                }
                write!(out, "}}")
            }
        }
    }
}

fn write_string(out: &mut impl Write, text: &str) -> io::Result<()> {
    write!(out, "\"")?;
    for character in text.chars() {
        match character {
            '"' => write!(out, "\\\"")?,
            '\\' => write!(out, "\\\\")?,
            '\n' => write!(out, "\\n")?,
            '\r' => write!(out, "\\r")?,
            '\t' => write!(out, "\\t")?,
            c if c <= '\u{001f}' => write!(out, "\\u{:04x}", u32::from(c))?,
            c => write!(out, "{c}")?,
        }
    }
    write!(out, "\"")
}

pub fn write_file(path: &Path, value: &Json) -> Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    value.write(&mut file)?;
    writeln!(file)?;
    file.sync_all()?;
    Ok(())
}

pub fn distribution(mut values: Vec<f64>) -> Json {
    values.sort_by(f64::total_cmp);
    let n = values.len();
    let at = |i| values.get(i).copied().unwrap_or(0.0);
    let median = if n.is_multiple_of(2) {
        (at(n.saturating_sub(1) / 2) + at(n / 2)) / 2.0
    } else {
        at(n / 2)
    };
    Json::object(vec![
        (
            "mean",
            Json::f(if n == 0 {
                0.0
            } else {
                values.iter().sum::<f64>() / n as f64
            }),
        ),
        ("median", Json::f(median)),
        ("p90", Json::f(at((9 * n).div_ceil(10).saturating_sub(1)))),
        ("max", Json::f(at(n.saturating_sub(1)))),
    ])
}

pub fn command(root: &Path, program: &str, args: &[&str]) -> Result<String> {
    let output = Command::new(program)
        .args(args)
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "{program} {args:?} failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?.trim_end().to_owned())
}

fn sha256(root: &Path, path: &Path) -> Result<String> {
    let text = path.to_str().ok_or("source path is not UTF-8")?;
    let output = command(root, "shasum", &["-a", "256", text])?;
    let hash = output
        .split_whitespace()
        .next()
        .ok_or("empty shasum result")?;
    if hash.len() != 64 || !hash.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err("invalid SHA256 result".into());
    }
    Ok(hash.to_owned())
}

pub fn identity() -> Result<Json> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()?;
    let head = command(&root, "git", &["rev-parse", "HEAD"])?;
    if head != BASE_HEAD {
        return Err(format!("PREHEADLESS source guard: expected {BASE_HEAD}, found {head}").into());
    }
    // Guard source used by the linked engine, not the parent M1 worktree.
    let tracked_diff = command(
        &root,
        "git",
        &[
            "diff",
            "--exit-code",
            "HEAD",
            "--",
            "crates/dodge-core/src",
            "crates/dodge-core/build.rs",
            "crates/dodge-core/Cargo.toml",
            "assets",
            "Cargo.toml",
            "Cargo.lock",
            ".cargo",
            "rust-toolchain.toml",
        ],
    )?;
    if !tracked_diff.is_empty() {
        return Err("PREHEADLESS source guard found modified engine inputs".into());
    }
    let embedded = [
        (
            "crates/dodge-core/examples/m0_baseline.rs",
            include_str!("../m0_baseline.rs"),
        ),
        (
            "crates/dodge-core/examples/m0/policy.rs",
            include_str!("policy.rs"),
        ),
        (
            "crates/dodge-core/examples/m0/report.rs",
            include_str!("report.rs"),
        ),
        (
            "crates/dodge-core/examples/m0/benchmark.rs",
            include_str!("benchmark.rs"),
        ),
    ];
    for (path, compiled) in embedded {
        if std::fs::read_to_string(root.join(path))? != compiled {
            return Err(format!(
                "harness source changed since compilation: {path}; rebuild before measuring"
            )
            .into());
        }
    }
    let files = command(
        &root,
        "git",
        &[
            "ls-files",
            "--",
            "crates/dodge-core",
            "assets",
            "Cargo.toml",
            "Cargo.lock",
            ".cargo",
            "rust-toolchain.toml",
            "rustfmt.toml",
            "clippy.toml",
        ],
    )?;
    let mut paths: std::collections::BTreeSet<_> = files.lines().map(str::to_owned).collect();
    paths.extend(embedded.iter().map(|(p, _)| (*p).to_owned()));
    let mut hashes = Vec::new();
    for path in paths {
        hashes.push(Json::object(vec![
            ("path", Json::s(path.clone())),
            ("sha256", Json::s(sha256(&root, Path::new(&path))?)),
        ]));
    }
    let executable = std::env::current_exe()?;
    Ok(Json::object(vec![
        ("worktree", Json::s(root.display().to_string())),
        ("head", Json::s(head)),
        ("tracked_engine_inputs_unchanged", Json::b(true)),
        ("compiled_harness_matches_disk", Json::b(true)),
        ("release_profile", Json::b(!cfg!(debug_assertions))),
        ("source_sha256", Json::array(hashes)),
        ("executable", Json::s(executable.display().to_string())),
        ("executable_sha256", Json::s(sha256(&root, &executable)?)),
        ("rustc_vv", Json::s(command(&root, "rustc", &["-Vv"])?)),
        ("cargo_version", Json::s(command(&root, "cargo", &["-V"])?)),
        ("host", Json::s(command(&root, "uname", &["-a"])?)),
        (
            "git_status_short",
            Json::s(command(&root, "git", &["status", "--short"])?),
        ),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_escapes_control_characters_and_rejects_nonfinite_values() -> io::Result<()> {
        let mut out = Vec::new();
        Json::s("a\"\\\n\u{0000}é").write(&mut out)?;
        assert_eq!(String::from_utf8_lossy(&out), "\"a\\\"\\\\\\n\\u0000é\"");
        assert!(Json::f(f64::NAN).write(&mut Vec::new()).is_err());
        assert!(Json::f(f64::INFINITY).write(&mut Vec::new()).is_err());
        Ok(())
    }

    #[test]
    fn median_and_nearest_rank_p90_are_explicit() -> io::Result<()> {
        let mut out = Vec::new();
        distribution(vec![4.0, 1.0, 3.0, 2.0]).write(&mut out)?;
        assert_eq!(
            String::from_utf8_lossy(&out),
            "{\"mean\":2.5,\"median\":2.5,\"p90\":4,\"max\":4}"
        );
        Ok(())
    }
}
