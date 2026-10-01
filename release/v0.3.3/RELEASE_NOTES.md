# VoiceFlow 0.3.3

这是一次面向公开交付链路的补丁版本：应用运行时保持 0.3.2 的稳定行为，官网、Pages 部署和发布材料现在与同一个稳定 Release 对齐。

发布构建：`build 261001.1`

## 本次更新

- 官网保留完全离线、内置模型、无需登录的准确产品文案，并随稳定 Release 自动更新版本号和 Windows 下载地址。
- Pages 工作流在 Release 工作流成功后自动渲染官网，且只接受带匹配安装包、`SHA256SUMS.txt`、SBOM 和第三方许可文件的已发布 Release。
- README、安装器、Windows 文件版本信息和发布材料统一为 `0.3.3`。

## 验证

- 本版本沿用 0.3.2 的本地运行时和固定内置模型；发布前重新运行仓库发布验证，并保留结果于 `docs/release-evidence-0.3.3.md`。
- 官网下载链接只在匹配的 GitHub Release 安装包和 SHA-256 校验信息发布后更新。
- 这些工程门禁不等同于自然语料准确率宣传。

## 下载

Windows 10 / 11 x64 用户下载：

`VoiceFlow-0.3.3-Windows-x64.exe`

安装包已经包含默认终稿模型和双语流式预览模型，安装后无需额外下载模型。

精确 SHA-256 请以本 Release 同时附带的 `SHA256SUMS.txt` 为准。

Windows 安装包的代码签名状态以本 Release 的实际资产和 Release 工作流签名校验为准；未签名时 Windows 可能显示安全提示。

---

VoiceFlow 0.3.3 is a release-pipeline patch. The runtime keeps the stable
0.3.2 behavior while the public site, Pages deployment, README, installer
metadata, and release materials now point to the same published Windows
release. The site is rendered only after the matching installer, checksums,
SBOM, and third-party notices have been uploaded. Build 261001.1.
