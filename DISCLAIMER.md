# Disclaimer

Self-Improving Prompt Optimizer is provided **as-is**, free of charge, for anyone to run, study, modify, and build on.

## You run this on your own machine, with your own keys

This is a local-first tool. You provide your own API key for an OpenAI-compatible endpoint, and optionally Agnes AI, and the app runs on your machine. The maintainer has no visibility into how you use it.

## You are responsible for your data

You are responsible for everything the app processes: your base prompt, task description, benchmark cases, generated candidate prompts, and model responses.

- **What you enter.** Do not submit content you lack the right to process, or confidential, regulated, or sensitive content, unless you accept the consequences of sending it to the configured provider.
- **Where it goes.** The app sends every base prompt, task description, candidate prompt, benchmark input, and LLM output to the configured OpenAI-compatible endpoint, or Agnes AI when selected, for generation, judging, and embedding. That data leaves your machine and is subject to the provider's terms, privacy policy, and retention practices. Review them before sending sensitive content.
- **What's stored locally.** Application checkpoints stay in memory and disappear when the process stops. Generated benchmarks are stored in `data/generated_benchmark.json` as plaintext. Browser downloads can include prompts, benchmark inputs, responses, scores, and usage. The live smoke-test command also writes a budget ledger and run export under `artifacts/`; Git ignores these files.
- **Compliance.** If GDPR, HIPAA, an employer data policy, or another regulatory or contractual obligation applies to you, ensure that your use of this tool and its configured provider complies with it.

## No warranty

This software is provided under the MIT License **"AS IS", WITHOUT WARRANTY OF ANY KIND**, express or implied. The author is not liable for any damages, data loss, unexpected API charges from a provider you configured, or other outcomes arising from your use of this project. See [LICENSE](LICENSE) for the full legal text.

## Accuracy of optimization results

The tool scores accuracy, clarity, conciseness, and helpfulness with an LLM judge. Cross-case spread and repeated-evaluation variation are diagnostics. LLM judgments can be biased or wrong. Repeated evaluation and holdout cases do not establish ground truth. Review the comparison and regressions before using a recommended prompt.

Run allowances use configured prices and conservative request reservations. They do not cap spending by other applications or replace provider billing controls. Missing usage retains its reservation. A budget-limited comparison is labeled incomplete, not an improvement. Credential placeholder replacement is a best-effort safeguard, not a guarantee that arbitrary sensitive content will be removed.

## No financial relationship

This project does not want or accept donations, sponsorships, or any form of financial support. Using this software creates no financial relationship between you and the author.

For support, see [SUPPORT.md](SUPPORT.md).
