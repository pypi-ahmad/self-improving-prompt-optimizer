# Contributing

This guide describes the development setup, branch conventions, and testing requirements for contributing to Self-Improving Prompt Optimizer.

## Development setup

### Prerequisites

- Python `>=3.13` (runtime version specified in `pyproject.toml` and `.python-version`)
- [uv](https://docs.astral.sh/uv/) package manager
- Access to an OpenAI-compatible API endpoint

### Installation

Clone the repository and install dependencies using `uv`:

```bash
git clone https://github.com/pypi-ahmad/self-improving-prompt-optimizer.git
cd self-improving-prompt-optimizer
uv sync
```

Configure local environment variables:

```bash
# On Unix-like shells
cp .env.example .env

# On Windows cmd
copy .env.example .env
```

Set `OPENAI_API_KEY` in `.env`.

To run the application locally during development:

```bash
uv run streamlit run app.py
```

## Branch expectations

- The repository maintains a single target branch: `main`.
- Feature and bugfix branches should branch off `main` and submit pull requests targeting `main`.
- Continuous integration (CI) workflows are not configured in this repository (there is no `.github/workflows/` directory). All verification is currently performed by human reviewers.

## Testing expectations

The repository does not contain an automated test suite. There is no `tests/` directory and no test runner configured in `pyproject.toml`.

Per the pull request template (`.github/PULL_REQUEST_TEMPLATE.md`), changes must be verified through manual testing:

1. **Local end-to-end execution**:
   - Launch the Streamlit application locally.
   - Run a multi-generation optimization using the built-in benchmark.
   - Verify that all three selection strategies (`hybrid`, `weighted`, `pareto`) execute without raising unhandled exceptions.
   - Confirm that the **Best Prompt**, **Pareto Front**, and **History** tabs populate correctly.
   - Verify that file downloads (`best_prompt.txt`, `history.json`, `history.csv`) produce valid content.
2. **Auto-benchmark generation** (if modifying `benchmark.py` or `prompts.py`):
   - Switch benchmark mode to "Auto-generated" and trigger benchmark creation.
   - Verify that test cases are generated, displayed, and written to `data/generated_benchmark.json`.
3. **Mid-run controls** (if modifying `app.py` or `graph.py`):
   - Test Stop and Resume functionality.
   - Test custom prompt injection during paused execution.

## Pull request checklist

Contributors submitting pull requests should ensure:

- The change has been tested by running the application locally.
- Documentation has been updated if setup steps, environment variables, or user-facing behavior changed.
- No new required external service dependencies are introduced beyond OpenAI-compatible API endpoints.
- No API keys, `.env` files, or populated benchmark data files (`data/generated_benchmark.json`) are staged or committed.

## Pull request template

The repository provides a template at `.github/PULL_REQUEST_TEMPLATE.md` with sections for describing changes, related issues, manual test steps taken, and checklist verification.
