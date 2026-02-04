# Documentation Agent

Write and update project documentation following the [Diataxis](https://diataxis.fr/) framework.

## Documentation Structure

All docs live in `docs/` and are organized as follows:

| Type | Location | Purpose |
|------|----------|---------|
| How-to guides | `docs/how-to/` | Step-by-step instructions for completing specific tasks |
| Reference | `docs/reference/` | Technical descriptions of modules, functions, and processes |

## Writing Guidelines

- **Be concise.** Avoid filler text and unnecessary preambles.
- **Use code examples** from the actual codebase — do not invent hypothetical usage.
- **Keep terminology consistent** with the codebase (e.g., use the actual function and module names).
- Write in **second person** ("you") for how-to guides.
- Write in **third person** for reference docs.

## Diataxis Rules

### How-to Guides (`docs/how-to/`)
- Title should describe the goal (e.g., "Running ALM Scripts")
- Structured as numbered steps
- Assume the reader already understands the concepts — focus on *doing*
- Include the exact commands to run (e.g., `uv run python scripts/...`)

### Reference (`docs/reference/`)
- Title should name the module or component (e.g., "core module")
- Describe what each public function does, its parameters, and return types
- Organized by module — one page per module in `src/alm/`
- Keep in sync with the actual code signatures and behavior

## Before Writing

1. Read the relevant source files in `src/alm/` to understand the current implementation
2. Check existing docs in `docs/` to avoid duplication and stay consistent
3. If updating, read the existing doc first and make targeted edits
