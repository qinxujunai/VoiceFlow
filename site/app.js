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
    navPrivacy: "体验",
    navGithub: "GitHub",
    heroEyebrow: "Windows 离线语音输入",
    heroTitle: "开口，文字就位。",
    heroLede: "按一下 F2 开始，再按一下完成。无需切换应用，声音在本机变成文字。",
    downloadVoiceFlow: "下载 Windows 版",
    viewGithub: "查看 GitHub",
    compatibility: "Windows 10 / 11 · x64 · v__VOICEFLOW_VERSION__",
    releaseStatus: "离线使用 · 无需登录",
    demoAlt: "VoiceFlow 听写时显示文字，完成后收起",
    demoSrc: "assets/voiceflow-demo.svg",
    privacyHref: "https://github.com/qinxujunai/VoiceFlow/blob/master/README.md#隐私与联网",
    valueOfflineLabel: "无需联网",
    valueOffline: "完全离线",
    valueOfflineBody: "安装后即可离线听写。录音和识别都在你的电脑上完成。",
    valueEverywhereLabel: "思路不中断",
    valueEverywhere: "说完，接着写。",
    valueEverywhereBody: "写邮件、记笔记、回消息。在输入框中按下 F2，说完再按一下。",
    valueRecoveryLabel: "随时回看",
    valueRecovery: "想法，有迹可循。",
    valueRecoveryBody: "在本地历史中查看和复制听写内容。需要时，也可以手动粘贴。",
    privacyEyebrow: "为安静的工作流而设计",
    privacyTitle: "只在需要时出现。",
    privacyBody: "录音时，小胶囊显示正在识别的文字。完成后自动收起，让你继续眼前的事。",
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
    navPrivacy: "Experience",
    navGithub: "GitHub",
    heroEyebrow: "Offline dictation for Windows",
    heroTitle: "Speak. Words land.",
    heroLede: "Press F2 once to start and again to finish. Stay in the current app while speech becomes text on your PC.",
    downloadVoiceFlow: "Download for Windows",
    viewGithub: "View on GitHub",
    compatibility: "Windows 10 / 11 · x64 · v__VOICEFLOW_VERSION__",
    releaseStatus: "Works offline · No sign-in",
    demoAlt: "The VoiceFlow capsule shows words during dictation and disappears when you finish",
    demoSrc: "assets/voiceflow-demo.en.svg",
    privacyHref: "https://github.com/qinxujunai/VoiceFlow/blob/master/README.en.md#privacy-and-networking",
    valueOfflineLabel: "No connection needed",
    valueOffline: "Entirely offline",
    valueOfflineBody: "Dictate offline after installation. Audio recording and recognition stay on your PC.",
    valueEverywhereLabel: "Stay in your flow",
    valueEverywhere: "Speak. Keep writing.",
    valueEverywhereBody: "Write emails, take notes, reply to messages. Press F2 in a text field, speak, then press again.",
    valueRecoveryLabel: "Revisit your words",
    valueRecovery: "Keep your thoughts close.",
    valueRecoveryBody: "Review and copy dictation in your local history. Paste manually whenever you need to.",
    privacyEyebrow: "Designed for a quiet workflow",
    privacyTitle: "There when you need it.",
    privacyBody: "A small capsule shows recognized words while you record. It disappears when you finish, so you can carry on.",
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
setLanguage(requestedLanguage || "zh");
