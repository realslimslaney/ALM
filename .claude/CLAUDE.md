# ALM

Educational Asset-Liability Management (ALM) toolkit for a life insurer: liabilities (SPIA,
whole life, term, fixed indexed annuity), backing assets (government and corporate bonds,
mortgage loans, private credit), interest-rate swaps, and the duration/convexity hedging that
keeps surplus stable when rates move. Built as a personal project for illustration; not for
professional use or financial advice. The repo is public and read by finance professionals,
so every label and number must be defensible.

## Layout

```
ALM/
├── src/alm/                 # importable package (installed editable by `uv sync`)
│   ├── asset.py             # Bond, Mortgage, PrivateCredit: cash flows, PV, duration, convexity
│   ├── liability.py         # SPIA, WL, Term, FIA policies; qx_from_table
│   ├── core.py              # SAA, Block, InterestRateSwap, dv01, dollar_convexity, immunize, irr
│   ├── option.py            # Black-Scholes European options (FIA crediting as a call spread)
│   ├── read.py              # FRED Treasury rates and credit spreads; SOA 2012 IAM table
│   ├── plot.py              # plotly line/bar/area helpers
│   └── utils.py             # get_project_root
├── scripts/                 # run_alm_demonstration.py; cross_review.py; sync_codex_skills.py
├── quarto/                  # ua_presentation.qmd (flagship deck); convexity-hedging.qmd (appendix)
├── docs/                    # MkDocs site (Diataxis): how-to/, reference/ (ref-*.qmd execute code)
├── assumptions/             # credit_spreads.csv: FRED snapshot, written only by `just refresh-spreads`
├── data/soa_tables/         # SOA 2012 IAM Basic ANB, tables 2581 (male) and 2582 (female)
├── tests/                   # pytest; synthetic data; FRED mocked; no network
├── .claude/                 # CLAUDE.md, agents/, skills/, hooks/, settings.json
├── .codex/agents/           # hand-written Codex ports of committer and pr-manager
└── .agents/skills/          # generated Codex mirrors of .claude/skills (never hand-edit)
```

## Conventions

- **Python 3.12+** (`requires-python`); CI tests 3.12 and 3.13.
- **Polars, not pandas.** Functions return polars DataFrames; expressions over row loops.
- Type hints on every public function; docstrings state the rate basis (annual effective vs
  nominal compounded `frequency` times) and units (DV01 per bp, duration in years).
- `pathlib.Path`; `alm.utils.get_project_root()` for repo-relative paths.
- Line length 100 (`[tool.ruff]` is authoritative); rules E, W, F, I, UP, B, SIM.
- Reusable logic goes in `src/alm/`; scripts are entry points only.
- **Version bumps**: raise `version` in `pyproject.toml` whenever dependencies change or a
  breaking API change lands (minor for deps/features, patch for constraints, major for
  breaking).

## Domain rules (binding for code, docs, and reports)

- Assets are valued at their own yield or purchase price, never at the risk-free rate.
- Government bonds carry zero credit spread; the Treasury curve is the benchmark.
- DV01 (via `core.dv01`) is the risk measure for net cash flows and swaps. Macaulay duration
  is never computed on a WL/Term net liability or on a swap (PV is ~0 and the result is
  meaningless).
- "Immunization" means Redington (PV, duration, and convexity conditions). `immunize()` is
  "DV01 + dollar-convexity matching for parallel shifts"; say so.
- Short-duration liability blocks (`term_saa`) tilt toward government bonds; long-duration
  blocks (`spia_saa`) tilt toward corporates and private credit.
- A yield on promised cash flows with zero defaults is a promised yield, not an expected
  return.
- Mortality is SOA 2012 IAM Basic (annuitant, no improvement); say so wherever it prices
  life products.
- Every number printed in a doc, README, or report is produced by code, never hand-typed.
- Reports never fetch FRED. `just refresh-spreads` is the only writer of
  `assumptions/credit_spreads.csv`; a render must succeed offline without `FRED_API_KEY`.

## Tooling

- **uv only**: `uv sync`, `uv add`, `uv add --dev`, `uv remove`, `uv run <cmd>`. Never pip.
- **just** for tasks (`just` lists them): `check`, `test`, `lint`, `fmt`/`format`, `fix`,
  `render`, `render-one <name>`, `render-refs`, `docs-serve`, `docs-build`, `run <script>`,
  `refresh-spreads`, `cross-review`, `codex-skills-sync`, `codex-skills-check`.
- **ruff** for lint and format; pre-commit runs it on commit (`uv run pre-commit install`).
- Rendered Quarto output (`quarto/*.html`, `*.pdf`) and `site/` are gitignored; GitHub
  Pages renders the deck in `.github/workflows/docs.yml`. Set
  `pio.renderers.default = "plotly_mimetype+notebook"` so plotly.js embeds once.
- Secrets: `.env` locally (`FRED_API_KEY`, see `.env.example`), never committed; CI has none
  and must not need any.

## Committing

- **Never commit without the user's explicit yes.** Propose the commit, then wait.
- Once approved, **delegate to the `committer` agent** (`.claude/agents/committer.md`),
  quoting the user's yes verbatim. The PreToolUse gate in `.claude/settings.json`
  (`.claude/hooks/gate_commit.py`, `$CLAUDE_PROJECT_DIR`-anchored) rejects `git commit`
  from anywhere else. Codex follows the same policy through `AGENTS.md` and
  `.codex/agents/committer.toml`. Auto-accept mode is not approval.
- The gate also blocks commits on `main`, `--no-verify`, `uv.lock` staged without a version
  bump, and a red `uv run pytest`. Fix the cause; never work around the gate.
- **Conventional Commits**: `feat:`/`fix:`/`docs:`/`ci:`/`refactor:`/`test:`/`chore:`,
  imperative, one logical change per commit.
- Always feature branch + PR: `git switch -c <type>/<slug> --no-track`, push `-u`.

## Pull requests

- **Delegate PR creation to `pr-manager`** (`.claude/agents/pr-manager.md`; Codex uses
  `pr_manager` in `.codex/agents/pr-manager.toml`). The committer commits; the PR manager
  never commits.
- **Every PR carries**: assignee `realslimslaney`, at least one area label (`finance`,
  `actuarial`, `docs`, `ci`, `tooling`), the open milestone that fits, and a linked issue
  (`Closes #N`, or `Part of #N` for one phase of a tracked plan). PRs and their issues go on
  the Personal Projects board (project 3) with Status "In Progress". Never create labels.
- Open PRs as drafts unless the user approved opening them ready. Bodies end with the
  attribution footer for the agent that created them.

## Skills and Codex mirrors

- Skills live in `.claude/skills/`; Codex gets generated mirrors in `.agents/skills/`. After
  adding or editing a skill run `just codex-skills-sync` and commit both;
  `tests/test_codex_skill_mirrors.py` fails on drift. Never edit a mirror. A hand-written
  Codex version carries `<!-- codex-custom -->` and is left alone.
- Agents are never copied; port a Claude agent to `.codex/agents/*.toml` by hand (the sync
  lists unported ones).
- `/cross-review` asks Codex for a read-only second review and records the exchange on the
  PR (`docs/how-to/how-to-cross-review-a-change.md`). Never pass `--approve-usage` or
  `--force` without the user's explicit yes.
- `/post-plan` posts the current plan to a GitHub issue.

## Specialized agents

`.claude/agents/`: `finance` (calculations and domain rules), `quarto` (reports and reference
pages), `docs` (Diataxis documentation), `code-review` (conventions review), `committer`,
`pr-manager`.

## Documentation (Diataxis)

- `docs/how-to/`: task-oriented, numbered steps, exact commands; files named
  `how-to-<verb>-<noun>.md` for new guides.
- `docs/reference/`: information-oriented, dry, accurate; one page per module or concept.
  When a major module or process is added to `src/alm/`, add a reference page.
- `docs/index.md` links the flagship deck first ("Start here"), then the reference pages.
- `uv run mkdocs build --strict` must pass.

## Working style

- Bias toward correctness over breadth: one right, well-labelled measure beats three
  approximate ones.
- Do not add error handling for cases that cannot happen; validate at input boundaries.
- No new top-level dependencies without a real need; check `pyproject.toml` first.
- When a change moves a published number, update every doc and report that prints it in the
  same change.
