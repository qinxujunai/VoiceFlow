const copy = {
  zh: {
    title: "VoiceFlow — 离线语音输入",
    description: "VoiceFlow 是 Windows 上的离线语音输入工具。按下 F2 说话，文字回到当前光标，声音与历史留在本机。",
    skip: "跳到主要内容",
    navValues: "产品",
    navPrivacy: "隐私",
    navDownload: "下载",
    navGithub: "GitHub",
    heroEyebrow: "Windows 离线语音输入",
    heroTitle: "开口，文字就位。",
    heroLede: "按下 F2，说出想法。VoiceFlow 在本机完成识别，把文字送回当前光标。",
    downloadVoiceFlow: "下载 Windows 版",
    viewGithub: "查看 GitHub",
    compatibility: "Windows 10 / 11 · x64 · v0.2.1",
    demoAlt: "VoiceFlow 胶囊从录音预览过渡到最终确认",
    valueOffline: "完全离线",
    valueOfflineBody: "核心听写在本机完成，不需要账户，也不上传录音。",
    valueEverywhere: "任意输入框",
    valueEverywhereBody: "不切换应用，文字直接回到你正在输入的位置。",
    valueRecovery: "始终可找回",
    valueRecoveryBody: "结果先进入剪贴板，并同步保存在本地历史。",
    privacyEyebrow: "安静、可靠、只在需要时出现",
    privacyTitle: "声音留在本机。文字回到正在做的事。",
    privacyBody: "VoiceFlow 不依赖云端识别。停止说话后，完整结果先写入剪贴板，再尝试粘贴，并保存在本地历史中。",
    privacyLink: "了解隐私与联网",
    downloadEyebrow: "VoiceFlow 0.2",
    downloadTitle: "下载，然后开口。",
    downloadBody: "一个安装包，内置离线模型。无需 Python，安装后即可断网听写。",
    downloadWindows: "下载 Windows 版",
    releaseNotes: "查看版本说明",
    unsignedNote: "当前安装包尚未代码签名，Windows 可能显示信誉提示。请仅从本页或 GitHub Releases 下载。",
    footerTagline: "离线语音输入，回到当前光标。",
    footerSource: "源代码",
    footerLicenses: "第三方许可",
    footerIssues: "问题反馈"
  },
  en: {
    title: "VoiceFlow — Offline dictation for Windows",
    description: "VoiceFlow is offline dictation for Windows. Press F2 to speak, return text to the cursor, and keep audio and history on your PC.",
    skip: "Skip to main content",
    navValues: "Product",
    navPrivacy: "Privacy",
    navDownload: "Download",
    navGithub: "GitHub",
    heroEyebrow: "Offline dictation for Windows",
    heroTitle: "Speak. Words land.",
    heroLede: "Press F2 and say what you mean. VoiceFlow recognizes speech on your PC and returns text to the current cursor.",
    downloadVoiceFlow: "Download for Windows",
    viewGithub: "View on GitHub",
    compatibility: "Windows 10 / 11 · x64 · v0.2.1",
    demoAlt: "The VoiceFlow capsule moves from live recording preview to final confirmation",
    valueOffline: "Entirely offline",
    valueOfflineBody: "Core dictation runs on your PC, with no account and no audio upload.",
    valueEverywhere: "Any text field",
    valueEverywhereBody: "Stay in the current app and return words to the place where you are typing.",
    valueRecovery: "Always recoverable",
    valueRecoveryBody: "Every result reaches the clipboard and is also saved to local history.",
    privacyEyebrow: "Quiet, dependable, present only when needed",
    privacyTitle: "Audio stays on your PC. Words return to your work.",
    privacyBody: "VoiceFlow does not depend on cloud recognition. When you stop, the complete result goes to the clipboard first, then paste is attempted, and local history keeps a copy.",
    privacyLink: "Read about privacy and networking",
    downloadEyebrow: "VoiceFlow 0.2",
    downloadTitle: "Download. Then speak.",
    downloadBody: "One installer includes the offline model. No Python required, and dictation works without a network.",
    downloadWindows: "Download for Windows",
    releaseNotes: "View release notes",
    unsignedNote: "The installer is not code-signed yet, so Windows may show a reputation warning. Download only from this page or GitHub Releases.",
    footerTagline: "Offline dictation, returned to your cursor.",
    footerSource: "Source",
    footerLicenses: "Third-party licenses",
    footerIssues: "Report an issue"
  }
};

const languageButtons = document.querySelectorAll("[data-language]");
const translatable = document.querySelectorAll("[data-i18n]");
const translatedImages = document.querySelectorAll("[data-i18n-alt]");

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

  translatedImages.forEach((image) => {
    const key = image.dataset.i18nAlt;
    if (copy[selected][key]) {
      image.alt = copy[selected][key];
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
