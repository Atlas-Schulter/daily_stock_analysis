# LLMOps Portfolio Extension

This fork builds on [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis). The upstream stock-analysis application is not claimed as original portfolio work. This extension focuses on strict report evaluation, usage/cost accounting, and release gating.

Both main-application image publishers now depend on a real LLM quality job and check out the same immutable source SHA. The release gate checks two synthetic cases per model (at most six API calls) and requires a 100% pass rate. Set repository variable `RELEASE_LLM_MODELS` to override the default Gemini model. Triggering a release incurs API usage.

See the [portfolio overview and architecture](../README.md) and [release operations, evidence and limitations](LLMOPS_RELEASE.md). The rehearsal publishes no image and uses synthetic responses; its negative job intentionally fails to demonstrate that its dependent publication marker is skipped. This is not proof of an actual GHCR push, production deployment, investment accuracy, or end-to-end application quality.


For application installation and features, see the [upstream English guide](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/README_EN.md). The upstream license and attribution are retained.
