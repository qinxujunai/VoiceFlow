<p align="right"><a href="README.md">中文</a> · <strong>English</strong></p>

![VoiceFlow — Let ideas take shape](docs/voiceflow-brand.en.svg)

<div align="center">

**Offline voice typing for Windows. Dictate at your cursor for AI conversations, email and messages.**

[Download VoiceFlow](https://github.com/qinxujunai/VoiceFlow/releases/latest)　·　[Explore the website](https://qinxujunai.github.io/VoiceFlow/?lang=en)　·　[Get help](docs/help.en.md)

Windows 10 / 11 · Works offline · No sign-in

</div>

## Less typing. Less switching.

![VoiceFlow product demo](docs/voiceflow-demo.svg)

Place your cursor in a text field. Press **F2** to start and again to finish.
Your voice becomes text on your computer. Recording and recognition stay local.

## Why VoiceFlow

I talk to AI by voice while I chat and build, often for five or ten minutes at a time. The voice input tools I tried each had strengths, but I kept hitting three problems:

1. **When I stopped, one network hiccup and the whole passage was gone.**
2. **The last few sentences often never appeared.** I wanted all of it: the last word I say should be the last word on screen.
3. **If the cursor wasn’t in a text box, everything I said simply vanished.**

So VoiceFlow runs entirely on your computer: no network delay; the final pass covers the whole recording; the text goes to the clipboard before it is typed, so nothing is lost even without a text box. If these have bothered you too, it was built for you.

| What matters during use | How VoiceFlow handles it |
| --- | --- |
| A connection or account? | Recording and recognition run locally. Dictate offline after installation, without signing in. |
| Automatic paste fails? | Final text is copied before paste is attempted. Press Ctrl+V; the old clipboard is not restored. |
| The last sentence at stop? | Final recognition covers the complete stopped recording. Preview is feedback and cannot overwrite the final text. |
| Recovering a result? | Final text is kept in local history; undelivered recordings have a local recovery path. |
| Vocabulary and formatting? | Custom terms and explicit corrections, per-app final punctuation, and preserved formatting for code and terminals. |

VoiceFlow focuses on everyday shortcut-driven input, without meeting speaker identification or cloud rewriting. These are delivery mechanisms, not a promise of zero failures. Recognition can be wrong, some apps require manual paste, and later copy operations can replace the clipboard.

## Quiet controls, manageable preferences

A black capsule shows recording and text preview. The tray provides dictation, recovery and exit actions. Maintain your terms and explicit corrections in the vocabulary, and choose text preferences per application.
Chinese, English and code-switching quality must be measured separately. A complete natural-speech comparison is not available, so no claim of superior accuracy is made. [Quality and limits](docs/product-quality-standard.md)

[What is new in 0.3.9?](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.9)

---

If text does not appear, press **Ctrl+V** to paste. Some apps require manual paste.
The installer is currently unsigned, so Windows may show a security prompt. See [Help](docs/help.en.md) for details.

[Feedback](https://github.com/qinxujunai/VoiceFlow/issues) · [Development](docs/development.en.md) · [Project license](LICENSE) · [Third-party licenses](THIRD_PARTY_NOTICES.md)
