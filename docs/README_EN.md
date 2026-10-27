# LLMOps Portfolio Extension

This fork builds on [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis). The upstream stock-analysis application is not claimed as original portfolio work. This extension focuses on strict report evaluation, usage/cost accounting, and release gating.

Both main-application image publishers now depend on a real LLM quality job and check out the same immutable source SHA. The release gate checks two synthetic cases per model (at most six API calls) and requires a 100% pass rate. Set repository variable `RELEASE_LLM_MODELS` to override the default Gemini model. Triggering a release incurs API usage.

See the [portfolio overview and architecture](../README.md) and [release operations, evidence and limitations](LLMOPS_RELEASE.md). The rehearsal publishes no image and uses synthetic responses; its negative job intentionally fails to demonstrate that its dependent publication marker is skipped. This is not proof of an actual GHCR push, production deployment, investment accuracy, or end-to-end application quality.


For application installation and features, see the [upstream English guide](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/README_EN.md). The upstream license and attribution are retained.

## Verified release and demonstration

[Docker Publish run #40529687538](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40529687538) succeeded on 2026-10-27: real-model quality gate (2/2 cases, zero errors), backend checks, Docker smoke, and GHCR push all passed. Release `v2.1.0` evaluated and built source commit `49bd537335c4d874d194d27cd3e1dc3f566993b1`, independently of the workflow dispatch revision.

Image: `ghcr.io/atlas-schulter/daily_stock_analysis:v2.1.0`. Immutable digest: `sha256:7d43c6d5268dac73381aa2ff2106bd931231f6b954e6a7b8df7e7ba4a38abb36`.

See [the evidence ledger](LLMOPS_RELEASE.md#verified-release-v210), [archived original gate artifacts](evidence/release-v2.1.0/), and [the three-minute demo and interview questions](DEMO_WALKTHROUGH.md). A later [v2.1.1 run](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40571513998) verified a digest-pinned GHCR pull and a Python core-module import smoke in the published container. FastAPI startup, HTTP health checks and production deployment remain unverified. The blocked dependency path was demonstrated separately with synthetic reports and a harmless marker job.

## Post-release verification: v2.1.1

Source `3c97bd2fcb89fb62e07f9d8e8895a4aefd4f8dca`; manifest digest `sha256:5b48240e2f5c2c3690b518b3cca9f316bd3b7478b9694e6f9abcfda29ac90571`. [Run #40571513998](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40571513998) passed the real-model Gate (2/2, zero errors), backend checks, push and post-push pull/import smoke. See [the evidence ledger](LLMOPS_RELEASE.md#verified-post-release-v211). This is distinct from full service startup or deployment acceptance.
