"""Exercise Cargo's provenance invalidation in disposable Git worktrees."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "native" / "build.rs"
FIXTURE_PACKAGE = "dodge-provenance-fixture"
TOOLCHAIN = "1.98.1"


@unittest.skipUnless(
    shutil.which("cargo") and shutil.which("git"), "requires Cargo and Git"
)
class BuildProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Check installation without invoking a proxy that could download Rust.
        rustup = shutil.which("rustup")
        if rustup is not None:
            result = subprocess.run(
                [rustup, "toolchain", "list"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if not any(
                line.startswith(f"{TOOLCHAIN}-") for line in result.stdout.splitlines()
            ):
                raise unittest.SkipTest(f"requires installed Rust {TOOLCHAIN}")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="dodge-build-provenance-", dir="/private/tmp"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # A parent Git command may export repository/config paths. None may
        # redirect these disposable fixture operations into the real checkout.
        self.environment = {
            name: value for name, value in os.environ.items()
            if not name.startswith("GIT_")
        }
        self.environment.update(
            RUSTUP_TOOLCHAIN=TOOLCHAIN,
            CARGO_NET_OFFLINE="true",
            CARGO_HOME=str(self.root / "cargo-home"),
            CARGO_TARGET_DIR=str(self.root / "target"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
        )
        for name in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
            self.environment.pop(name, None)

    def run_command(self, cwd: Path, *arguments: str) -> str:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def git(self, cwd: Path, *arguments: str) -> str:
        return self.run_command(
            cwd,
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            *arguments,
        )

    def write_fixture(self, root: Path) -> None:
        native = root / "learning" / "native"
        (native / "src").mkdir(parents=True)
        (native / "Cargo.toml").write_text(
            '[package]\nname = "' + FIXTURE_PACKAGE + '"\n'
            'version = "0.0.0"\nedition = "2024"\n\n[workspace]\n'
        )
        shutil.copyfile(BUILD_SCRIPT, native / "build.rs")
        (native / "src" / "main.rs").write_text(
            'fn main() { println!("{}\\n{}", '
            'env!("DODGE_GAME_REVISION"), env!("DODGE_CORE_DIRTY")); }\n'
        )
        core = root / "crates" / "dodge-core"
        (core / "src").mkdir(parents=True)
        for path in (core / "Cargo.toml", core / "build.rs", core / "src" / "lib.rs"):
            path.write_text("# fixture source\n")
        (root / "assets").mkdir()
        (root / "assets" / "dodge.p8").write_text("fixture cartridge\n")

    def build_provenance(self, root: Path) -> tuple[str, str]:
        self.run_command(
            root / "learning" / "native", "cargo", "build", "--quiet", "--offline"
        )
        values = self.run_command(
            root, str(self.root / "target" / "debug" / FIXTURE_PACKAGE)
        ).splitlines()
        self.assertEqual(len(values), 2)
        return values[0], values[1]

    def assert_current_provenance(self, worktree: Path, dirty: str = "false") -> None:
        self.assertEqual(
            self.build_provenance(worktree),
            (self.git(worktree, "rev-parse", "HEAD"), dirty),
        )

    def assert_unchanged_build_is_cached(self, worktree: Path) -> None:
        outputs = list(
            (self.root / "target" / "debug" / "build").glob(
                f"{FIXTURE_PACKAGE}-*/output"
            )
        )
        self.assertEqual(len(outputs), 1)
        before = outputs[0].stat().st_mtime_ns
        self.assert_current_provenance(worktree)
        self.assertEqual(outputs[0].stat().st_mtime_ns, before)

    def test_commits_dirty_sources_packed_refs_and_detached_head(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()
        self.git(repository, "init", "--quiet", "--initial-branch=main")
        self.git(repository, "config", "user.name", "Provenance fixture")
        self.git(repository, "config", "user.email", "fixture@example.invalid")
        self.write_fixture(repository)
        self.git(repository, "add", ".")
        self.git(repository, "commit", "--quiet", "-m", "fixture")
        worktree = self.root / "worktree"
        self.git(repository, "worktree", "add", "--quiet", "-b", "fixture", str(worktree))
        # All watched metadata exists for the first invalidation check. A
        # missing packed-refs or core source path must not mask the regression.
        self.git(worktree, "pack-refs", "--all", "--no-prune")
        self.assert_current_provenance(worktree)
        self.assert_unchanged_build_is_cached(worktree)

        # No watched game source changes: only the attached branch ref advances.
        index = Path(
            self.git(
                worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"
            )
        )
        index_stat = index.stat()
        self.git(worktree, "commit", "--quiet", "--allow-empty", "-m", "metadata only")
        os.utime(index, ns=(index_stat.st_atime_ns, index_stat.st_mtime_ns))
        self.assert_current_provenance(worktree)

        for relative in (
            "crates/dodge-core/src/lib.rs",
            "crates/dodge-core/Cargo.toml",
            "crates/dodge-core/build.rs",
            "assets/dodge.p8",
        ):
            with self.subTest(path=relative):
                path = worktree / relative
                path.write_text(path.read_text() + "changed\n")
                self.assert_current_provenance(worktree, "true")
                self.git(worktree, "add", relative)
                self.git(worktree, "commit", "--quiet", "-m", f"update {relative}")
                self.assert_current_provenance(worktree)

        self.git(worktree, "pack-refs", "--all", "--prune")
        self.assert_current_provenance(worktree)
        self.assert_unchanged_build_is_cached(worktree)
        self.git(worktree, "commit", "--quiet", "--allow-empty", "-m", "packed metadata")
        self.git(worktree, "pack-refs", "--all", "--prune")
        self.assert_current_provenance(worktree)

        self.git(worktree, "checkout", "--quiet", "--detach")
        self.assert_current_provenance(worktree)
        self.git(worktree, "commit", "--quiet", "--allow-empty", "-m", "detached metadata")
        self.assert_current_provenance(worktree)

    def test_export_without_git_reports_unknown(self) -> None:
        exported = self.root / "exported"
        self.write_fixture(exported)
        self.assertEqual(self.build_provenance(exported), ("unknown", "unknown"))


if __name__ == "__main__":
    unittest.main()
