# ruff: noqa: E501  (ported verbatim from the sibling repos, which lint at 102/110 columns)
"""PreToolUse gate: blocks `git commit` unless committer/verify/branch/version/pytest rules pass.

Wired in .claude/settings.json (matcher Bash|PowerShell). Exit 0 allows the tool call,
exit 2 blocks it and feeds stderr back to the model. Stdlib-only so a stale venv can
never break the gate itself.
"""

import json
import re
import subprocess
import sys

REQUIRE_COMMITTER_AGENT = True
# Must beat the 300s hook timeout in settings.json: a harness-killed hook is non-blocking,
# so the gate has to be the one that times out and exits 2.
PYTEST_TIMEOUT_S = 240
TAIL_LINES = 30

QUOTED_OR_BARE = r"""(?:\S*"[^"]*"|\S*'[^']*'|\S+)"""
GIT_COMMIT_RE = re.compile(
    rf"""(?:^|[;&|(\n])\s*
         (?:command\s+|sudo\s+)?
         git(?:\.exe)?\s+
         (?:
             (?:-[cC]|--git-dir|--work-tree|--namespace|--exec-path|--config-env)
                 (?:=\S+|\s+{QUOTED_OR_BARE})\s+
           | --?[A-Za-z][\w-]*\s+
         )*
         commit(?![\w-])""",
    re.VERBOSE | re.IGNORECASE,
)
NO_VERIFY_RE = re.compile(r"(?:^|\s)(?:--no-verify|-n)(?![\w-])")
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)

MSG_DELEGATE = (
    "BLOCKED: direct commits from this session are disabled. Delegate to the 'committer' subagent "
    "(Agent tool, subagent_type: committer) with a summary of the approved changes and whether to "
    "push. Do not retry git commit here."
)
MSG_NO_VERIFY = (
    "BLOCKED: --no-verify is not allowed; pre-commit hooks (ruff, financial-data guard) must run. "
    "Retry without it. If a hook fails, fix the underlying issue instead of bypassing it."
)
MSG_ON_MAIN = (
    "BLOCKED: HEAD is on 'main' — never commit to main. Create a feature branch first: "
    "git switch -c <type>/<slug> --no-track && git push -u origin <type>/<slug> — then retry."
)
MSG_VERSION = (
    "BLOCKED: uv.lock is staged but pyproject.toml's version matches main — dependency changes "
    "require a version bump. Bump version in pyproject.toml, run uv lock, stage both, then retry."
)
MSG_PYTEST_FAILED = (
    "BLOCKED: test suite is red — commits require a green 'uv run pytest'. Fix the failures below; "
    "if they look pre-existing or unrelated, stop and tell the user instead of committing. If the "
    "failures are import errors the venv may be stale: run 'uv sync' and retry."
)
MSG_PYTEST_TIMEOUT = (
    f"BLOCKED: pytest exceeded {PYTEST_TIMEOUT_S}s inside the commit gate. Investigate the hang "
    "(likely a Streamlit AppTest); do not commit until the suite completes green."
)


def looks_like_git_commit(command: str) -> bool:
    return bool(GIT_COMMIT_RE.search(command))


def uses_no_verify(command: str) -> bool:
    return bool(NO_VERIFY_RE.search(command))


def pyproject_version(text: str) -> str | None:
    match = VERSION_RE.search(text)
    return match.group(1) if match else None


def run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")


def block(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def check_version_bump(cwd: str) -> str | None:
    staged = run_git(["diff", "--cached", "--name-only"], cwd).stdout.splitlines()
    if "uv.lock" not in staged:
        return None
    main_pyproject = run_git(["show", "main:pyproject.toml"], cwd)
    staged_pyproject = run_git(["show", ":pyproject.toml"], cwd)
    if main_pyproject.returncode != 0 or staged_pyproject.returncode != 0:
        return None
    main_version = pyproject_version(main_pyproject.stdout)
    staged_version = pyproject_version(staged_pyproject.stdout)
    if main_version and staged_version and main_version == staged_version:
        return MSG_VERSION
    return None


def run_pytest(cwd: str) -> int:
    try:
        result = subprocess.run(
            ["uv", "run", "--no-sync", "pytest", "-x", "-q"],
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=PYTEST_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return block(MSG_PYTEST_TIMEOUT)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + "\n" + result.stderr).strip().splitlines()[-TAIL_LINES:])
        return block(f"{MSG_PYTEST_FAILED}\n--- last {TAIL_LINES} lines ---\n{tail}")
    return 0


def run_checks(payload: dict, command: str) -> int:
    cwd = payload.get("cwd") or "."
    if REQUIRE_COMMITTER_AGENT and payload.get("agent_type") != "committer":
        return block(MSG_DELEGATE)
    if uses_no_verify(command):
        return block(MSG_NO_VERIFY)
    if run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip() == "main":
        return block(MSG_ON_MAIN)
    version_message = check_version_bump(cwd)
    if version_message:
        return block(version_message)
    return run_pytest(cwd)


def main() -> int:
    payload = json.load(sys.stdin)
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not looks_like_git_commit(command):
        return 0
    # Past detection the gate must fail CLOSED: an uncaught crash exits 1, which the harness
    # treats as non-blocking — a buggy gate would silently wave commits through.
    try:
        return run_checks(payload, command)
    except Exception as exc:
        return block(
            f"BLOCKED: commit gate crashed while checking ({exc!r}). Fix .claude/hooks/gate_commit.py "
            "or ask the user how to proceed; do not retry the commit as-is."
        )


if __name__ == "__main__":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.exit(main())
    except Exception as exc:
        print(
            f"gate_commit.py internal error before commit detection ({exc!r}) — the gate did NOT run; "
            "do not commit until this is fixed.",
            file=sys.stderr,
        )
        sys.exit(1)
