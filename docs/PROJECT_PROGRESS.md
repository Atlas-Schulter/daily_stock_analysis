# 原始 P1–P3 计划与验收 Todo

截至 2026-10-27。状态以证据为准；“基础目标完成”不表示所有生产场景已覆盖。此表维护在仓库，不是 ChatGPT 原生侧栏。

- [x] **P1：增加独立功能——自定义风险提醒**
  - [x] 按跌幅阈值判断风险，提供可选 Discord 发送及股票/日期去重。
  - [x] 触发、未触发、发送失败不写入去重状态等本地测试通过。
- [x] **P1：加入自动化测试并验证 CI**
  - [x] GitHub Actions 自动测试已运行；发布链路已有 backend gate 成功证据。
- [x] **P2：结构化日志、错误告警与 API 成本统计（基础实现）**
  - [x] 结构化运行事件与 metrics 文件；失败通知入口；LLM usage 和估算费用记录。
  - [x] 本次复查 risk 相关 12 项、observability 3 项测试通过。
  - [ ] 所有 provider 的实际账单对账、真实故障通知逐渠道验收：可选后续项，尚未完成。
- [x] **P2：LLM 输出质量评估（基础版本）**
  - [x] 20 个合成 fixture、严格结构/事实校验、失败处理与原始证据。
  - [x] 发布 Gate 实际两例通过并接入主应用发布依赖；不代表已完成全部案例及生产 Prompt 的端到端评测。
- [x] **P3：构建 Docker Image 并完成定时任务型部署**
  - [x] 主应用镜像构建、GHCR 发布及 [v2.1.1 发布后 pull/import smoke](LLMOPS_RELEASE.md#verified-post-release-v211)。
  - [x] 独立 risk-alert 镜像从 GHCR 拉取并由 schedule 启动；[运行证据](https://github.com/Atlas-Schulter/daily_stock_analysis/actions/runs/40457981665)。
  - [x] 真实获取 3 只股票行情、执行风险判断并写出成功 metrics；数据错误为 0。
  - [x] 无股票达到跌幅阈值时正常结束，未发送无必要消息。
  - [ ] 风险触发后的真实 Discord 送达：本次未触发；已有 mock HTTP/失败/去重测试，不能当作真实送达证据。
- [x] **作品整理**
  - [x] 中英文 README、架构、来源与能力边界说明。
  - [x] 评测、发布、镜像 smoke、定时任务证据归档。
  - [x] 3 分钟演示稿及面试追问。

## P3 为什么可以完成

原目标是构建镜像并部署运行。risk-alert 作为定时批处理容器，已在 GitHub-hosted runner 上按 schedule 拉取镜像、获取真实行情、完成规则判断及输出结果；这满足本项目的定时任务型部署验收。它不是长期运行的生产服务。没有风险时“不发通知”是正确行为，不应为了打勾改阈值制造告警。

## 后续可选验收（不阻塞原始基础目标）

- [ ] 在真实风险出现时核实 Discord 发送日志与接收结果；或用户单独授权清晰标记的测试消息。
- [ ] 更广案例集及生产 Prompt 回归；价格目录/真实账单对账。
- [ ] 若以后提供 Web/API 服务，再补 FastAPI 启动与 HTTP 健康检查。

## 证据与边界

[部署证据与说明](LLMOPS_RELEASE.md#verified-scheduled-risk-deployment)；[原始 metrics](evidence/risk-deployment-40457981665/risk_metrics.json)；[整理摘要](evidence/risk-deployment-40457981665/verification.json)。独立 risk-alert 的定时部署与主应用镜像发布属于两条链路，不混用其源码和 digest。真实通知送达仍是明确的待验证项。
