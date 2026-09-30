---
name: cross-review
description: Ask the other AI (Codex from Claude Code, Claude Code from Codex) for an independent read-only review of the current change, verify its findings, argue the ones you disagree with over a usage-budgeted number of rounds (at most three), post every message as a comment on the PR (or the work's issue), and hand the user a consensus table. Use when the user says "cross-review", "ask codex to review this", "get a second opinion from claude", "peer review this diff", "have the other AI look at this", or wants both AIs to agree on a change before it ships. Never edits code, never commits, and never applies fixes until the user names them.
---

# Cross Review

Ask the other AI for an independent review of the current change, verify its findings yourself, argue
the ones you disagree with over at most three rounds, and hand the user a consensus table. The peer is
read-only; nothing in the working tree changes until the user says so. From Claude Code the peer is
Codex; from Codex the peer is Claude Code (`--peer` overrides). Every message in the exchange goes on
the PR as a comment, so GitHub is the record and `.scratch/cross-review/` is only a cache.

## Steps

1. **Scope.** Run `git status --short` and `git log --oneline main..HEAD`. Nothing changed: stop and say
   so. Base defaults to `main`; use `--base <branch>` for stacked work and `--commit <sha>` for one
   commit. Pass `--focus <words>` only when the user hinted at a focus.
   Decide where the record goes:
   - `gh pr view --json number,url` succeeds: the PR. Nothing else to pass.
   - No PR: find the issue for this work (`gh issue list --search "<slug>"`), or have the `pr-manager`
     agent create one with the area label, milestone and project, then pass `--issue N`.
   - `gh repo view` fails: there is no GitHub repo, so the exchange stays local and step 8 must say so.
   - `--no-post` only when the user asks for it. Never skip posting silently.
2. **Budget.** `just cross-review usage`. Show the user the two-agent table and the budget it implies
   (under 75% used: 3 rounds; 75% to 90%: 2 rounds; 90% or more, or an unknown reading: 0). Exit 5 means
   the gate is closed: ask the user. On a yes, rerun with `--approve-usage`; if a reading is unknown, ask
   them to run `/usage` (Claude) or `/status` (Codex) and pass `--claude-usage N` / `--codex-usage N`.
   Never pass `--approve-usage` or `--force` on your own.
3. **Start.** `just cross-review start [--base main] [--issue N] [--focus ...]` in the background
   (Claude: `run_in_background`; Codex: background exec with escalated permissions, because the Claude
   peer needs network and its own home directory). Reviews take 3 to 10 minutes. The output carries a
   `session: <name>` line; keep that name. Exit 2, 3 or 4: report the message and the session's
   `round-01-error.txt`, then stop.
4. **Verify every finding yourself.** For each `F<n>`, open the cited file:line and re-derive the claim
   from the code, the tests and `.claude/CLAUDE.md`. Decide AGREE (say what you will change), DISPUTE
   (cite the code path, test or rule that refutes it) or PARTIAL (which part holds). Never take the
   peer's word, and never fold on a HOLD that brings no new evidence.
5. **Reply.** Write `.scratch/cross-review/<name>/draft.md` with one block per finding, each starting
   with `F<n>: AGREE | DISPUTE | PARTIAL` on its own line and then the reasoning with file:line. Then
   `just cross-review reply <name> --file .scratch/cross-review/<name>/draft.md` in the background, for
   the same reason as step 3. Never pass long text on the command line; `just` re-splits it.
6. **Loop.** `just cross-review status <name>` lists each finding as agreed, dropped or open. While any
   finding is open and rounds remain in the budget, repeat steps 4 and 5 on the open findings only. Stop
   early when nothing is open. The script refuses a round past the budget.
7. **Conclude.** Write the report below to `.scratch/cross-review/<name>/report.md` and run
   `just cross-review conclude <name> --file .scratch/cross-review/<name>/report.md` so it lands on
   the PR or issue as the closing comment.
8. **Report and stop.** Give the user the same report plus the comment links, then
   `Transcript: just cross-review transcript <name>` and `Nothing was changed. Say which fixes to apply.`
   When the session has no GitHub target, open with `Not recorded on GitHub: no repo found. The full
   exchange is below.` and paste the complete transcript into the chat so nothing depends on the
   scratch directory. No fixes, no commit, no new review.

Resuming later: `just cross-review transcript --pr N` (or `--issue N`) rebuilds the exchange from the
marked comments, and `just cross-review reply --pr N --file ...` continues it with the peer session id
recovered from the last comment.

## Report format

| # | Sev | Where | Finding | Peer | Me | Outcome |
|---|---|---|---|---|---|---|
| F1 | HIGH | src/x.py:42 | one line | HOLD | AGREE | Fix |
| F2 | LOW | src/x.py:7 | one line | CONCEDE | DISPUTE | Dropped |
| F3 | MEDIUM | src/y.py:15 | one line | HOLD | DISPUTE | Your call |

Below the table: `Agreed fixes:` (what changes, one line each), `Dropped:` (why, one line each),
`Unresolved:` (both positions, one line each), the usage line for both agents before and after, then
the transcript command and the closing sentence.

## Notes

- The PR (or issue) is the record and the local session only a cache. Every comment is posted from the
  user's GitHub account, so the heading names the speaker: `Cross-review round 2 reply by Codex
  (reviewer)`. The HTML marker under it is what `status`, `transcript --pr` and `post` read.
- Sessions live in `.scratch/cross-review/` (gitignored). `--last` means the newest one; pass the
  session name whenever more than one review may be running.
- The peer is read-only: `codex exec -s read-only`, or `claude -p` limited to Read, Grep and Glob under
  `--permission-mode dontAsk` (no Bash, so no `git diff --output` writes). A `permission denials: n`
  line means it tried something else; mention it in the report if it seems to have limited the review.
- The full diff is saved as `round-01-diff.patch` in the session directory. Over 120k characters it is
  not inlined in the brief; the peer reads the patch file and the working tree, and the review is slower.
- Exit 4 (Codex host): the sandbox has no network; rerun with escalated permissions.
- Claude peer rounds print their cost; Codex rounds spend plan quota. Both count against the budget.
- Claude usage comes from the snapshot the status line writes to `~/.claude/rate-limits.json`; Codex
  usage from its session logs. A missing snapshot reads as unknown, which closes the gate.
