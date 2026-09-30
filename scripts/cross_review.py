# ruff: noqa: E501, SIM105  (ported verbatim from the sibling repos, which lint at 102/110 columns)
"""Second-opinion code review by the other AI, discussed over resumable rounds and recorded on GitHub.

    just cross-review usage                          # both agents' rate-limit usage and the round budget
    just cross-review start [--base main]            # the peer reviews the branch; round 1
    just cross-review reply <session> --file f       # answer per finding; the peer replies; round N
    just cross-review conclude <session> --file f    # post the consensus report as the closing comment
    just cross-review post <session> --pr N          # catch up on comments not yet on GitHub
    just cross-review status <session>               # each finding as agreed, dropped or open
    just cross-review transcript <session>           # the whole exchange

The peer is Codex (`codex exec`) when this runs inside Claude Code and Claude Code (`claude -p`)
otherwise; `--peer` overrides. The peer runs read-only and its session is resumed for every later round.
Every message is posted as a comment on the branch's PR, or on the issue given with `--issue`, so
GitHub holds the record; `.scratch/cross-review/` is only a cache. With no GitHub repo the exchange
stays local and every command says so.

The round budget comes from both agents' rate-limit usage: under 75% used gives 3 rounds, 75% to 90%
gives 2, and 90% or more (or an unknown reading) runs nothing until `--approve-usage` carries the
user's explicit yes. Codex usage is read from its session logs; Claude usage from the snapshot the
status line writes to `~/.claude/rate-limits.json`.

Exit codes: 0 ok, 1 usage or config error, 2 the peer failed, 3 the peer timed out, 4 the sandbox has
no network, 5 the usage gate.
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIRNAME = Path(".scratch") / "cross-review"
PEERS = ("codex", "claude")
LABELS = {"codex": "Codex", "claude": "Claude Code"}
INSTALL_HINTS = {
    "codex": "npm install -g @openai/codex, then codex login",
    "claude": "see https://claude.com/claude-code, then log in",
}
MAX_DIFF_CHARS = 120_000
MAX_COMMENT_CHARS = 65_000
MAX_FINDINGS = 10
DEFAULT_TIMEOUT_S = 1800.0
GH_TIMEOUT_S = 120.0
DIFF_EXCLUDES = ("uv.lock", ".agents/skills", "quarto/_freeze")
CLAUDE_TOOLS = "Read,Grep,Glob"
PATCH_FILENAME = "round-01-diff.patch"
STRIPPED_ENV = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"}
STRIPPED_ENV_PREFIX = "CLAUDE_CODE_"
# The justfile loads .env (dotenv-load), which holds ANTHROPIC_API_KEY for the weekly email. In `-p`
# mode an API key outranks the subscription login, so a Claude peer would silently bill API credits.
STRIPPED_API_KEYS = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"}
USAGE_REDUCED_AT = 75.0
USAGE_BLOCKED_AT = 90.0
BUDGET_FULL = 3
BUDGET_REDUCED = 2

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PEER_FAILED = 2
EXIT_TIMEOUT = 3
EXIT_SANDBOXED = 4
EXIT_BUDGET = 5

SESSION_NAME_RE = re.compile(r"^\d{8}-\d{6}-(?:codex|claude)(?:-\d+)?$")
FINDING_RE = re.compile(r"^### (F\d+) \[(HIGH|MEDIUM|LOW)\] (\S+)", re.MULTILINE)
BLOCK_END_RE = re.compile(r"^##", re.MULTILINE)
PEER_VERDICT_RE = re.compile(
    r"^(F\d+): (CONCEDE|HOLD|REVISE)(?:[ \t]*\[(HIGH|MEDIUM|LOW)\])?", re.MULTILINE
)
HOST_VERDICT_RE = re.compile(r"^(F\d+): (AGREE|DISPUTE|PARTIAL)\b", re.MULTILINE)
MARKER_RE = re.compile(r"<!-- cross-review ([^>]*?) -->")
PART_RE = re.compile(r"^(\d+)/(\d+)$")
MESSAGE_KINDS = ("review", "response", "reply", "report")
ROLES = ("reviewer", "responder")
BANNER = "NOT RECORDED ON GITHUB: no GitHub repo found; this exchange lives only in {path}"

REVIEW_BRIEF = """You are the second reviewer on a change in this repository. The first reviewer is {host_label}, \
the AI that wrote or is shepherding the change. It will verify each of your findings against the code and \
discuss them with you over up to two more turns. Be concrete and skeptical. Praise is noise; a finding you \
cannot back with code is worse than none.

Scope: {scope_line}
Focus: {focus}

Conventions this repo enforces (see .claude/CLAUDE.md and AGENTS.md for the rest): Python 3.12+, uv only \n(never pip), just, ruff at 100 columns, pathlib with alm.utils.get_project_root(), polars (never pandas), \ntype hints and docstrings on public functions with the rate basis and units stated, tests in tests/ on \nsynthetic data with no network (FRED calls are mocked), no FRED refresh during a Quarto render, and a \nversion bump in pyproject.toml whenever dependencies change. Domain rules: assets are valued at their own \nyield or purchase price, never at the risk-free rate; DV01 (not Macaulay duration) is the risk measure for \nnet cash flows and swaps; short-duration liability blocks tilt toward government bonds.

Do this:
1. Read the diff (the Diff section at the end says where it is), then open every changed file and what \
it calls or is called by. Verify each claim against the working tree, not the diff alone.
2. Hunt for: wrong results, unhandled input at a boundary (CLI args, files, network), broken invariants \
between modules, data loss or security exposure, tests that pass without testing the claim, new behavior \
with no test, and violations of the conventions above. Skip taste.
3. Read only. Do not edit, create, or delete files, and do not commit. The patch file and the working tree \
hold everything you need.

Answer in exactly this shape; the F numbers are how we refer to findings later:

## Findings
### F1 [HIGH] path/to/file.py:LINE
Claim: one sentence, what is wrong.
Evidence: the code path or input that shows it, with file:line for anything you read.
Fix: one or two sentences.

(F2, F3, ... in the same shape, highest severity first, at most {max_findings}. A severity with nothing to \
report gets one line, for example "No HIGH findings".)

## Checked and fine
Bullets: what you verified and found correct, and anything you could not verify, marked UNVERIFIED with \
what you would need.

## Summary
Two or three sentences: overall risk, and whether you would merge as is.

Severity: HIGH = wrong behavior, data loss, security, or a test that hides a bug. MEDIUM = an edge case, a \
missing boundary check, or a structure that will produce a bug on the next change. LOW = a convention, \
naming, or simplification point.

## Diff
{diff_section}
"""

DIFF_INLINE = """{file_count} files, {line_count} diff lines, also saved whole at {patch_path}. Not inlined \
even if changed: {excludes}.

{stat}

```diff
{diff}
```
"""

DIFF_TOO_LARGE = """The diff is {line_count} lines across {file_count} files, too large to inline. Read it \
from {patch_path} in parts, searching it for `diff --git a/<path>`. Untracked new files (read them \
directly): {untracked}. Not inlined even if changed: {excludes}.

{stat}
"""

DISCUSSION_FOOTER = """---
Reply format. First, one line per finding you have raised so far, in order:
F<n>: CONCEDE | HOLD | REVISE
CONCEDE = you now agree it is not a problem, is already handled, or is out of scope. HOLD = still a real \
problem at the stated severity. REVISE = you keep it but change the severity or claim; give the new severity \
in brackets.
Then the reasoning for each HOLD or REVISE, re-reading the code and citing file:line. A HOLD with no new \
evidence should be a CONCEDE. If my reply exposes a new problem, add it as F{next} in the round-one shape \
(### F{next} [SEVERITY] path:line, then Claim, Evidence, Fix). Stay under 500 words unless a HOLD needs code.
"""

Runner = Callable[..., subprocess.CompletedProcess]


class CrossReviewError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DiffScope:
    branch: str
    head: str
    base: str | None
    merge_base: str | None
    commit: str | None

    def describe(self) -> str:
        if self.commit:
            return f"commit `{self.commit[:7]}` against its parent"
        return (
            f"working tree of branch `{self.branch}` against merge-base `{(self.merge_base or '')[:7]}` of "
            f"`{self.base}`; committed and uncommitted changes, untracked files shown as new-file diffs"
        )

    def to_json(self) -> dict:
        return {
            "branch": self.branch,
            "head": self.head,
            "base": self.base,
            "merge_base": self.merge_base,
            "commit": self.commit,
        }


@dataclass(frozen=True)
class DiffBundle:
    stat: str
    diff: str
    untracked: tuple[str, ...]
    file_count: int
    line_count: int

    @property
    def is_empty(self) -> bool:
        return not self.diff.strip() and not self.untracked


@dataclass(frozen=True)
class PeerReply:
    session_id: str | None
    text: str
    failure: str | None
    cost_usd: float | None = None
    permission_denials: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class UsageWindow:
    name: str
    used_percent: float
    resets_at: float | None


@dataclass(frozen=True)
class UsageReading:
    agent: str
    windows: tuple[UsageWindow, ...]
    captured_at: float | None
    source: str

    @property
    def worst_percent(self) -> float | None:
        return max((window.used_percent for window in self.windows), default=None)

    def to_json(self) -> dict:
        return {
            "agent": self.agent,
            "windows": [
                {
                    "name": window.name,
                    "used_percent": window.used_percent,
                    "resets_at": window.resets_at,
                }
                for window in self.windows
            ],
            "captured_at": self.captured_at,
            "source": self.source,
        }


@dataclass(frozen=True)
class Target:
    kind: str
    number: int
    url: str

    def describe(self) -> str:
        noun = "PR" if self.kind == "pr" else "issue"
        return f"{noun} #{self.number} {self.url}"

    def to_json(self) -> dict:
        return {"kind": self.kind, "number": self.number, "url": self.url}


@dataclass(frozen=True)
class Message:
    round: int
    kind: str
    author: str
    role: str
    text: str
    comment_url: str | None = None
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def title(self) -> str:
        speaker = f"{LABELS.get(self.author, self.author)} ({self.role})"
        if self.kind == "report":
            return f"Cross-review consensus report by {speaker}"
        return f"Cross-review round {self.round} {self.kind} by {speaker}"


# ------------------------------------------------------------------------------------------------------
# host, peer, environment


def detect_host(env: Mapping[str, str]) -> str:
    return "claude" if env.get("CLAUDECODE") == "1" else "codex"


def default_peer(host: str) -> str:
    return "codex" if host == "claude" else "claude"


def child_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in env.items()
        if key not in STRIPPED_ENV | STRIPPED_API_KEYS and not key.startswith(STRIPPED_ENV_PREFIX)
    }


def find_cli(peer: str, env: Mapping[str, str]) -> Path:
    found = shutil.which(peer, path=env.get("PATH"))
    if found is None and peer == "claude":
        found = env.get("CLAUDE_CODE_EXECPATH")
    if not found or not Path(found).exists():
        raise CrossReviewError(f"{peer} CLI not found on PATH ({INSTALL_HINTS[peer]})")
    return Path(found)


def gh_executable(env: Mapping[str, str]) -> str:
    return shutil.which("gh", path=env.get("PATH")) or "gh"


def display_path(path: Path) -> str:
    try:
        return "~/" + path.resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ------------------------------------------------------------------------------------------------------
# git and the diff


def run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args], cwd=str(cwd), capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CrossReviewError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.decode("utf-8", errors="replace")


def resolve_scope(base: str, commit: str | None, cwd: Path) -> DiffScope:
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).strip()
    head = run_git(["rev-parse", "HEAD"], cwd).strip()
    if commit:
        sha = run_git(["rev-parse", "--verify", f"{commit}^{{commit}}"], cwd).strip()
        return DiffScope(branch, head, None, None, sha)
    merge_base = run_git(["merge-base", base, "HEAD"], cwd).strip()
    return DiffScope(branch, head, base, merge_base, None)


def exclude_pathspecs() -> list[str]:
    return [f":(exclude){pattern}" for pattern in DIFF_EXCLUDES]


def is_excluded(relative_path: str) -> bool:
    return any(
        relative_path == pattern or relative_path.startswith(pattern + "/")
        for pattern in DIFF_EXCLUDES
    )


def untracked_diff(relative_path: str, cwd: Path) -> str:
    header = f"diff --git a/{relative_path} b/{relative_path}\nnew file mode 100644\n"
    raw = (cwd / relative_path).read_bytes()
    if b"\0" in raw:
        return header + f"Binary file {relative_path} added\n"
    lines = raw.decode("utf-8", errors="replace").splitlines(keepends=True)
    body = "".join(
        difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{relative_path}")
    )
    if body and not body.endswith("\n"):
        body += "\n"
    return header + body


def collect_diff(scope: DiffScope, cwd: Path) -> DiffBundle:
    excludes = exclude_pathspecs()
    diff_flags = ["--no-color", "--no-ext-diff", "--find-renames"]
    if scope.commit:
        diff = run_git(["show", "--format=", *diff_flags, scope.commit, "--", ".", *excludes], cwd)
        stat = run_git(
            ["show", "--format=%s", "--stat=110", scope.commit, "--", ".", *excludes], cwd
        )
        untracked: tuple[str, ...] = ()
    else:
        merge_base = scope.merge_base or ""
        diff = run_git(["diff", *diff_flags, merge_base, "--", ".", *excludes], cwd)
        stat = run_git(["diff", "--stat=110", merge_base, "--", ".", *excludes], cwd)
        listed = run_git(["ls-files", "--others", "--exclude-standard"], cwd).splitlines()
        untracked = tuple(path for path in listed if path and not is_excluded(path))
        for relative_path in untracked:
            diff += untracked_diff(relative_path, cwd)
        if untracked:
            stat = stat.rstrip("\n") + "\n" + "\n".join(f" {path} | new file" for path in untracked)
    file_count = sum(1 for line in diff.splitlines() if line.startswith("diff --git "))
    return DiffBundle(stat.strip(), diff, untracked, file_count, diff.count("\n"))


def render_review_brief(
    scope: DiffScope, bundle: DiffBundle, host: str, focus: str | None, patch_path: Path
) -> str:
    excludes = ", ".join(DIFF_EXCLUDES)
    if len(bundle.diff) > MAX_DIFF_CHARS:
        diff_section = DIFF_TOO_LARGE.format(
            line_count=bundle.line_count,
            file_count=bundle.file_count,
            patch_path=patch_path,
            untracked=", ".join(bundle.untracked) or "none",
            excludes=excludes,
            stat=bundle.stat,
        )
    else:
        diff_section = DIFF_INLINE.format(
            file_count=bundle.file_count,
            line_count=bundle.line_count,
            patch_path=patch_path,
            excludes=excludes,
            stat=bundle.stat,
            diff=bundle.diff.rstrip("\n"),
        )
    return REVIEW_BRIEF.format(
        host_label=LABELS[host],
        scope_line=scope.describe(),
        focus=focus or "none given; review the whole change",
        max_findings=MAX_FINDINGS,
        diff_section=diff_section,
    )


def render_discussion(message: str, next_finding: int) -> str:
    return message.rstrip("\n") + "\n\n" + DISCUSSION_FOOTER.format(next=next_finding)


# ------------------------------------------------------------------------------------------------------
# peers


def codex_argv(
    cli: Path, cwd: Path, output_path: Path, model: str | None, resume_id: str | None
) -> list[str]:
    if resume_id:
        argv = [str(cli), "exec", "resume", resume_id, "-", "--json", "-o", str(output_path)]
    else:
        argv = [str(cli), "exec", "-", "--json", "-o", str(output_path), "-s", "read-only"]
        argv += ["-C", str(cwd), "--skip-git-repo-check"]
    if model:
        argv += ["-m", model]
    return argv


def claude_argv(cli: Path, model: str | None, resume_id: str | None) -> list[str]:
    argv = [str(cli), "-p", "--output-format", "json", "--tools", CLAUDE_TOOLS]
    argv += ["--permission-mode", "dontAsk", "--permission-prompts", "none"]
    if model:
        argv += ["--model", model]
    if resume_id:
        argv += ["--resume", resume_id]
    return argv


def parse_codex_reply(stdout: str, output_path: Path) -> PeerReply:
    session_id = None
    failure = None
    last_message = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            session_id = event.get("thread_id")
        elif kind in {"turn.failed", "error"}:
            error = event.get("error")
            detail = error.get("message") if isinstance(error, dict) else event.get("message")
            failure = str(detail or kind)
        elif kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                last_message = str(item["text"])
    text = (
        output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""
    )
    text = text.strip() or (last_message or "").strip()
    if not text and failure is None:
        failure = "no final message written"
    return PeerReply(session_id, text, failure)


def parse_claude_reply(stdout: str, returncode: int) -> PeerReply:
    payload = None
    try:
        candidate = json.loads(stdout.strip())
        payload = candidate if isinstance(candidate, dict) else None
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("type") == "result":
                payload = candidate
                break
    if payload is None:
        return PeerReply(None, stdout.strip(), f"claude exited {returncode} without a JSON result")
    failure = None
    subtype = payload.get("subtype")
    if returncode != 0 or payload.get("is_error") or subtype not in (None, "success"):
        failure = f"claude reported {subtype or 'an error'} (exit {returncode})"
    denials = payload.get("permission_denials") or []
    cost = payload.get("total_cost_usd")
    return PeerReply(
        payload.get("session_id"),
        str(payload.get("result") or "").strip(),
        failure,
        float(cost) if isinstance(cost, (int, float)) else None,
        len(denials),
    )


def kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False
        )
    else:
        process.kill()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_process(
    argv: list[str], *, input: bytes | None, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess:
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=env,
    )
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def call_peer(
    peer: str,
    prompt: str,
    *,
    cwd: Path,
    output_path: Path,
    model: str | None,
    resume_id: str | None,
    timeout_s: float,
    runner: Runner,
    env: Mapping[str, str],
) -> PeerReply:
    cli = find_cli(peer, env)
    if peer == "codex":
        argv = codex_argv(cli, cwd, output_path, model, resume_id)
    else:
        argv = claude_argv(cli, model, resume_id)
    completed = runner(
        argv, input=prompt.encode("utf-8"), cwd=cwd, env=child_env(env), timeout=timeout_s
    )
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
    if peer == "codex":
        reply = parse_codex_reply(stdout, output_path)
        if reply.failure is None and completed.returncode != 0:
            reply = PeerReply(reply.session_id, reply.text, f"codex exited {completed.returncode}")
    else:
        reply = parse_claude_reply(stdout, completed.returncode)
    failure = reply.failure
    network_tokens = ("ENOTFOUND", "fetch failed", "ECONNREFUSED")
    if failure and peer == "claude" and any(token in stderr for token in network_tokens):
        failure += "; the network looks blocked, rerun with escalated permissions"
    return PeerReply(
        reply.session_id,
        reply.text,
        failure,
        reply.cost_usd,
        reply.permission_denials,
        stdout,
        stderr,
    )


# ------------------------------------------------------------------------------------------------------
# usage and the round budget


def window_name(minutes: int | None) -> str:
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "weekly"
    return f"{minutes} min" if minutes else "window"


def parse_timestamp(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def last_rate_limit_record(path: Path) -> tuple[float | None, dict] | None:
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if '"rate_limits"' not in line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") or {}
        limits = payload.get("rate_limits")
        if isinstance(limits, dict):
            return parse_timestamp(record.get("timestamp")), limits
    return None


def read_codex_usage(
    codex_home: Path, now_epoch: float, thread_id: str | None = None
) -> UsageReading:
    sessions_dir = codex_home / "sessions"
    candidates = list(sessions_dir.rglob("rollout-*.jsonl")) if sessions_dir.is_dir() else []
    if thread_id:
        matching = [path for path in candidates if thread_id in path.name]
        candidates = matching or candidates
    if not candidates:
        return UsageReading(
            "codex", (), None, f"no session logs under {display_path(sessions_dir)}"
        )
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    record = last_rate_limit_record(newest)
    if record is None:
        return UsageReading("codex", (), None, f"{display_path(newest)} (no rate-limit record)")
    captured_at, limits = record
    windows = []
    for key in ("primary", "secondary"):
        window = limits.get(key)
        if not isinstance(window, dict):
            continue
        used = float(window.get("used_percent") or 0.0)
        resets_at = parse_timestamp(window.get("resets_at"))
        if resets_at is not None and resets_at < now_epoch:
            used = 0.0
        windows.append(UsageWindow(window_name(window.get("window_minutes")), used, resets_at))
    plan = limits.get("plan_type")
    source = display_path(newest) + (f" (plan {plan})" if plan else "")
    return UsageReading("codex", tuple(windows), captured_at, source)


def read_claude_usage(config_dir: Path, now_epoch: float) -> UsageReading:
    snapshot = config_dir / "rate-limits.json"
    if not snapshot.is_file():
        return UsageReading("claude", (), None, f"{display_path(snapshot)} missing")
    try:
        data = json.loads(snapshot.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return UsageReading("claude", (), None, f"{display_path(snapshot)} unreadable")
    windows = []
    for key, name in (("five_hour", "5h"), ("seven_day", "weekly"), ("spend_limit", "spend")):
        window = data.get(key)
        if not isinstance(window, dict):
            continue
        used = float(window.get("used_percentage") or 0.0)
        resets_at = parse_timestamp(window.get("resets_at"))
        if resets_at is not None and resets_at < now_epoch:
            used = 0.0
        windows.append(UsageWindow(name, used, resets_at))
    captured_at = parse_timestamp(data.get("captured_at"))
    return UsageReading("claude", tuple(windows), captured_at, display_path(snapshot))


def manual_usage(agent: str, percent: float, now_epoch: float) -> UsageReading:
    window = UsageWindow("manual", float(percent), None)
    return UsageReading(agent, (window,), now_epoch, "given on the command line")


def read_usage(
    env: Mapping[str, str],
    now_epoch: float,
    *,
    claude_manual: float | None,
    codex_manual: float | None,
    codex_thread: str | None = None,
) -> dict[str, UsageReading]:
    home = Path.home()
    codex_home = Path(env.get("CODEX_HOME") or home / ".codex")
    claude_dir = Path(env.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    if claude_manual is not None:
        claude_reading = manual_usage("claude", claude_manual, now_epoch)
    else:
        claude_reading = read_claude_usage(claude_dir, now_epoch)
    if codex_manual is not None:
        codex_reading = manual_usage("codex", codex_manual, now_epoch)
    else:
        codex_reading = read_codex_usage(codex_home, now_epoch, codex_thread)
    return {"claude": claude_reading, "codex": codex_reading}


def worst_usage(readings: Mapping[str, UsageReading]) -> float | None:
    worsts = [reading.worst_percent for reading in readings.values()]
    if any(worst is None for worst in worsts):
        return None
    return max(worst for worst in worsts if worst is not None)


def round_budget(worst_percent: float | None, approved: bool) -> int:
    if worst_percent is None or worst_percent >= USAGE_BLOCKED_AT:
        return BUDGET_REDUCED if approved else 0
    if worst_percent >= USAGE_REDUCED_AT:
        return BUDGET_REDUCED
    return BUDGET_FULL


def format_span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def render_usage(readings: Mapping[str, UsageReading], budget: int, now_epoch: float) -> str:
    lines = [f"{'agent':<12} {'window':<8} {'used':>5}  {'resets':<12} {'reading age':<12} source"]
    for agent in ("claude", "codex"):
        reading = readings[agent]
        if reading.captured_at is None:
            age = "unknown"
        else:
            age = format_span(now_epoch - reading.captured_at) + " ago"
        if not reading.windows:
            lines.append(
                f"{LABELS[agent]:<12} {'-':<8} {'?':>5}  {'-':<12} {age:<12} {reading.source}"
            )
            continue
        for index, window in enumerate(reading.windows):
            if window.resets_at is None:
                resets = "-"
            else:
                resets = "in " + format_span(window.resets_at - now_epoch)
            source = reading.source if index == 0 else ""
            used = f"{window.used_percent:.0f}%"
            lines.append(
                f"{LABELS[agent]:<12} {window.name:<8} {used:>5}  {resets:<12} {age:<12} {source}"
            )
    worst = worst_usage(readings)
    if worst is None:
        rule = "a reading is unknown"
    elif worst >= USAGE_BLOCKED_AT:
        rule = f"worst {worst:.0f}% is at or above {USAGE_BLOCKED_AT:.0f}%"
    elif worst >= USAGE_REDUCED_AT:
        rule = f"worst {worst:.0f}% is at or above {USAGE_REDUCED_AT:.0f}%"
    else:
        rule = f"worst {worst:.0f}% is under {USAGE_REDUCED_AT:.0f}%"
    if budget:
        verdict = f"{budget} rounds"
    else:
        verdict = "0 rounds; needs the user's explicit yes (--approve-usage)"
    lines.append(f"budget: {verdict} ({rule})")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------
# GitHub record


class GhError(CrossReviewError):
    """gh exited nonzero or answered with something other than JSON; the message carries its output."""


def gh_json(args: list[str], *, cwd: Path, runner: Runner, env: Mapping[str, str]) -> dict | list:
    argv = [gh_executable(env), *args]
    completed = runner(argv, input=None, cwd=cwd, env=dict(env), timeout=GH_TIMEOUT_S)
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise GhError(f"gh {' '.join(args[:2])} failed: {stderr or f'exit {completed.returncode}'}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise GhError(
            f"gh {' '.join(args[:2])} answered with something other than JSON: {stdout.strip()[:200]!r}"
        ) from None


def github_remote(cwd: Path) -> str | None:
    """The first remote URL on a GitHub host, or None when this repo has no such remote."""
    try:
        listed = run_git(["config", "--get-regexp", r"^remote\..*\.url$"], cwd)
    except CrossReviewError:
        return None
    for line in listed.splitlines():
        _key, _space, url = line.partition(" ")
        if "github" in url.lower():
            return url.strip()
    return None


def resolve_target(
    cwd: Path,
    runner: Runner,
    env: Mapping[str, str],
    *,
    pr: int | None,
    issue: int | None,
    no_post: bool,
) -> tuple[Target | None, str]:
    """Walk the record ladder: explicit target, else the branch's PR, else an error; no repo means local."""
    if no_post:
        return None, "no-post"
    try:
        repo = gh_json(
            ["repo", "view", "--json", "nameWithOwner,url"], cwd=cwd, runner=runner, env=env
        )
    except GhError:
        if pr or issue or github_remote(cwd):
            raise
        return None, "no-repo"
    if not isinstance(repo, dict) or not repo.get("url"):
        raise CrossReviewError(f"gh repo view answered without a repository url: {str(repo)[:200]}")
    repo_url = str(repo["url"]).rstrip("/")
    if pr:
        return Target("pr", pr, f"{repo_url}/pull/{pr}"), "pr"
    if issue:
        return Target("issue", issue, f"{repo_url}/issues/{issue}"), "issue"
    try:
        current = gh_json(
            ["pr", "view", "--json", "number,url,state"], cwd=cwd, runner=runner, env=env
        )
    except GhError as error:
        raise CrossReviewError(
            f"no PR found for this branch ({error}); pass --issue N (the issue for this work; create one "
            "with `gh issue create` if none exists) or --no-post"
        ) from None
    if isinstance(current, dict) and current.get("number"):
        return Target("pr", int(current["number"]), str(current["url"])), "pr"
    raise CrossReviewError(
        "no PR for this branch; pass --issue N (the issue for this work; create one with "
        "`gh issue create` if none exists) or --no-post"
    )


def marker_fields(session: dict, message: Message) -> dict[str, str]:
    scope = session.get("scope") or {}
    return {
        "session": session["name"],
        "round": str(message.round),
        "kind": message.kind,
        "author": message.author,
        "role": message.role,
        "peer_session": session.get("peer_session_id") or "none",
        "model": session.get("model") or "default",
        "head": (scope.get("head") or "")[:7] or "none",
    }


def render_marker(fields: Mapping[str, str]) -> str:
    return (
        "<!-- cross-review " + " ".join(f"{key}={value}" for key, value in fields.items()) + " -->"
    )


def render_comment(title: str, fields: Mapping[str, str], text: str) -> str:
    body = text.strip("\n")
    return f"### {title}\n{render_marker(fields)}\n\n{body}\n"


def split_comment(
    title: str, fields: Mapping[str, str], text: str, limit: int = MAX_COMMENT_CHARS
) -> list[str]:
    whole = render_comment(title, fields, text)
    if len(whole) <= limit:
        return [whole]
    header_room = len(render_comment(title + " (part 99/99)", {**fields, "part": "99/99"}, ""))
    chunk_limit = max(1000, limit - header_room)
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > chunk_limit:
            chunks.append(current)
            current = ""
        while len(line) > chunk_limit:
            chunks.append(line[:chunk_limit])
            line = line[chunk_limit:]
        current += line
    if current:
        chunks.append(current)
    total = len(chunks)
    return [
        render_comment(
            f"{title} (part {index}/{total})", {**fields, "part": f"{index}/{total}"}, chunk
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def post_comment(
    target: Target, body: str, *, body_path: Path, cwd: Path, runner: Runner, env: Mapping[str, str]
) -> str:
    body_path.write_text(body, encoding="utf-8", newline="\n")
    argv = [
        gh_executable(env),
        target.kind,
        "comment",
        str(target.number),
        "--body-file",
        str(body_path),
    ]
    completed = runner(argv, input=None, cwd=cwd, env=dict(env), timeout=GH_TIMEOUT_S)
    if completed.returncode != 0:
        detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise CrossReviewError(f"gh {target.kind} comment failed: {detail}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def parse_marker(body: str) -> tuple[dict[str, str], str] | None:
    match = MARKER_RE.search(body)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for pair in match.group(1).split():
        key, _, value = pair.partition("=")
        fields[key] = value
    text = body[match.end() :].lstrip("\r\n")
    return fields, text


def iter_json_objects(text: str) -> Iterable[dict]:
    decoder = json.JSONDecoder()
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return
        try:
            value, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            return
        if isinstance(value, dict):
            yield value


def fetch_comments(
    target: Target, *, cwd: Path, runner: Runner, env: Mapping[str, str]
) -> list[Message]:
    endpoint = f"repos/{{owner}}/{{repo}}/issues/{target.number}/comments"
    argv = [
        gh_executable(env),
        "api",
        endpoint,
        "--paginate",
        "--jq",
        ".[] | {body, html_url, created_at}",
    ]
    completed = runner(argv, input=None, cwd=cwd, env=dict(env), timeout=GH_TIMEOUT_S)
    if completed.returncode != 0:
        detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise CrossReviewError(f"gh api comments failed for {target.describe()}: {detail}")
    parts: dict[tuple[str, int, str, str], dict[int, tuple[str, str, dict[str, str]]]] = {}
    totals: dict[tuple[str, int, str, str], set[int]] = {}
    order: list[tuple[str, int, str, str]] = []
    for comment in iter_json_objects((completed.stdout or b"").decode("utf-8", errors="replace")):
        parsed = parse_marker(str(comment.get("body") or ""))
        if parsed is None:
            continue
        fields = validated_marker(parsed[0])
        if fields is None:
            continue
        part_index, part_total = parse_part(fields)
        key = (fields["session"], int(fields["round"]), fields["kind"], fields["author"])
        if key not in parts:
            order.append(key)
        parts.setdefault(key, {})[part_index] = (
            parsed[1],
            str(comment.get("html_url") or ""),
            fields,
        )
        totals.setdefault(key, set()).add(part_total)
    messages = []
    for key in order:
        pieces = parts[key]
        expected = totals[key]
        if len(expected) != 1 or set(pieces) != set(range(1, next(iter(expected)) + 1)):
            print(
                f"warning: skipping round {key[1]} {key[2]} by {key[3]} on {target.describe()}: "
                "incomplete or inconsistent parts",
                file=sys.stderr,
            )
            continue
        text = "\n".join(pieces[index][0].rstrip("\n") for index in sorted(pieces))
        first_url, fields = pieces[1][1], pieces[1][2]
        messages.append(
            Message(key[1], key[2], key[3], fields["role"], text, first_url, dict(fields))
        )
    return messages


def validated_marker(fields: Mapping[str, str]) -> dict[str, str] | None:
    """PR comments are untrusted input: only markers whose fields are safe as paths and bookkeeping pass."""
    if not SESSION_NAME_RE.match(fields.get("session", "")):
        return None
    if fields.get("kind") not in MESSAGE_KINDS or fields.get("author") not in PEERS:
        return None
    if fields.get("role") not in ROLES:
        return None
    round_text = fields.get("round", "")
    if not round_text.isdigit() or int(round_text) < 1:
        return None
    part = PART_RE.match(fields.get("part", "1/1"))
    if part is None or not 1 <= int(part.group(1)) <= int(part.group(2)):
        return None
    return dict(fields)


def parse_part(fields: Mapping[str, str]) -> tuple[int, int]:
    part = PART_RE.match(fields.get("part", "1/1"))
    if part is None:
        return 1, 1
    return int(part.group(1)), int(part.group(2))


# ------------------------------------------------------------------------------------------------------
# sessions


def sessions_dir_for(repo_root: Path) -> Path:
    return repo_root / SESSIONS_DIRNAME


def new_session_dir(sessions_dir: Path, peer: str, now: datetime.datetime) -> Path:
    base_name = f"{now:%Y%m%d-%H%M%S}-{peer}"
    candidate = sessions_dir / base_name
    suffix = 2
    while candidate.exists():
        candidate = sessions_dir / f"{base_name}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def resolve_session(sessions_dir: Path, name: str | None, last: bool) -> Path:
    if name:
        session_dir = sessions_dir / name
        if not (session_dir / "session.json").is_file():
            raise CrossReviewError(f"no session named {name} under {display_path(sessions_dir)}")
        return session_dir
    if last:
        if sessions_dir.is_dir():
            candidates = sorted(
                (
                    path
                    for path in sessions_dir.iterdir()
                    if path.is_dir() and SESSION_NAME_RE.match(path.name)
                ),
                key=lambda path: path.name,
            )
        else:
            candidates = []
        if not candidates:
            raise CrossReviewError(f"no sessions under {display_path(sessions_dir)}")
        return candidates[-1]
    raise CrossReviewError("give a session name, --last, --pr N or --issue N")


def load_session(session_dir: Path) -> dict:
    return json.loads((session_dir / "session.json").read_text(encoding="utf-8"))


def save_session(session_dir: Path, session: dict) -> None:
    payload = json.dumps(session, indent=2) + "\n"
    (session_dir / "session.json").write_text(payload, encoding="utf-8", newline="\n")


def session_target(session: dict) -> Target | None:
    target = session.get("target")
    if not target:
        return None
    return Target(target["kind"], int(target["number"]), target["url"])


def banner_for(session: dict, session_dir: Path) -> str | None:
    if session.get("record") == "no-repo":
        return BANNER.format(path=display_path(session_dir))
    return None


def message_filename(message: Message) -> str:
    if message.kind == "report":
        return "report.md"
    return f"round-{message.round:02d}-{message.kind}.md"


def load_messages(session_dir: Path, session: dict) -> list[Message]:
    messages = []
    for entry in session.get("messages", []):
        path = session_dir / entry["file"]
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        messages.append(
            Message(
                int(entry["round"]),
                entry["kind"],
                entry["author"],
                entry["role"],
                text,
                entry.get("comment_url"),
            )
        )
    return messages


def add_message(session_dir: Path, session: dict, message: Message) -> dict:
    filename = message_filename(message)
    destination = session_dir / filename
    if destination.resolve().parent != session_dir.resolve():
        raise CrossReviewError(f"refusing to write {filename} outside {display_path(session_dir)}")
    destination.write_text(message.text.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    entry = {
        "round": message.round,
        "kind": message.kind,
        "author": message.author,
        "role": message.role,
        "file": filename,
        "comment_url": message.comment_url,
    }
    session.setdefault("messages", []).append(entry)
    return entry


def post_entry(
    session_dir: Path,
    session: dict,
    entry: dict,
    *,
    cwd: Path,
    runner: Runner,
    env: Mapping[str, str],
) -> str | None:
    target = session_target(session)
    if target is None or entry.get("comment_url"):
        return entry.get("comment_url")
    text = (session_dir / entry["file"]).read_text(encoding="utf-8")
    message = Message(int(entry["round"]), entry["kind"], entry["author"], entry["role"], text)
    bodies = split_comment(message.title, marker_fields(session, message), text)
    posted_urls = list(entry.get("comment_urls") or [])
    body_path = session_dir / ".comment-body.md"
    for body in bodies[len(posted_urls) :]:
        posted_urls.append(
            post_comment(target, body, body_path=body_path, cwd=cwd, runner=runner, env=env)
        )
        entry["comment_urls"] = posted_urls
        save_session(session_dir, session)
    entry["comment_url"] = posted_urls[0] if posted_urls else None
    save_session(session_dir, session)
    return entry["comment_url"]


def import_session(
    target: Target,
    sessions_dir: Path,
    *,
    cwd: Path,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
) -> Path:
    """Rebuild a local session from the marked comments on a PR or issue, or refresh a cached one."""
    fetched = fetch_comments(target, cwd=cwd, runner=runner, env=env)
    if not fetched:
        raise CrossReviewError(f"no cross-review comments on {target.describe()}")
    name, messages = select_session(fetched)
    session_dir = sessions_dir / name
    if session_dir.is_symlink() or session_dir.resolve().parent != sessions_dir.resolve():
        raise CrossReviewError(
            f"refusing to use {display_path(session_dir)}: outside the session cache"
        )
    review = next((message for message in messages if message.kind == "review"), messages[0])
    peer = review.author
    peer_session = None
    for message in reversed(messages):
        if message.fields.get("peer_session") not in (None, "", "none"):
            peer_session = message.fields["peer_session"]
            break
    head = ""
    model = None
    for message in messages:
        if not head and message.fields.get("head") not in (None, "", "none"):
            head = message.fields["head"]
        if model is None and message.fields.get("model") not in (None, "", "default"):
            model = message.fields["model"]
    rounds = sorted({message.round for message in messages if message.kind in {"review", "reply"}})
    concluded = any(message.kind == "report" for message in messages)
    if (session_dir / "session.json").is_file():
        session = load_session(session_dir)
        reconcile_session(
            session_dir,
            session,
            messages,
            peer_session=peer_session,
            rounds=rounds,
            concluded=concluded,
        )
        return session_dir
    session_dir.mkdir(parents=True, exist_ok=True)
    session = {
        "name": name,
        "peer": peer,
        "host": default_peer(peer),
        "peer_session_id": peer_session,
        "model": model,
        "scope": {"branch": None, "head": head, "base": None, "merge_base": None, "commit": None},
        "focus": None,
        "target": target.to_json(),
        "record": target.kind,
        "usage": {},
        "approved": False,
        "budget": BUDGET_FULL,
        "created_at": now.isoformat(timespec="seconds"),
        "imported_from": target.url,
        "rounds": [{"number": number, "status": "ok"} for number in rounds],
        "messages": [],
        "concluded": concluded,
    }
    for message in messages:
        add_message(session_dir, session, message)
    save_session(session_dir, session)
    return session_dir


def select_session(messages: list[Message]) -> tuple[str, list[Message]]:
    """One PR can carry several exchanges; take the newest session and only its messages."""
    names = sorted(
        {message.fields.get("session", "") for message in messages if message.fields.get("session")}
    )
    if not names:
        raise CrossReviewError("no cross-review comments carry a valid session marker")
    chosen = names[-1]
    return chosen, [message for message in messages if message.fields.get("session") == chosen]


def message_sort_key(entry: dict) -> tuple[int, int]:
    return int(entry["round"]), MESSAGE_KINDS.index(entry["kind"]) if entry[
        "kind"
    ] in MESSAGE_KINDS else 9


def reconcile_session(
    session_dir: Path,
    session: dict,
    messages: list[Message],
    *,
    peer_session: str | None,
    rounds: list[int],
    concluded: bool,
) -> None:
    """Fold what GitHub holds into the cache: new messages, their URLs, completed rounds, the closing state."""
    entries = session.setdefault("messages", [])
    for message in messages:
        match = next(
            (
                entry
                for entry in entries
                if int(entry["round"]) == message.round
                and entry["kind"] == message.kind
                and entry["author"] == message.author
            ),
            None,
        )
        if match is None:
            add_message(session_dir, session, message)
        elif not match.get("comment_url"):
            match["comment_url"] = message.comment_url
    entries.sort(key=message_sort_key)
    by_number = {int(info["number"]): info for info in session.get("rounds", [])}
    for number in rounds:
        info = by_number.get(number)
        if info is None:
            session.setdefault("rounds", []).append({"number": number, "status": "ok"})
        elif info.get("status") != "ok":
            info["status"] = "ok"
    session["rounds"].sort(key=lambda info: int(info["number"]))
    if peer_session and not session.get("peer_session_id"):
        session["peer_session_id"] = peer_session
    session["concluded"] = bool(session.get("concluded")) or concluded
    save_session(session_dir, session)


def open_session(
    args: argparse.Namespace,
    *,
    repo_root: Path,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
) -> tuple[Path, dict]:
    sessions_dir = sessions_dir_for(repo_root)
    pr = getattr(args, "pr", None)
    issue = getattr(args, "issue", None)
    if args.session is None and not args.last and (pr or issue):
        target, _ = resolve_target(repo_root, runner, env, pr=pr, issue=issue, no_post=False)
        if target is None:
            raise CrossReviewError("no GitHub repo found here, so --pr and --issue cannot be used")
        session_dir = import_session(
            target, sessions_dir, cwd=repo_root, runner=runner, env=env, now=now
        )
    else:
        session_dir = resolve_session(sessions_dir, args.session, args.last)
    return session_dir, load_session(session_dir)


# ------------------------------------------------------------------------------------------------------
# findings


def finding_state(peer_verdicts: Mapping[int, str], host_verdicts: Mapping[int, str]) -> str:
    """Agreed only when the host's AGREE comes in a later round than the peer's last REVISE.

    The host answers before the peer in each round, so a REVISE in the same round as an AGREE reopens
    the finding, and a later HOLD does not close it again on its own.
    """
    last_peer_round = max(peer_verdicts, default=0)
    if peer_verdicts.get(last_peer_round) == "CONCEDE":
        return "dropped"
    last_revise_round = max(
        (number for number, verdict in peer_verdicts.items() if verdict == "REVISE"), default=0
    )
    last_host_round = max(host_verdicts, default=0)
    if host_verdicts.get(last_host_round) == "AGREE" and last_host_round > last_revise_round:
        return "agreed"
    return "open"


def finding_blocks(text: str) -> list[tuple[str, str, str, str]]:
    matches = list(FINDING_RE.finditer(text))
    blocks = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        section_end = BLOCK_END_RE.search(block)
        if section_end:
            block = block[: section_end.start()]
        claim = ""
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("claim:"):
                claim = stripped.partition(":")[2].strip()
                break
            if stripped and not claim:
                claim = stripped
        number, severity, location = match.groups()
        blocks.append((number, severity, location, claim))
    return blocks


def parse_verdicts(messages: Iterable[Message]) -> dict[str, dict]:
    findings: dict[str, dict] = {}

    def slot(number: str) -> dict:
        return findings.setdefault(
            number,
            {
                "severity": "?",
                "location": "?",
                "claim": "",
                "first_round": None,
                "peer": {},
                "host": {},
                "revised": {},
            },
        )

    for message in messages:
        if message.kind in {"review", "reply"}:
            for number, severity, location, claim in finding_blocks(message.text):
                finding = slot(number)
                finding["severity"] = severity
                finding["location"] = location
                if claim and not finding["claim"]:
                    finding["claim"] = claim
                if finding["first_round"] is None:
                    finding["first_round"] = message.round
            for number, verdict, severity in PEER_VERDICT_RE.findall(message.text):
                finding = slot(number)
                finding["peer"][message.round] = verdict
                if severity:
                    finding["severity"] = severity
                    finding["revised"][message.round] = severity
        elif message.kind == "response":
            for number, verdict in HOST_VERDICT_RE.findall(message.text):
                slot(number)["host"][message.round] = verdict
    for finding in findings.values():
        finding["state"] = finding_state(finding["peer"], finding["host"])
    return dict(sorted(findings.items(), key=lambda item: int(item[0][1:])))


def next_finding_number(messages: Iterable[Message]) -> int:
    highest = 0
    for message in messages:
        for match in FINDING_RE.finditer(message.text):
            highest = max(highest, int(match.group(1)[1:]))
    return highest + 1


def rounds_done(session: dict) -> int:
    return sum(1 for round_info in session.get("rounds", []) if round_info.get("status") == "ok")


def read_message(tokens: list[str] | None, file_path: str | None) -> str:
    if file_path:
        if file_path == "-":
            return sys.stdin.read()
        path = Path(file_path)
        if not path.is_file():
            raise CrossReviewError(f"message file not found: {file_path}")
        return path.read_text(encoding="utf-8")
    if tokens:
        return " ".join(tokens)
    raise CrossReviewError(
        "give the message with --file PATH (or --file - for stdin) or --message WORD..."
    )


# ------------------------------------------------------------------------------------------------------
# commands


def apply_usage_gate(
    session: dict | None,
    env: Mapping[str, str],
    now_epoch: float,
    *,
    claude_manual: float | None,
    codex_manual: float | None,
    approved: bool,
) -> tuple[dict[str, UsageReading], int]:
    thread = session.get("peer_session_id") if session and session.get("peer") == "codex" else None
    readings = read_usage(
        env, now_epoch, claude_manual=claude_manual, codex_manual=codex_manual, codex_thread=thread
    )
    budget = round_budget(worst_usage(readings), approved)
    if session is not None and session.get("budget"):
        budget = min(budget, int(session["budget"]))
    return readings, budget


def codex_home_for(env: Mapping[str, str]) -> Path:
    return Path(env.get("CODEX_HOME") or Path.home() / ".codex")


def peer_round(
    session_dir: Path,
    session: dict,
    round_number: int,
    prompt: str,
    *,
    kind: str,
    repo_root: Path,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    timeout_s: float,
) -> tuple[int, dict | None]:
    """Run one peer turn: returns the exit code and the entry for the peer's text (None on failure)."""
    peer = session["peer"]
    request_path = session_dir / f"round-{round_number:02d}-request.md"
    request_path.write_text(prompt, encoding="utf-8", newline="\n")
    output_path = session_dir / f"round-{round_number:02d}-{kind}.md"
    error_path = session_dir / f"round-{round_number:02d}-error.txt"
    started = datetime.datetime.now()
    round_info = {
        "number": round_number,
        "status": "running",
        "started_at": now.isoformat(timespec="seconds"),
    }
    session["rounds"] = [
        info for info in session.get("rounds", []) if info.get("number") != round_number
    ]
    session["rounds"].append(round_info)
    save_session(session_dir, session)
    try:
        reply = call_peer(
            peer,
            prompt,
            cwd=repo_root,
            output_path=output_path,
            model=session.get("model"),
            resume_id=session.get("peer_session_id"),
            timeout_s=timeout_s,
            runner=runner,
            env=env,
        )
    except subprocess.TimeoutExpired:
        round_info["status"] = "failed"
        round_info["duration_s"] = round((datetime.datetime.now() - started).total_seconds(), 1)
        error_path.write_text(
            f"timed out after {timeout_s:.0f} s\n", encoding="utf-8", newline="\n"
        )
        save_session(session_dir, session)
        print(
            f"cross-review: {LABELS[peer]} timed out after {timeout_s:.0f} s; see {display_path(error_path)}",
            file=sys.stderr,
        )
        return EXIT_TIMEOUT, None
    round_info["duration_s"] = round((datetime.datetime.now() - started).total_seconds(), 1)
    round_info["cost_usd"] = reply.cost_usd
    round_info["permission_denials"] = reply.permission_denials
    if reply.session_id and not session.get("peer_session_id"):
        session["peer_session_id"] = reply.session_id
    if reply.failure:
        round_info["status"] = "failed"
        error_path.write_text(
            f"{reply.failure}\n\n--- stdout ---\n{reply.stdout[-4000:]}\n\n--- stderr ---\n{reply.stderr[-4000:]}\n",
            encoding="utf-8",
            newline="\n",
        )
        save_session(session_dir, session)
        print(
            f"cross-review: {LABELS[peer]} failed: {reply.failure}; see {display_path(error_path)}",
            file=sys.stderr,
        )
        return EXIT_PEER_FAILED, None
    round_info["status"] = "ok"
    entry = add_message(
        session_dir, session, Message(round_number, kind, peer, "reviewer", reply.text)
    )
    if peer == "codex":
        after = read_codex_usage(
            codex_home_for(env), datetime.datetime.now().timestamp(), session["peer_session_id"]
        )
        session.setdefault("usage", {})["after"] = {"codex": after.to_json()}
    save_session(session_dir, session)
    return EXIT_OK, entry


def print_round_summary(session: dict, round_info: dict, entry: dict | None) -> None:
    duration = format_span(round_info.get("duration_s") or 0)
    cost = round_info.get("cost_usd")
    cost_text = f"${cost:.2f}" if isinstance(cost, (int, float)) else "plan quota"
    line = f"round {round_info['number']}: {duration}   cost: {cost_text}"
    if round_info.get("permission_denials"):
        line += f"   permission denials: {round_info['permission_denials']}"
    print(line)
    if entry and entry.get("comment_url"):
        print(f"comment: {entry['comment_url']}")
    elif entry and session.get("record") == "no-post":
        print("comment: not posted (--no-post); run `post` later")


def print_session_header(session: dict, session_dir: Path) -> None:
    print(f"session: {session['name']}")
    print(f"dir: {display_path(session_dir)}")
    peer_id = session.get("peer_session_id") or "pending"
    print(
        f"peer: {LABELS[session['peer']]} (session {peer_id})   model: {session.get('model') or 'default'}"
    )
    target = session_target(session)
    print(
        f"target: {target.describe() if target else 'none (' + str(session.get('record', 'unknown')) + ')'}"
    )
    worst = (session.get("usage") or {}).get("worst_percent")
    worst_text = "unknown" if worst is None else f"{worst:.0f}%"
    print(
        f"budget: {session.get('budget')} rounds   usage worst: {worst_text}   rounds done: {rounds_done(session)}"
    )
    banner = banner_for(session, session_dir)
    if banner:
        print(banner)


def print_peer_text(session_dir: Path, entry: dict | None) -> None:
    if entry is None:
        return
    print()
    print((session_dir / entry["file"]).read_text(encoding="utf-8").rstrip("\n"))


def cmd_usage(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    now_epoch = now.timestamp()
    readings, budget = apply_usage_gate(
        None,
        env,
        now_epoch,
        claude_manual=args.claude_usage,
        codex_manual=args.codex_usage,
        approved=args.approve_usage,
    )
    print(render_usage(readings, budget, now_epoch))
    return EXIT_OK


def cmd_start(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    host = detect_host(env)
    peer = args.peer or default_peer(host)
    if peer == "claude" and env.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        raise CrossReviewError(
            "network is disabled in this sandbox, so Claude Code cannot run; rerun with escalated permissions",
            EXIT_SANDBOXED,
        )
    now_epoch = now.timestamp()
    readings, budget = apply_usage_gate(
        None,
        env,
        now_epoch,
        claude_manual=args.claude_usage,
        codex_manual=args.codex_usage,
        approved=args.approve_usage,
    )
    print(render_usage(readings, budget, now_epoch))
    if budget == 0 and not args.dry_run:
        worst = worst_usage(readings)
        detail = "a usage reading is unknown" if worst is None else f"usage is at {worst:.0f}%"
        raise CrossReviewError(
            f"{detail}; this needs the user's explicit approval. Rerun with --approve-usage after they say "
            "yes, or pass --claude-usage N / --codex-usage N with numbers they read from /usage and /status",
            EXIT_BUDGET,
        )
    scope = resolve_scope(args.base, args.commit, repo_root)
    bundle = collect_diff(scope, repo_root)
    if bundle.is_empty:
        raise CrossReviewError("nothing to review: the diff is empty")
    focus = " ".join(args.focus) if args.focus else None
    if args.dry_run:
        target, record = None, "dry-run"
    else:
        target, record = resolve_target(
            repo_root, runner, env, pr=args.pr, issue=args.issue, no_post=args.no_post
        )
    session_dir = new_session_dir(sessions_dir_for(repo_root), peer, now)
    patch_path = session_dir / PATCH_FILENAME
    patch_path.write_text(bundle.diff, encoding="utf-8", newline="\n")
    brief = render_review_brief(scope, bundle, host, focus, patch_path)
    session = {
        "name": session_dir.name,
        "peer": peer,
        "host": host,
        "host_session_id": env.get("CLAUDE_CODE_SESSION_ID"),
        "peer_session_id": None,
        "model": args.model,
        "scope": scope.to_json(),
        "focus": focus,
        "target": target.to_json() if target else None,
        "record": record,
        "usage": {
            "before": {agent: reading.to_json() for agent, reading in readings.items()},
            "worst_percent": worst_usage(readings),
        },
        "approved": bool(args.approve_usage),
        "budget": budget,
        "created_at": now.isoformat(timespec="seconds"),
        "rounds": [],
        "messages": [],
        "concluded": False,
    }
    save_session(session_dir, session)
    if args.dry_run:
        brief_path = session_dir / "round-01-request.md"
        brief_path.write_text(brief, encoding="utf-8", newline="\n")
        print_session_header(session, session_dir)
        print(f"dry run: the brief is in {display_path(brief_path)}; the peer was not called")
        return EXIT_OK
    code, entry = peer_round(
        session_dir,
        session,
        1,
        brief,
        kind="review",
        repo_root=repo_root,
        runner=runner,
        env=env,
        now=now,
        timeout_s=args.timeout,
    )
    if code != EXIT_OK:
        print_session_header(session, session_dir)
        return code
    if entry is not None:
        post_entry(session_dir, session, entry, cwd=repo_root, runner=runner, env=env)
    print_session_header(session, session_dir)
    print_round_summary(session, session["rounds"][-1], entry)
    print_peer_text(session_dir, entry)
    return EXIT_OK


def cmd_reply(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    session_dir, session = open_session(args, repo_root=repo_root, runner=runner, env=env, now=now)
    banner = banner_for(session, session_dir)
    if banner:
        print(banner)
    if session.get("concluded"):
        raise CrossReviewError(
            f"session {session['name']} is concluded; start a new review instead"
        )
    if not session.get("peer_session_id"):
        raise CrossReviewError(
            "the peer never answered in this session (start failed); run start again"
        )
    message = read_message(args.message, args.file)
    if not message.strip():
        raise CrossReviewError("the message is empty")
    messages = load_messages(session_dir, session)
    answered = {number for number, _verdict in HOST_VERDICT_RE.findall(message)}
    if not answered:
        print(
            "warning: no `F<n>: AGREE | DISPUTE | PARTIAL` lines in the message, so status cannot track it",
            file=sys.stderr,
        )
    skipped = [
        number
        for number, finding in parse_verdicts(messages).items()
        if finding["state"] == "open" and number not in answered
    ]
    if answered and skipped:
        print(f"warning: no verdict for {', '.join(skipped)} (still open)", file=sys.stderr)
    if args.approve_usage:
        session["approved"] = True
    readings, budget = apply_usage_gate(
        session,
        env,
        now.timestamp(),
        claude_manual=args.claude_usage,
        codex_manual=args.codex_usage,
        approved=bool(session.get("approved")),
    )
    session["budget"] = budget
    usage = session.setdefault("usage", {})
    usage["latest"] = {agent: reading.to_json() for agent, reading in readings.items()}
    usage["worst_percent"] = worst_usage(readings)
    save_session(session_dir, session)
    if budget == 0:
        worst = worst_usage(readings)
        detail = "a usage reading is unknown" if worst is None else f"usage is at {worst:.0f}%"
        raise CrossReviewError(
            f"{detail}; this needs the user's explicit approval. Rerun with --approve-usage after they say yes",
            EXIT_BUDGET,
        )
    done = rounds_done(session)
    if done >= budget and not args.force:
        raise CrossReviewError(
            f"{done} of {budget} rounds used; the budget is spent. --force overrides it only with the user's "
            "explicit yes"
        )
    last_round = session["rounds"][-1] if session.get("rounds") else None
    if last_round and last_round.get("status") != "ok":
        round_number = int(last_round["number"])
    else:
        round_number = done + 1
    existing = None
    for entry in session.get("messages", []):
        if entry["kind"] != "response" or int(entry["round"]) != round_number:
            continue
        if (session_dir / entry["file"]).read_text(encoding="utf-8").strip() == message.strip():
            existing = entry
    if existing is None:
        session["messages"] = [
            entry
            for entry in session.get("messages", [])
            if not (entry["kind"] == "response" and int(entry["round"]) == round_number)
        ]
        response = Message(round_number, "response", session["host"], "responder", message)
        existing = add_message(session_dir, session, response)
    save_session(session_dir, session)
    post_entry(session_dir, session, existing, cwd=repo_root, runner=runner, env=env)
    prompt = render_discussion(message, next_finding_number(messages))
    code, entry = peer_round(
        session_dir,
        session,
        round_number,
        prompt,
        kind="reply",
        repo_root=repo_root,
        runner=runner,
        env=env,
        now=now,
        timeout_s=args.timeout,
    )
    if code != EXIT_OK:
        print_session_header(session, session_dir)
        return code
    if entry is not None:
        post_entry(session_dir, session, entry, cwd=repo_root, runner=runner, env=env)
    print_session_header(session, session_dir)
    print_round_summary(session, session["rounds"][-1], entry)
    print_peer_text(session_dir, entry)
    return EXIT_OK


def cmd_conclude(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    session_dir, session = open_session(args, repo_root=repo_root, runner=runner, env=env, now=now)
    banner = banner_for(session, session_dir)
    if banner:
        print(banner)
    if session.get("concluded"):
        raise CrossReviewError(f"session {session['name']} already has a consensus report")
    report = read_message(None, args.file)
    if not report.strip():
        raise CrossReviewError("the report is empty")
    round_number = max((int(info["number"]) for info in session.get("rounds", [])), default=1)
    entry = add_message(
        session_dir, session, Message(round_number, "report", session["host"], "responder", report)
    )
    session["concluded"] = True
    save_session(session_dir, session)
    url = post_entry(session_dir, session, entry, cwd=repo_root, runner=runner, env=env)
    print_session_header(session, session_dir)
    print(f"report: {url or 'saved locally in ' + display_path(session_dir / entry['file'])}")
    return EXIT_OK


def cmd_post(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    session_dir = resolve_session(sessions_dir_for(repo_root), args.session, args.last)
    session = load_session(session_dir)
    if args.pr or args.issue:
        target, record = resolve_target(
            repo_root, runner, env, pr=args.pr, issue=args.issue, no_post=False
        )
        if target is None:
            raise CrossReviewError("no GitHub repo found here, so there is nowhere to post")
        stored = session_target(session)
        if stored is not None and (stored.kind, stored.number) != (target.kind, target.number):
            raise CrossReviewError(
                f"this session is recorded on {stored.describe()}; comments are not moved to "
                f"{target.describe()}"
            )
        session["target"] = target.to_json()
        session["record"] = record
        save_session(session_dir, session)
    target = session_target(session)
    if target is None:
        banner = banner_for(session, session_dir)
        raise CrossReviewError(
            banner or "this session has no PR or issue; pass --pr N or --issue N"
        )
    posted = 0
    for entry in session.get("messages", []):
        if entry.get("comment_url"):
            continue
        url = post_entry(session_dir, session, entry, cwd=repo_root, runner=runner, env=env)
        posted += 1
        print(f"posted round {entry['round']} {entry['kind']}: {url}")
    on_target = sum(1 for entry in session.get("messages", []) if entry.get("comment_url"))
    total = len(session.get("messages", []))
    print(f"{posted} comment(s) posted; {on_target} of {total} messages on {target.describe()}")
    return EXIT_OK


def cmd_status(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    session_dir, session = open_session(args, repo_root=repo_root, runner=runner, env=env, now=now)
    print_session_header(session, session_dir)
    findings = parse_verdicts(load_messages(session_dir, session))
    if not findings:
        print("findings: none parsed yet")
    for number, finding in findings.items():
        peer_text = (
            ", ".join(f"{verdict} (r{rnd})" for rnd, verdict in sorted(finding["peer"].items()))
            or "raised"
        )
        host_text = (
            ", ".join(f"{verdict} (r{rnd})" for rnd, verdict in sorted(finding["host"].items()))
            or "-"
        )
        print(
            f"{number:<4} {finding['severity']:<7} {finding['location']:<40} {finding['state']:<8} "
            f"peer: {peer_text}   host: {host_text}   first claim: {finding['claim']}"
        )
    counts = {
        state: sum(1 for finding in findings.values() if finding["state"] == state)
        for state in ("agreed", "dropped", "open")
    }
    posted = sum(1 for entry in session.get("messages", []) if entry.get("comment_url"))
    concluded = "yes" if session.get("concluded") else "no"
    print(
        f"agreed: {counts['agreed']}   dropped: {counts['dropped']}   open: {counts['open']}   "
        f"posted: {posted} of {len(session.get('messages', []))} messages   concluded: {concluded}"
    )
    return EXIT_OK


def elide_diff(brief: str) -> str:
    head, separator, _ = brief.partition("\n## Diff\n")
    if not separator:
        return brief
    return head + "\n## Diff\n[diff elided; --full shows it]\n"


def cmd_transcript(
    args: argparse.Namespace,
    *,
    runner: Runner,
    env: Mapping[str, str],
    now: datetime.datetime,
    repo_root: Path,
) -> int:
    session_dir, session = open_session(args, repo_root=repo_root, runner=runner, env=env, now=now)
    print(f"# Cross-review {session['name']}")
    print_session_header(session, session_dir)
    brief_path = session_dir / "round-01-request.md"
    if brief_path.is_file():
        brief = brief_path.read_text(encoding="utf-8")
        print("\n## Round 1 brief (sent to the peer)\n")
        print(brief if args.full else elide_diff(brief))
    for message in load_messages(session_dir, session):
        print(f"\n## {message.title}\n")
        if message.comment_url:
            print(f"<{message.comment_url}>\n")
        print(message.text.rstrip("\n"))
    return EXIT_OK


# ------------------------------------------------------------------------------------------------------
# CLI


def add_usage_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--claude-usage", type=float, metavar="PCT", help="Claude usage percent from /usage"
    )
    parser.add_argument(
        "--codex-usage", type=float, metavar="PCT", help="Codex usage percent from /status"
    )
    parser.add_argument(
        "--approve-usage", action="store_true", help="the user explicitly approved 90%%+ usage"
    )


def add_session_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("session", nargs="?", help="session name under .scratch/cross-review")
    parser.add_argument("--last", action="store_true", help="the newest local session")
    parser.add_argument("--pr", type=int, help="rebuild the session from this PR's comments")
    parser.add_argument("--issue", type=int, help="rebuild the session from this issue's comments")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cross-review",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    usage = subparsers.add_parser(
        "usage", help="both agents' rate-limit usage and the round budget"
    )
    add_usage_arguments(usage)
    usage.set_defaults(func=cmd_usage)

    start = subparsers.add_parser("start", help="ask the peer for the round-1 review")
    start.add_argument("--peer", choices=PEERS)
    start.add_argument("--base", default="main", help="branch to diff against (default main)")
    start.add_argument("--commit", help="review one commit instead of the working tree")
    start.add_argument("--focus", nargs="+", help="what the reviewer should concentrate on")
    start.add_argument("--model", help="model for the peer")
    start.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds to wait for the peer"
    )
    start.add_argument("--dry-run", action="store_true", help="write the brief and stop")
    target_group = start.add_mutually_exclusive_group()
    target_group.add_argument("--pr", type=int, help="post the exchange on this PR")
    target_group.add_argument("--issue", type=int, help="post the exchange on this issue")
    target_group.add_argument(
        "--no-post", action="store_true", help="keep the exchange local (user's choice)"
    )
    add_usage_arguments(start)
    start.set_defaults(func=cmd_start)

    reply = subparsers.add_parser(
        "reply", help="send the host's per-finding response and get the peer's reply"
    )
    add_session_arguments(reply)
    reply.add_argument("--file", help="file holding the message; - reads stdin")
    reply.add_argument("--message", nargs="+", help="short message given inline")
    reply.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    reply.add_argument(
        "--force", action="store_true", help="exceed the round budget (user's explicit yes only)"
    )
    add_usage_arguments(reply)
    reply.set_defaults(func=cmd_reply)

    conclude = subparsers.add_parser(
        "conclude", help="post the consensus report as the closing comment"
    )
    add_session_arguments(conclude)
    conclude.add_argument("--file", required=True, help="file holding the report")
    conclude.set_defaults(func=cmd_conclude)

    post = subparsers.add_parser("post", help="post every message not yet on GitHub")
    post.add_argument("session", nargs="?")
    post.add_argument("--last", action="store_true")
    post.add_argument("--pr", type=int)
    post.add_argument("--issue", type=int)
    post.set_defaults(func=cmd_post)

    status = subparsers.add_parser("status", help="each finding as agreed, dropped or open")
    add_session_arguments(status)
    status.set_defaults(func=cmd_status)

    transcript = subparsers.add_parser("transcript", help="print the whole exchange")
    add_session_arguments(transcript)
    transcript.add_argument("--full", action="store_true", help="include the round-1 diff")
    transcript.set_defaults(func=cmd_transcript)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = run_process,
    env: Mapping[str, str] | None = None,
    now: datetime.datetime | None = None,
    repo_root: Path = REPO_ROOT,
) -> int:
    environment = dict(os.environ) if env is None else dict(env)
    moment = now or datetime.datetime.now()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, runner=runner, env=environment, now=moment, repo_root=repo_root)
    except CrossReviewError as error:
        print(f"cross-review: {error}", file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    sys.exit(main())
