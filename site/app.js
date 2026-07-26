const copy = {
  zh: {
    title: "VoiceFlow — 离线语音输入",
    description: "VoiceFlow 是完全离线的 Windows 语音输入工具。按 F2 说话，文字回到当前光标，结果始终保留在剪贴板和本地历史。",
    skip: "跳到主要内容",
    navWhy: "为什么是 VoiceFlow",
    navHow: "使用方式",
    navDownload: "下载",
    navGithub: "GitHub",
    heroEyebrow: "完全离线 · Windows",
    heroTitle: "说完，文字就在光标处。",
    heroLede: "按 F2 开始说话，再按一次停止。VoiceFlow 在本机完成识别，把文字送回你正在使用的输入框。",
    downloadWindows: "下载 Windows Beta",
    viewSource: "查看源代码",
    compatibility: "Windows 10 / 11 · x64 · 无需 Python · 安装后可离线使用",
    betaNote: "公开 Beta 当前未签名；Windows 可能显示信誉提示。请只从本页或 GitHub Releases 下载并核对 SHA256。",
    problemEyebrow: "一个更安静的输入方式",
    problemTitle: "语音输入不该要求你上传声音、切换窗口，或担心文字消失。",
    problemBody: "VoiceFlow 把语音识别变成系统里的一层输入能力。它不接管你的工作，只在你需要时出现，完成后立即退回托盘。",
    featureOfflineTitle: "全程在本机",
    featureOfflineBody: "录音、识别、词典和历史默认不离开这台电脑，也不需要账户。",
    featureAnywhereTitle: "在当前输入框说话",
    featureAnywhereBody: "记事本、浏览器、文档或聊天窗口，不必把内容搬到另一个应用。",
    featureRecoveryTitle: "文字总能找回",
    featureRecoveryBody: "先写入剪贴板，再发送粘贴，同时保存在本地历史。",
    featureLongTitle: "长语音不丢尾",
    featureLongBody: "预览只负责反馈，停止后仍会补齐完整音频并输出最终结果。",
    howEyebrow: "三步完成一次听写",
    howTitle: "不需要学习新的工作流。",
    stepOneTitle: "按下快捷键",
    stepOneBody: "F2、右 Ctrl 或鼠标侧键都可以开始。",
    stepTwoTitle: "自然说话",
    stepTwoBody: "小胶囊只显示必要状态，不抢走当前焦点。",
    stepThreeTitle: "再按一次停止",
    stepThreeBody: "文字回到光标处，并保留在剪贴板和历史中。",
    trustEyebrow: "隐私不是一个开关",
    trustTitle: "断开网络，核心功能仍然可用。",
    trustBody: "默认 SenseVoice 模型随离线安装包提供。日常听写不会自动下载模型、检查更新或调用云端服务。",
    privacyLink: "阅读隐私与联网说明",
    downloadEyebrow: "选择你的平台",
    downloadTitle: "只提供真正经过验收的版本。",
    downloadBody: "当前公开目标是 Windows x64。macOS 需要独立完成权限、签名和公证，不会用未验证的包占位。",
    windowsTitle: "Windows 10 / 11 · x64",
    windowsBody: "包含离线模型，安装后无需 Python。Beta 安装器约 314 MB；当前未签名。",
    windowsAction: "下载安装包",
    macTitle: "正在进行原生权限与发布验证",
    macBody: "全局输入、辅助功能权限、签名和 notarization 全部通过后才会开放。",
    macAction: "尚未发布",
    sourceEyebrow: "开放源码，发布可验证",
    sourceTitle: "每个安装包都应有版本、哈希、许可和构建来源。",
    releaseNotes: "查看 Releases",
    footerLicenses: "第三方许可",
    footerIssues: "问题反馈"
  },
  en: {
    title: "VoiceFlow — Offline dictation for Windows",
    description: "VoiceFlow is offline, system-wide dictation for Windows. Press F2, speak, and your words return to the current cursor.",
    skip: "Skip to main content",
    navWhy: "Why VoiceFlow",
    navHow: "How it works",
    navDownload: "Download",
    navGithub: "GitHub",
    heroEyebrow: "Fully offline · Windows",
    heroTitle: "Speak. The words land at your cursor.",
    heroLede: "Press F2 to start and press it again to stop. VoiceFlow recognizes speech on your PC and returns the text to the field you were already using.",
    downloadWindows: "Download Windows Beta",
    viewSource: "View source",
    compatibility: "Windows 10 / 11 · x64 · No Python required · Offline after install",
    betaNote: "This public Beta is currently unsigned, so Windows may show a reputation warning. Download only here or from GitHub Releases and verify the SHA-256.",
    problemEyebrow: "A quieter way to type",
    problemTitle: "Dictation should not make you upload your voice, switch windows, or wonder where the text went.",
    problemBody: "VoiceFlow turns local speech recognition into an input layer for Windows. It appears only when you need it, then returns to the tray.",
    featureOfflineTitle: "Processed on your PC",
    featureOfflineBody: "Audio, recognition, vocabulary, and history stay on this computer by default. No account required.",
    featureAnywhereTitle: "Speak in the field you are using",
    featureAnywhereBody: "Notepad, browsers, documents, and chats work without moving content to another app.",
    featureRecoveryTitle: "Your text stays recoverable",
    featureRecoveryBody: "VoiceFlow writes to the clipboard before sending paste and also stores local history.",
    featureLongTitle: "Complete long dictation",
    featureLongBody: "Preview is feedback only. The final pass still covers the complete stopped audio.",
    howEyebrow: "One dictation in three steps",
    howTitle: "No new workflow to learn.",
    stepOneTitle: "Press a shortcut",
    stepOneBody: "Start with F2, Right Ctrl, or a mouse side button.",
    stepTwoTitle: "Speak naturally",
    stepTwoBody: "A compact pill shows only the state you need without taking focus.",
    stepThreeTitle: "Press again to stop",
    stepThreeBody: "Text returns to the cursor and remains in the clipboard and local history.",
    trustEyebrow: "Privacy is not a toggle",
    trustTitle: "Core dictation still works without a network.",
    trustBody: "The offline installer includes the default SenseVoice model. Everyday dictation does not download models, check for updates, or call cloud services.",
    privacyLink: "Read the privacy and networking notes",
    downloadEyebrow: "Choose your platform",
    downloadTitle: "Only verified builds are offered.",
    downloadBody: "The current public target is Windows x64. macOS requires its own permissions, signing, and notarization work; VoiceFlow will not publish an unverified placeholder.",
    windowsTitle: "Windows 10 / 11 · x64",
    windowsBody: "Includes the offline model and needs no Python. The Beta installer is about 314 MB and is currently unsigned.",
    windowsAction: "Download installer",
    macTitle: "Native permissions and release checks in progress",
    macBody: "The download will open only after global input, Accessibility, signing, and notarization pass.",
    macAction: "Not released",
    sourceEyebrow: "Open source, verifiable releases",
    sourceTitle: "Every installer should have a version, hash, licenses, and build provenance.",
    releaseNotes: "View Releases",
    footerLicenses: "Third-party licenses",
    footerIssues: "Report an issue"
  }
};

const languageButtons = document.querySelectorAll("[data-language]");
const translatable = document.querySelectorAll("[data-i18n]");

function setLanguage(language) {
  const selected = copy[language] ? language : "zh";
  document.documentElement.lang = selected === "zh" ? "zh-CN" : "en";
  document.title = copy[selected].title;
  document.querySelector('meta[name="description"]').content =
    copy[selected].description;
  translatable.forEach((element) => {
    const key = element.dataset.i18n;
    if (copy[selected][key]) {
      element.textContent = copy[selected][key];
    }
  });
  languageButtons.forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.language === selected)
    );
  });
  localStorage.setItem("voiceflow-language", selected);
  const url = new URL(window.location.href);
  if (selected === "en") {
    url.searchParams.set("lang", "en");
  } else {
    url.searchParams.delete("lang");
  }
  window.history.replaceState({}, "", url);
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
});

const requestedLanguage = new URLSearchParams(window.location.search).get("lang");
const savedLanguage = localStorage.getItem("voiceflow-language");
setLanguage(requestedLanguage || savedLanguage || "zh");
