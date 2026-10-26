# VoiceFlow documentation / 文档索引

> Documentation sync: **2026-10-22**. This index separates current guidance from historical evidence. 原始决策、测试和发布时间保持不变；整理日期不代表重新测试。

## 后续智能体从这里开始

1. 先读 [AGENTS.md](../AGENTS.md) 和 [产品/架构设计](../DESIGN.md)，再读对应模块的现行契约。
2. 当前已核对的公开 Windows 版本为 **0.3.10 / build 261022.1 / PE 0.3.10.1**。先看 [发布与本机验收](release-validation-0.3.10.md)、[精确安装包签署](../release/v0.3.10/RELEASE_SIGNOFF.json) 和 [Release 附件](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.10)。版本状态会变化，执行前重新核对。
3. 日常行为以源码和实际运行进程为准；发布身份以版本标签、安装包哈希和安装后 EXE 为准。仓库文档更新不会自动改变已安装程序。
4. 历史文档中的“当前”“候选”“未完成”仅指原记录时点；不要拿旧候选的许可阻断或旧测试数字代替最新签署。历史性能不代表本次重新测量，也不能证明自然语音准确率提升。
5. 保持离线优先、忠实整理、独立预览与终稿、剪贴板/历史恢复、一个保存事务和关闭设置继续驻留托盘。不要恢复滚动窗口重识别、隐藏猜词替换或用户端模型选择器。
6. 发布按 [检查清单](release-checklist.md) 同步源码、真实安装版、GitHub 附件、双语说明和在线官网下载；不要改写原始许可证、不可变校验附件或旧发布记录来“刷日期”。

## 用户与开发入口

- [中文使用帮助](help.zh-CN.md) · [English help](help.en.md)
- [中文开发文档](development.zh-CN.md) · [Development](development.en.md)
- [质量标准](product-quality-standard.md) · [质量门](quality-gate.md) · [模型策略](model-strategy.md)
- [第三方声明](../THIRD_PARTY_NOTICES.md) · [当前依赖审查](../licenses/release-review-0.3.10.md) · [对应 LGPL 源码](../licenses/LGPL-SOURCE.md)

## 整理范围

项目自有、Git 跟踪的 Markdown 指南和历史证据在本轮统一标注整理日期；历史文件名不改，以免破坏链接和证据引用。未跟踪的私人计划/日志未上传。第三方原文、`licenses/`、`vendor/` 和 `release/` 下的版本化材料保持原始字节，下面单独列出。

## 项目文档目录

| 文档 | 状态 | 本轮文档整理 |
| --- | --- | --- |
| [AGENTS.md](../AGENTS.md) | Current contract / guide | 2026-10-22 |
| [DESIGN.md](../DESIGN.md) | Current contract / guide | 2026-10-22 |
| [README.en.md](../README.en.md) | Current contract / guide | 2026-10-22 |
| [README.md](../README.md) | Current contract / guide | 2026-10-22 |
| [design-qa-v031.md](design-qa-v031.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/asr-evaluation-plan.md](asr-evaluation-plan.md) | Current contract / guide | 2026-10-22 |
| [docs/asr-runtime-build.md](asr-runtime-build.md) | Current contract / guide | 2026-10-22 |
| [docs/decisions/ADR-001-capsule-finalization-contract.md](decisions/ADR-001-capsule-finalization-contract.md) | Superseded design | 2026-10-22 |
| [docs/decisions/ADR-002-single-visual-state-and-fixed-model.md](decisions/ADR-002-single-visual-state-and-fixed-model.md) | Current contract / guide | 2026-10-22 |
| [docs/decisions/ADR-003-quiet-successful-delivery.md](decisions/ADR-003-quiet-successful-delivery.md) | Current contract / guide | 2026-10-22 |
| [docs/decisions/ADR-004-supervised-runtime-boundary.md](decisions/ADR-004-supervised-runtime-boundary.md) | Current contract / guide | 2026-10-22 |
| [docs/decisions/ADR-005-native-capsule-and-process-budgets.md](decisions/ADR-005-native-capsule-and-process-budgets.md) | Current contract / guide | 2026-10-22 |
| [docs/development.en.md](development.en.md) | Current contract / guide | 2026-10-22 |
| [docs/development.zh-CN.md](development.zh-CN.md) | Current contract / guide | 2026-10-22 |
| [docs/feedback-review-2026-07-28.md](feedback-review-2026-07-28.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/flagship-reliability-architecture.md](flagship-reliability-architecture.md) | Current contract / guide | 2026-10-22 |
| [docs/help.en.md](help.en.md) | Current contract / guide | 2026-10-22 |
| [docs/help.zh-CN.md](help.zh-CN.md) | Current contract / guide | 2026-10-22 |
| [docs/model-center-contract.md](model-center-contract.md) | Superseded design | 2026-10-22 |
| [docs/model-lab-2026-07-18-preliminary.md](model-lab-2026-07-18-preliminary.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/model-strategy.md](model-strategy.md) | Current contract / guide | 2026-10-22 |
| [docs/platform-release-contract.md](platform-release-contract.md) | Current contract / guide | 2026-10-22 |
| [docs/product-quality-standard.md](product-quality-standard.md) | Current contract / guide | 2026-10-22 |
| [docs/punctuation-model-review.md](punctuation-model-review.md) | Current contract / guide | 2026-10-22 |
| [docs/qt-lgpl-compliance.md](qt-lgpl-compliance.md) | Current contract / guide | 2026-10-22 |
| [docs/quality-gate.md](quality-gate.md) | Current contract / guide | 2026-10-22 |
| [docs/release-checklist.md](release-checklist.md) | Current contract / guide | 2026-10-22 |
| [docs/release-evidence-0.3.2.md](release-evidence-0.3.2.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.3.md](release-evidence-0.3.3.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.4.md](release-evidence-0.3.4.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.5.md](release-evidence-0.3.5.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.6.md](release-evidence-0.3.6.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.7.md](release-evidence-0.3.7.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-evidence-0.3.8.md](release-evidence-0.3.8.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-notes-0.3.9.md](release-notes-0.3.9.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-notes-v0.1.0.md](release-notes-v0.1.0.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-performance-evidence-2026-08-11.md](release-performance-evidence-2026-08-11.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/release-validation-0.3.9.md](release-validation-0.3.9.md) | Historical release evidence; dated results retained | 2026-10-22 |
| [docs/release-validation-0.3.10.md](release-validation-0.3.10.md) | Current release evidence | 2026-10-22 |
| [docs/release-notes-0.3.10.md](release-notes-0.3.10.md) | Release notes | 2026-10-22 |
| [docs/resource-profile-2026-07-28.md](resource-profile-2026-07-28.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/runtime-boundary.md](runtime-boundary.md) | Current contract / guide | 2026-10-22 |
| [docs/sensevoice-redistribution-decision.md](sensevoice-redistribution-decision.md) | Current contract / guide | 2026-10-22 |
| [docs/stop-latency-evaluation-2026-10-26.md](stop-latency-evaluation-2026-10-26.md) | Historical evidence / release notes | 2026-10-26 |
| [docs/streaming-preview-evaluation-2026-07-28.md](streaming-preview-evaluation-2026-07-28.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/streaming-preview-evaluation-2026-08-05.md](streaming-preview-evaluation-2026-08-05.md) | Historical evidence / release notes | 2026-10-22 |
| [docs/streaming-preview-model-review.md](streaming-preview-model-review.md) | Current contract / guide | 2026-10-22 |
| [docs/upgrade-and-data-contract.md](upgrade-and-data-contract.md) | Current contract / guide | 2026-10-22 |
| [eval/README.md](../eval/README.md) | Current contract / guide | 2026-10-22 |

## 保留原始字节的记录

下列材料按既有版本/哈希管理，目录整理日期为 2026-10-22；不把它们改写成今天重新审查或重测。

- [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
- [release/v0.2.0-beta.1/RELEASE_NOTES.md](../release/v0.2.0-beta.1/RELEASE_NOTES.md)
- [release/v0.2.0/RELEASE_NOTES.md](../release/v0.2.0/RELEASE_NOTES.md)
- [release/v0.2.0/THIRD_PARTY_NOTICES.md](../release/v0.2.0/THIRD_PARTY_NOTICES.md)
- [release/v0.2.1/RELEASE_NOTES.md](../release/v0.2.1/RELEASE_NOTES.md)
- [release/v0.2.2/RELEASE_NOTES.md](../release/v0.2.2/RELEASE_NOTES.md)
- [release/v0.3.0/RELEASE_NOTES.md](../release/v0.3.0/RELEASE_NOTES.md)
- [release/v0.3.0/THIRD_PARTY_NOTICES.md](../release/v0.3.0/THIRD_PARTY_NOTICES.md)
- [release/v0.3.1/RELEASE_NOTES.md](../release/v0.3.1/RELEASE_NOTES.md)
- [release/v0.3.1/THIRD_PARTY_NOTICES.md](../release/v0.3.1/THIRD_PARTY_NOTICES.md)
- [release/v0.3.2/RELEASE_NOTES.md](../release/v0.3.2/RELEASE_NOTES.md)
- [release/v0.3.3/RELEASE_NOTES.md](../release/v0.3.3/RELEASE_NOTES.md)
- [release/v0.3.4/RELEASE_NOTES.md](../release/v0.3.4/RELEASE_NOTES.md)
- [release/v0.3.5/RELEASE_NOTES.md](../release/v0.3.5/RELEASE_NOTES.md)
- [release/v0.3.6/RELEASE_NOTES.md](../release/v0.3.6/RELEASE_NOTES.md)
- [release/v0.3.7/RELEASE_NOTES.md](../release/v0.3.7/RELEASE_NOTES.md)
- [release/v0.3.8/RELEASE_NOTES.md](../release/v0.3.8/RELEASE_NOTES.md)
- [release/v0.3.9/RELEASE_NOTES.md](../release/v0.3.9/RELEASE_NOTES.md)

- [release/v0.3.10/RELEASE_NOTES.md](../release/v0.3.10/RELEASE_NOTES.md)
