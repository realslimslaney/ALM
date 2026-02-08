# Contributing

Thanks for your interest in contributing to the ALM toolkit!

## Getting Started

1. Fork the repository and clone your fork
2. Install dependencies: `uv sync`
3. Install pre-commit hooks: `uv run pre-commit install`
4. Create a feature branch: `git checkout -b my-feature`

## Development Workflow

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
uv run pytest          # test
just check             # run all checks (pre-commit + tests)
```

All code must pass linting, formatting, and tests before merging.

## Code Style

- Use **Polars** over pandas for data manipulation
- Add **type hints** to function signatures
- Keep functions focused and single-purpose
- Follow the existing patterns in `src/alm/`

## Pull Requests

1. Keep PRs focused — one feature or fix per PR
2. Add tests for new functionality
3. Update documentation if you change public APIs
4. Fill out the PR template

## Reporting Issues

Use the [GitHub issue tracker](https://github.com/realslimslaney/ALM/issues) with the appropriate template (bug report or feature request).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
