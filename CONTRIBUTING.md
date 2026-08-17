# Contributing

Thanks for considering a contribution — this project is free, open, and community-driven, and improvements from anyone are genuinely welcome, whether that's a one-line typo fix or a new selection strategy.

## Ways to contribute

- **Report a bug** — see [SUPPORT.md](SUPPORT.md) and the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Suggest a feature** — use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
- **Improve the docs** — README clarity, missing setup steps, and typo fixes are all valuable and welcome as small PRs.
- **Submit code** — new judging metrics, selection strategies, a CLI entry point, or UI improvements (see the README's [Future Improvements](README.md#future-improvements) for ideas).

No contribution is too small. If you're unsure whether something is worth a PR, open an issue first and ask.

## Getting set up

```bash
git clone https://github.com/pypi-ahmad/self-improving-prompt-optimizer.git
cd self-improving-prompt-optimizer
uv sync
copy .env.example .env    # then add your own OPENAI_API_KEY
```

You'll need access to an OpenAI-compatible API (`OPENAI_API_KEY`, and optionally `OPENAI_BASE_URL` for a different endpoint). See the README's [Environment Variables](README.md#environment-variables) section for the full list.

Run the app locally to test your changes:

```bash
uv run streamlit run app.py
```

## Development workflow

1. Fork the repo and create a branch from `main`.
2. Make your change. Keep it focused — a PR that does one thing is much easier to review than one that mixes a bug fix with a refactor.
3. Test it manually against the running app (there is currently no automated test suite — see below).
4. Update the README or other docs if your change affects setup, configuration, or user-facing behavior.
5. Open a PR using the [pull request template](.github/PULL_REQUEST_TEMPLATE.md), describing what changed and why.

## Project structure

See the [README's Project Structure section](README.md#project-structure) for a map of `app.py`, `graph.py`, `evaluator.py`, `benchmark.py`, `prompts.py`, and `utils.py`. Understanding the LangGraph loop in `graph.py` (initialize → generate variations → filter by diversity → evaluate → select → update elite → check stopping) is the fastest way to orient yourself — see [README.md's "How It Works"](README.md#how-it-works) section for the full diagram.

## Testing

There is no automated test suite in this repository today. If you're adding non-trivial logic (a new scoring heuristic, a new selection strategy, a state-machine change), please:

- Test it manually by running a real optimization end-to-end.
- Consider adding a small `pytest` test alongside your change if it's a pure function (e.g. something in `utils.py`) — this is welcomed but not required.

## Code style

- Match the existing style in the file you're editing.
- Keep functions small and single-purpose, consistent with the existing modules.
- Avoid adding new dependencies unless there's a clear need — this project intentionally keeps its dependency list small.
- Prompt templates live in `prompts.py` — if you're changing LLM instructions, edit them there rather than inlining new prompt text elsewhere.

## Reporting security issues

Please do **not** open a public issue for a security vulnerability. See [SECURITY.md](SECURITY.md) for how to report it privately.

## A note on scope

This is a personal, local-first project maintained on a best-effort basis. Response times to issues and PRs will vary — please be patient. See [SUPPORT.md](SUPPORT.md) for what to expect.
