# Disclaimer

Self-Improving Prompt Optimizer is provided **as-is**, free of charge, for anyone to run, study, modify, and build on. Please read this before you use it.

## You run this on your own machine, with your own keys

This is a local-first tool. When you run it, you provide your own API key (an OpenAI-compatible endpoint, and optionally Agnes AI) and everything executes on your own machine. Nobody else's infrastructure is involved, and the maintainer has no visibility into how you use it.

## You are responsible for your data

Everything the app processes — your base prompt, task description, benchmark test cases, generated candidate prompts, and every model response — is **100% your responsibility**:

- **What you enter.** Don't submit content you don't have the right to process, or content that's confidential, regulated, or sensitive, unless you understand and accept the consequences of sending it to whichever provider you've configured.
- **Where it goes.** Every base prompt, task description, candidate prompt, benchmark input, and LLM output is sent to your configured OpenAI-compatible endpoint (or Agnes AI, if selected) for generation, judging, and embedding. That data leaves your machine and is subject to that provider's own terms, privacy policy, and data-retention practices — review those before sending anything sensitive.
- **What's stored locally.** Optimization runs themselves are **not** persisted to disk — the LangGraph checkpointer (`InMemorySaver`) keeps run state only in memory, and it's gone when the app process stops. The one thing that *is* written to disk is an auto-generated benchmark, saved to `data/generated_benchmark.json` in plaintext when you use the "Generate benchmark from task description" button. Delete that file any time you want to clear it.
- **Compliance.** If you're subject to GDPR, HIPAA, an employer's data policy, or any other regulatory or contractual obligation, it's on you to ensure your use of this tool — and the provider you point it at — complies with those obligations.

## No warranty

This software is provided under the MIT License **"AS IS", WITHOUT WARRANTY OF ANY KIND**, express or implied. The author is not liable for any damages, data loss, unexpected API charges from a provider you configured, or other outcomes arising from your use of this project. See [LICENSE](LICENSE) for the full legal text.

## Accuracy of optimization results

This tool uses an LLM to mutate prompts, judge candidate outputs, and score them across multiple metrics (accuracy, clarity, conciseness, helpfulness, consistency). LLM-as-judge scoring is a heuristic, not ground truth — it can be inconsistent, biased toward certain phrasing styles, or simply wrong. A "best prompt" the optimizer converges on is only as good as the benchmark and the judge model behind it; always review the output yourself before trusting it in production.

## No financial relationship

This project does not want or accept donations, sponsorships, or any form of financial support. See [README.md](README.md#support-the-project) for details. Using this software creates no financial relationship between you and the author.

If any of this is unclear, please open an issue — see [SUPPORT.md](SUPPORT.md).
