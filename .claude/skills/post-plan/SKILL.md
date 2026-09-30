---
name: post-plan
description: Post the current implementation plan or work summary to GitHub using the gh CLI — by default creating a new issue, or commenting on a PR/issue when one is named. Use when the user says "post-plan", "post this plan to an issue", "open an issue for this plan", "capture this plan on GitHub", or otherwise wants a plan or work summary tracked on GitHub.
---

# Post Plan to GitHub

Turn the current plan (or a work summary) into a tracked GitHub artifact using
the `gh` CLI. Defaults to **creating a new issue**; comment on a PR or existing
issue only when the user names one. `gh` uses the user's local GitHub auth
automatically — never handle tokens yourself.

## Steps

1. **Identify the repository.**
   - Run `git remote get-url origin` and convert it to `owner/repo` form.
   - If safe-directory checks block git, use
     `git -c safe.directory=<repo-path> remote get-url origin`.

2. **Choose the target.**
   - **Default: a new issue.**
   - If the user gave a **PR number**, verify and comment on it instead:
     `gh pr view <n> --repo <owner/repo> --json number,title,state,url`
   - If the user gave an **issue number**, comment on that issue:
     `gh issue view <n> --repo <owner/repo> --json number,title,state,url`

3. **Prepare the body.**
   - Use the current plan if one exists (the plan file or the approved plan in
     this conversation); otherwise summarize local work: summary, key changes,
     validation steps, follow-ups.
   - **Sanitize:** strip secrets and `.env` values, and replace machine-specific
     absolute paths (e.g. `C:\Users\<user>\...`, `/home/<user>/...`) with
     repo-relative paths. Keep `.claude/...`-style paths.
   - Follow the Issue Body Template below when creating an issue.

4. **Create or comment.**
   - Write the body to a temp file **outside the repo** (e.g.
     `$env:TEMP\post-plan-body.md`), never inside the working tree, then:
     - New issue: `gh issue create --repo <owner/repo> --title "<title>" --body-file <tmp>`
     - PR comment: `gh pr comment <n> --repo <owner/repo> --body-file <tmp>`
     - Issue comment: `gh issue comment <n> --repo <owner/repo> --body-file <tmp>`
   - Delete the temp file afterward. Report the URL `gh` prints.

5. **Optional follow-up issues.**
   - Only for clearly actionable items the user asked to capture, or explicit
     future work / failed validation. Search for dupes first:
     `gh issue list --repo <owner/repo> --state open --search "<keywords>" --json number,title,url`
   - Create one issue per item; link it back to the primary issue/PR; include
     acceptance criteria. Skip vague ideas.

6. **Final response.**
   - Report the created issue (or comment) URL.
   - List any follow-up issue URLs, or state none were created.
   - Note skipped candidates and why (duplicate, too vague).

## Issue Body Template

```markdown
## Summary

<what should be done / what this plan covers>

## Context

<why — the problem or motivation>

## Acceptance Criteria

- [ ] <observable outcome>
- [ ] <tests / docs / validation if relevant>
```

## Notes

- Never commit the temp body file — keep it outside the repo and delete it after.
- `gh` uses the user's local GitHub authentication automatically.
- Don't pass `--label` unless the label already exists on the repo (it errors otherwise).
- Default title: a short imperative summary of the plan; ask the user if ambiguous.
