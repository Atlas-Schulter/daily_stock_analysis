## LLMOps Engineering Extension

This repository is a fork of [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis), extended as a personal engineering project focused on LLMOps, CI/CD, and AI application reliability.

### My Contributions

- **Risk Monitoring:** Developed configurable stock risk alerts with Discord notifications and duplicate alert prevention.
- **CI Automation:** Added automated unit and integration tests using GitHub Actions.
- **Observability:** Implemented structured logging, execution metrics, and failure notifications.
- **LLM Monitoring:** Integrated token usage tracking and JSONL telemetry.
- **LLM Evaluation:** Added automated structural checks for generated reports.

### Current Development Status

Core risk monitoring and CI functionality have been tested. LLM token usage accuracy and provider-specific streaming behavior are still being investigated.

For implementation details, see [LLMOps Engineering Notes](docs/LLMOPS.md).

---

*Original project documentation continues below.*


### Live Benchmark V2 / 实时评测

唯一入口为 `python -m benchmarks.live_v2`；原 `live_v2_fixed.py` 的有效修复已合并，不再维护副本。
The only runner is `python -m benchmarks.live_v2`; the duplicate fixed runner has been removed.

```bash
python -m unittest discover -s tests -p 'test_live*.py' -v
python -m unittest discover -s tests -p 'test_benchmark_v2.py' -v
python -m unittest discover -s tests -p 'test_quality_gate.py' -v
```

真实请求必须显式传入 `--confirm-live`；`--max-calls` 默认 20，限制计划的模型数 × 样本数，不自动重试。
Live requests require `--confirm-live`. The default `--max-calls=20` caps models × selected cases; retries are disabled.

进程环境变量（runner 不自动读取 `.env`） / Process environment (no automatic `.env` loading):

| Variable | Default | Meaning / 含义 |
| --- | --- | --- |
| `LLM_BENCHMARK_DELAY_SECONDS` | `2` | Finite non-negative seconds between calls, including model boundaries / 请求间隔 |
| `LLM_BENCHMARK_MAX_TOKENS` | `4096` | Positive output token cap; raising it can increase cost / 输出 token 上限 |

Gemini 路由请求 JSON mode；其他 provider 不强制该参数。Provider/model 实际支持情况仍需真实小样本验证。
Gemini routes request JSON mode; other providers do not receive that parameter. Provider/model compatibility requires a live smoke test.
HTTP 429 或 `RateLimitError` 停止当前模型，剩余样本记为 `SkippedAfterRateLimit`，继续下一个模型。
HTTP 429 or `RateLimitError` stops the current model, records remaining cases as skipped, and continues with the next model.

产物仍位于 `artifacts/live_v2/`，每次运行覆盖旧产物。JSON 解析失败也保留已收到的 usage。
Artifacts remain in `artifacts/live_v2/` and are replaced per run. Received usage is retained even when JSON parsing fails.

- `planned_calls = attempted_calls + skipped_calls`; `attempted_calls = successful_calls + failed_calls`.
- `successful_calls` means a decoded JSON object, not a passed quality check / 解析成功不代表质量通过。
- `call_success_rate = successful_calls / planned_calls` (existing denominator / 保留原分母).
- `attempt_success_rate = successful_calls / attempted_calls` (new / 新增).
- Report quality rates use submitted reports; `fixture_coverage` uses the full fixture suite / 质量率只评估已有报告，覆盖率以完整案例集为分母。
- Token, latency and cost summaries include every usage row, including invalid JSON responses / 费用和 token 包含解析失败响应。
- `known_cost_usd` is a partial known estimate; `total_cost_usd` and `cost_per_success_usd` are null if pricing or attempted-call usage is incomplete / 缺少费用或调用 usage 时不伪装完整账单。
- All-failed models remain visible with zero evaluated cases and null quality rates / 全失败模型仍显示。

`benchmark-live-v2.yml` is a manual comparison workflow; model errors are recorded without automatically failing the runner.
`llm-quality-gate.yml` runs offline regression tests on matching pushes and only calls paid APIs on explicit manual opt-in.
Its live job also enforces strict quality checks and fails on errors, skipped cases, or missing reports.
Both workflows use the same runner and offline test commands. Quality checks accept flat repository fixtures and nested observation fixtures.

Benchmark Workflow 用于手动比较，失败会写入产物；Quality Gate Workflow 自动触发时只做离线测试，手动启用真实调用后严格阻断错误、跳过及缺失报告。
两个 Workflow 共用 runner 和测试命令，字段校验复用同一实现，兼容平铺和嵌套 fixture。
