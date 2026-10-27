# 3 分钟 LLMOps 项目演示

目标：讲清楚为什么需要质量检查、如何让失败阻断发布，以及证据能证明什么。演示使用已有结果，不需要现场重跑模型或发布镜像。建议先按下表练习一次，把浏览器页面提前打开。

## 演示前准备

| 标签页 | 打开内容 | 要看哪里 |
| --- | --- | --- |
| 1 | [项目 README](../README.md) | 贡献表和架构图 |
| 2 | [真实发布运行](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40529687538) | 三个 job 的依赖图 |
| 3 | [实际 Gate 结果](evidence/release-v2.1.0/quality_gate.json) | passed、expected_pairs、quality_passed_pairs、error_rows |
| 4 | [阻断演练](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40476357498) | invalid-gate、blocked-publish-marker、verify-dependencies |
| 5 | [来源证明](evidence/release-v2.1.0/release_provenance.json) 和 [发布证据表](LLMOPS_RELEASE.md#verified-release-v210) | source_sha、tag、digest |

## 操作与讲稿（约 3 分钟）

### 0:00–0:25：问题与个人贡献

操作：显示 README 的贡献表和架构图。

讲稿：
> 这个项目基于已有的开源股票分析应用。我扩展的重点是 LLM 输出评测、用量和费用记录，以及质量检查与镜像发布的集成。模型接口调用成功，只能说明收到了响应；JSON、字段和数据仍可能出错，所以我把输出质量设成一个发布前检查。

### 0:25–1:00：检查什么，为什么可信

操作：打开归档的 quality_gate.json，指出 2/2 通过、error_rows=0；需要时打开 reports.jsonl。

讲稿：
> 我维护了 20 个合成案例。检查器验证必需字段、数据类型、null 以及四个结构化事实值。当前发布只取前两个案例做 smoke check，这次 Gemini 两例都通过，且没有错误。真实模型响应和检查结果分开保存，避免只看绿色图标。质量校验共享同一实现，用量在解析前记录，因此无效 JSON 的调用也不会丢失 token 记录。

### 1:00–1:35：展示真实发布链路

操作：切换 Docker Publish，依次指向 resolve-source、llm-quality / quality、build-and-push。

讲稿：
> 发布先把版本 tag 解析成 commit SHA，检查和构建都使用这个版本。build-and-push 通过 needs 依赖质量 job，通过之后还要跑后端检查和 Docker smoke。这次 v2.1.0 的整条链路已成功，日志记录了 GHCR 镜像 digest。我用 digest 标识这次发布，避免 latest 后来移动造成混淆。

### 1:35–2:15：展示失败确实被拦截

操作：切换阻断演练，指出 invalid-gate 为红、blocked-publish-marker 为 skipped、verify-dependencies 为绿。

讲稿：
> 为验证反例，我生成了字段完整但 close 被改错的合成报告。它被 Gate 拒绝，依赖它的标记 job 没有执行。演练使用真正的 Gate CLI，但后续只是无副作用标记，不推送镜像。整体红色是故意失败的结果，最终核对 job 确认这些状态符合预期。真实发布成功与独立阻断演练是两份不同证据。

### 2:15–2:40：可追溯性与踩坑

操作：显示 provenance 的 source_sha，和发布证据表中的 tag/SHA 对照。

讲稿：
> 本次 Workflow 从 main 启动，但评测和构建的是 v2.1.0 指向的 49bd537。Workflow 版本和发布源码不是同一个概念，所以我把实际 source SHA 写入 provenance。我还修过一个真实问题：Prompt 没讲清顶层字段到嵌套对象的映射，模型把 observations 当成缺失数据。修复时明确了映射并更新 Prompt 版本，没有放宽 Gate。

### 2:40–3:00：边界和下一步

操作：回到 README 范围说明。

讲稿：
> 当前证据证明了小样本 LLM 检查与镜像发布的集成，以及失败依赖阻断。这是专用合成 Prompt 的评测，不能代表股票建议正确，也没有覆盖生产 Prompt 的全部行为。发布后镜像的拉取启动验收和生产部署还没有完成；下一步应补真实应用的回归数据和产物验收。

## 常见追问

| 问题 | 回答要点 |
| --- | --- |
| 为什么不是 API 成功就通过？ | API 成功、JSON 可解析、结构正确和事实一致是不同层级。 |
| 为什么发布只跑两例？ | 成本与耗时折中，是 smoke sample；完整 20 例属于另一层验证，目前不能说发布覆盖全部案例。 |
| 你证明了整个生产系统质量吗？ | 没有。检查的是专用合成数据保真度，不是所有生产报告或自由文本事实。 |
| 模型限流或缺少 key 怎么办？ | 请求失败会形成错误或缺失报告，严格 Gate 失败，发布 job 不执行；这是可用性与安全性的折中。 |
| 两条镜像入口都覆盖了吗？ | 两条主应用发布 Workflow 都有依赖；这次真实成功证据来自 Docker Publish，另一条没有本次实际推送证据。 |
| token 和费用都准确吗？ | 保存 provider 返回的 usage；费用按配置估算，未知不记为零，不把估算当最终账单。 |
| 怎么保证检查和发布同一版？ | tag 一次解析成完整 SHA，Gate 和构建 checkout 同一 SHA；provenance 记录该值。 |
| 红色演练不是失败了吗？ | invalid-gate 是预期失败；要同时核对 blocked job 跳过和最终 verifier 成功，不能仅用整体颜色判断。 |
| 为什么不现场运行？ | 用可复核的历史证据控制演示时间和 API 成本；需要时另行运行离线反例。 |
| AI 写了代码，你做了什么？ | 如实讲需求定义、评测规则、测试判断、日志定位和集成验证；说明使用 AI 辅助编码，只认领自己能解释的部分。 |

## 30-second English opening

> I extended an existing open-source application with LLM report validation, usage and cost tracking, and a release quality gate. The key idea is that a successful API response is not enough: I check structure and fixture consistency before publishing the container. I can show a successful real-model GHCR release and a separate negative dependency rehearsal. The current release sample has two synthetic cases; it is not a claim of full production-report quality.

## 不要夸大的表述

- 可以说：实现真实 LLM 小样本检查，并接入两条主应用镜像发布 Workflow；其中 Docker Publish 已有成功运行记录。
- 可以说：单独的负面演练验证 Gate 失败后依赖 job 跳过。
- 不要说：阻止了所有生产部署、验证了所有模型、完成了所有 20 例发布检查，或已完成发布后的镜像运行验收。
- 不要把上游股票分析系统整体描述为个人从零开发成果。

## 本次交付涉及哪些文件

更新 README.md、docs/README_EN.md、docs/LLMOPS_RELEASE.md；新增本演示稿与 docs/evidence/release-v2.1.0 下的原始证据副本和说明。不修改 Python 或 Workflow，不触发新发布。文档回滚可独立 revert 本次提交，不涉及已发布镜像。
