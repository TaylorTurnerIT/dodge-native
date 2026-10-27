use std::{path::PathBuf, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=../../.git");
    // A linked worktree's .git is only a pointer. Its HEAD and index live in
    // the worktree directory, while branch and packed refs live in the common
    // repository. Watch all of them so an empty commit also refreshes the hash.
    for path in ["HEAD", "index", "packed-refs"] {
        watch_git_path(path);
    }
    if let Some(branch) = git_output(&["symbolic-ref", "--quiet", "HEAD"]) {
        watch_git_path(&branch);
    }
    println!("cargo:rerun-if-changed=../../crates/dodge-core/Cargo.toml");
    println!("cargo:rerun-if-changed=../../crates/dodge-core/build.rs");
    println!("cargo:rerun-if-changed=../../crates/dodge-core/src");
    println!("cargo:rerun-if-changed=../../assets/dodge.p8");
    let revision = git_output(&["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".to_owned());
    let dirty = Command::new("git")
        .args([
            "-C",
            "../..",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "crates/dodge-core",
            "assets/dodge.p8",
        ])
        .output()
        .map(|result| match result.status.code() {
            Some(0) => "false",
            Some(1) => "true",
            _ => "unknown",
        })
        .unwrap_or("unknown");
    println!("cargo:rustc-env=DODGE_GAME_REVISION={revision}");
    println!("cargo:rustc-env=DODGE_CORE_DIRTY={dirty}");
}

fn watch_git_path(path: &str) {
    if let Some(path) = git_output(&["rev-parse", "--path-format=absolute", "--git-path", path]) {
        // Cargo treats a missing watched file as dirty on every build. Watch
        // its closest existing ancestor instead, including creation of loose
        // refs after pack-refs or creation of packed-refs in a fresh clone.
        let mut path = PathBuf::from(path);
        while !path.exists() {
            if !path.pop() {
                return;
            }
        }
        println!("cargo:rerun-if-changed={}", path.display());
    }
}

fn git_output(args: &[&str]) -> Option<String> {
    let result = Command::new("git")
        .args(["-C", "../.."])
        .args(args)
        .output()
        .ok()?;
    if !result.status.success() {
        return None;
    }
    String::from_utf8(result.stdout)
        .ok()
        .map(|value| value.trim().to_owned())
}
