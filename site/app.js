const copy = {
  zh: {
    title: "VoiceFlow — 离线语音输入",
    description: "VoiceFlow 是 Windows 上的离线语音输入工具。按下 F2 说话，文字回到当前光标；不需要账户，也不上传录音。",
    brandHome: "VoiceFlow 首页",
    primaryNav: "主要导航",
    languageSwitch: "语言",
    valuesAria: "VoiceFlow 核心价值",
    skip: "跳到主要内容",
    navValues: "产品",
    navPrivacy: "隐私",
    navGithub: "GitHub",
    heroEyebrow: "Windows 离线语音输入",
    heroTitle: "开口，文字就位。",
    heroLede: "按一下 F2 开始，再按一下完成。无需切换应用，声音在本机变成文字。",
    downloadVoiceFlow: "下载 Windows 版",
    viewGithub: "查看 GitHub",
    compatibility: "Windows 10 / 11 · x64 · v0.2.2",
    demoAlt: "VoiceFlow 胶囊从录音预览过渡到完成状态",
    demoSrc: "assets/voiceflow-demo.svg",
    privacyHref: "https://github.com/qinxujunai/VoiceFlow/blob/master/README.md#隐私与联网",
    valueOfflineLabel: "声音不出电脑",
    valueOffline: "完全离线",
    valueOfflineBody: "无需账户，不上传录音；断开网络照常听写。",
    valueEverywhereLabel: "思路不中断",
    valueEverywhere: "任意输入框",
    valueEverywhereBody: "留在正在使用的应用里，文字直接回到光标。",
    valueRecoveryLabel: "结果不会丢",
    valueRecovery: "始终可找回",
    valueRecoveryBody: "即使没有粘贴成功，剪贴板和本地历史仍有完整文字。",
    privacyEyebrow: "为安静的工作流而设计",
    privacyTitle: "只在需要时出现。<br>完成后，继续做你的事。",
    privacyBody: "小胶囊负责告诉你正在听。停止说话后，完整结果先进入剪贴板，再回到当前光标，并保存在本地历史中。",
    privacyLink: "了解隐私与联网",
    footerTagline: "Windows 10 / 11 · 离线语音输入",
    footerSource: "源代码",
    footerLicenses: "第三方许可",
    footerIssues: "问题反馈"
  },
  en: {
    title: "VoiceFlow — Offline dictation for Windows",
    description: "VoiceFlow is offline dictation for Windows. Press F2 to speak and return text to the cursor, with no account or audio upload.",
    brandHome: "VoiceFlow home",
    primaryNav: "Primary navigation",
    languageSwitch: "Language",
    valuesAria: "VoiceFlow core benefits",
    skip: "Skip to main content",
    navValues: "Product",
    navPrivacy: "Privacy",
    navGithub: "GitHub",
    heroEyebrow: "Offline dictation for Windows",
    heroTitle: "Speak. Words land.",
    heroLede: "Press F2 once to start and again to finish. Stay in the current app while speech becomes text on your PC.",
    downloadVoiceFlow: "Download for Windows",
    viewGithub: "View on GitHub",
    compatibility: "Windows 10 / 11 · x64 · v0.2.2",
    demoAlt: "The VoiceFlow capsule moves from live recording preview to completion",
    demoSrc: "assets/voiceflow-demo.en.svg",
    privacyHref: "https://github.com/qinxujunai/VoiceFlow/blob/master/README.en.md#privacy-and-networking",
    valueOfflineLabel: "Audio stays on your PC",
    valueOffline: "Entirely offline",
    valueOfflineBody: "No account and no audio upload. Dictation keeps working without a network.",
    valueEverywhereLabel: "Stay in your flow",
    valueEverywhere: "Any text field",
    valueEverywhereBody: "Remain in the app you are using and return words directly to the cursor.",
    valueRecoveryLabel: "Your words remain",
    valueRecovery: "Always recoverable",
    valueRecoveryBody: "If paste misses, the complete text is still in the clipboard and local history.",
    privacyEyebrow: "Designed for a quiet workflow",
    privacyTitle: "There when you need it.<br>Gone when you are done.",
    privacyBody: "The small capsule lets you know VoiceFlow is listening. When you stop, the complete result reaches the clipboard first, returns to the cursor, and remains in local history.",
    privacyLink: "Read about privacy and networking",
    footerTagline: "Windows 10 / 11 · Offline dictation",
    footerSource: "Source",
    footerLicenses: "Third-party licenses",
    footerIssues: "Report an issue"
  }
};

const languageButtons = document.querySelectorAll("[data-language]");
const translatable = document.querySelectorAll("[data-i18n]");
const translatedImages = document.querySelectorAll("[data-i18n-alt]");
const translatedAriaLabels = document.querySelectorAll("[data-i18n-aria]");
const translatedSources = document.querySelectorAll("[data-i18n-src]");
const translatedLinks = document.querySelectorAll("[data-i18n-href]");

function setLanguage(language) {
  const selected = copy[language] ? language : "zh";
  document.documentElement.lang = selected === "zh" ? "zh-CN" : "en";
  document.title = copy[selected].title;
  document.querySelector('meta[name="description"]').content =
    copy[selected].description;

  translatable.forEach((element) => {
    const key = element.dataset.i18n;
    if (copy[selected][key]) {
      if (key === "privacyTitle") {
        element.innerHTML = copy[selected][key];
      } else {
        element.textContent = copy[selected][key];
      }
    }
  });

  translatedImages.forEach((image) => {
    const key = image.dataset.i18nAlt;
    if (copy[selected][key]) {
      image.alt = copy[selected][key];
    }
  });

  translatedAriaLabels.forEach((element) => {
    const key = element.dataset.i18nAria;
    if (copy[selected][key]) {
      element.setAttribute("aria-label", copy[selected][key]);
    }
  });

  translatedSources.forEach((element) => {
    const key = element.dataset.i18nSrc;
    if (copy[selected][key]) {
      element.src = copy[selected][key];
    }
  });

  translatedLinks.forEach((element) => {
    const key = element.dataset.i18nHref;
    if (copy[selected][key]) {
      element.href = copy[selected][key];
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
