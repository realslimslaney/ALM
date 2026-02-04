# Running Scripts

Scripts in `scripts/` are standalone Python files that use the `alm` package.

## Running a Script

```bash
uv run python scripts/<script_name>.py
```

All scripts can import from the `alm` package directly:

```python
from alm import some_function
```

## Adding a New Script

1. Create a new `.py` file in `scripts/`
2. Import what you need from `alm`
3. Run it with `uv run python scripts/your_script.py`
