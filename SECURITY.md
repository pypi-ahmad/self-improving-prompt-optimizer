# Security Policy

## Supported versions

This single-branch personal project has no maintained release branches. Security fixes, when needed, are applied only to `main`. Run the latest `main` commit.

## Reporting a vulnerability

If you find a security issue, **do not open a public GitHub issue**. Instead:

1. Open a [private security advisory](https://github.com/pypi-ahmad/self-improving-prompt-optimizer/security/advisories/new) on GitHub, or
2. If that's not available to you, open a regular issue with minimal detail asking to be contacted privately, and the maintainer will follow up.

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce it.
- Which file(s)/component(s) are involved, if known.

This is a best-effort, single-maintainer project. There is no dedicated security team or SLA.

## Scope

This is a **local-first application** that runs on your machine with your API key. It has no hosted service, backend, or shared infrastructure. Relevant security topics include:

- Handling of API keys and credentials (`runtime.py`, `.env` loading via `python-dotenv`).
- Local data storage (`data/generated_benchmark.json`: plain JSON, without encryption or access control beyond OS filesystem permissions).
- Handling of untrusted input passed to the LLM (base prompt, task description, injected prompts, benchmark inputs).
- Dependencies with known CVEs (see `pyproject.toml` / `uv.lock`).

**Out of scope:** vulnerabilities in third-party services used by this project, including OpenAI's API, Agnes AI, or another OpenAI-compatible endpoint. Report these directly to the relevant provider.

## Data handling reminder

The maintainer does not operate a data collection service. The application sends task content to configured providers. Application checkpoints stay in memory; generated benchmarks, explicit downloads, and live-verification artifacts may contain task content. Errors and exports exclude configured API credentials and raw provider exception bodies. Imported JSON Schemas cannot load external references. See [DISCLAIMER.md](DISCLAIMER.md) for data-handling details.
