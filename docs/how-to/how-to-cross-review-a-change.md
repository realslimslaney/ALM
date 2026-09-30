# How to Cross-Review a Change with the Other AI

Have the other AI review the current branch, let the host AI argue the findings with it, and keep the
whole exchange on the PR. From Claude Code the reviewer is Codex; from Codex the reviewer is Claude
Code. The reviewer runs read-only, the discussion is capped by both agents' rate-limit usage, and
nothing is edited until you name the fixes to apply.

## Prerequisites

- Both CLIs on `PATH` and logged in to your subscriptions: `codex login status` and
  `claude auth status`. The Claude reviewer never receives `ANTHROPIC_API_KEY`, even though `just`
  loads it from `.env`, so its rounds draw on your Claude plan rather than API credits.
- `gh` authenticated for the repo (`gh auth status`); comments post from your account.
- The Claude usage snapshot. Claude Code hands its rate-limit percentages only to the status line, so
  the status-line command in `~/.claude/settings.json` writes them to `~/.claude/rate-limits.json`
  each time it runs. Without that file the Claude reading is unknown and the usage gate stays closed
  until you pass `--claude-usage N` from `/usage`.

## Run it

In Claude Code say `/cross-review`; in Codex invoke the mirrored `cross-review` skill. The host then:

1. Checks the scope and finds the PR for the branch.
2. Runs `just cross-review usage` and shows you both agents' usage and the round budget.
3. Runs `just cross-review start`, which sends the reviewer a brief with the diff and posts the review
   on the PR.
4. Verifies each finding against the code, writes a per-finding response, and runs
   `just cross-review reply <session> --file <draft>`; the response and the reviewer's reply both land
   on the PR.
5. Repeats while findings are open and rounds remain, then posts a consensus report with
   `just cross-review conclude` and stops.

A round takes 3 to 10 minutes. Expect the whole exchange to take 10 to 30 minutes.

## Commands

| Command | Purpose |
|---|---|
| `just cross-review usage` | Both agents' usage and the budget it implies. |
| `just cross-review start [--base main] [--commit SHA] [--focus WORDS] [--pr N \| --issue N \| --no-post]` | Round 1. |
| `just cross-review reply <session> --file PATH` | One discussion round. `--last` picks the newest session. |
| `just cross-review conclude <session> --file PATH` | Posts the consensus report. |
| `just cross-review post <session> [--pr N \| --issue N]` | Posts anything not yet on GitHub. |
| `just cross-review status <session>` | Each finding as agreed, dropped or open. |
| `just cross-review transcript <session> [--full]` | The whole exchange; `--pr N` rebuilds it from GitHub. |

`--claude-usage N`, `--codex-usage N` and `--approve-usage` override the usage gate; the host passes
them only after you say so.

## The usage budget

| Worst reading across both agents | Rounds |
|---|---|
| under 75% | 3 (the review plus two discussion rounds) |
| 75% to under 90% | 2 |
| 90% or more, or unknown | 0 until you approve; then 2 |

The worst reading is the highest percentage over the 5-hour and weekly windows of both agents. Codex
usage is read from its newest session log; Claude usage from the snapshot above. A reading is a lower
bound inside its window, and a window past its reset time counts as 0%.

## Where the record lives

Every message is a comment on the PR: the review, each response, each reply, and the report. The
heading names the speaker (`Cross-review round 2 reply by Codex (reviewer)`) because all comments
post from your account. The HTML marker under the heading carries the session name, round, author,
reviewer session id and the reviewed commit, which is how `transcript --pr N` rebuilds the exchange
and `reply --pr N` continues it in a later session.

- No PR yet: pass `--issue N` with the issue for the work (the host creates one with
  `gh issue create` if needed).
- A session without a target (started with `--no-post`, or before the PR existed):
  `just cross-review post <session> --pr N` catches up. A session already recorded on an issue or PR
  stays there; `post` refuses to move comments to a different target.
- No GitHub repo: the exchange stays under `.scratch/cross-review/<session>/`, every command prints
  `NOT RECORDED ON GITHUB`, and the host pastes the full transcript into the chat.

## If it stops

| Exit | Meaning | What to do |
|---|---|---|
| 1 | Config or usage error (empty diff, missing CLI, bad session, budget spent) | Read the message. |
| 2 | The reviewer failed | See `round-NN-error.txt` in the session directory. |
| 3 | The reviewer timed out (default 30 minutes) | Rerun with `--timeout`. |
| 4 | Codex sandbox has no network | Rerun the command with escalated permissions. |
| 5 | Usage gate | Approve with `--approve-usage`, or give the numbers. |

## Limits

- The full diff is saved as `round-01-diff.patch` in the session directory. Over 120k characters it
  is not inlined in the brief, and the reviewer reads the patch file instead.
- At most ten findings per review, three rounds per session, and one report per session.
- The reviewer cannot edit, commit, or reach outside the repository.
- Comments over 65k characters post as numbered parts under the same marker.
