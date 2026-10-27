# VoiceFlow 0.3.11

## 中文

- 20 秒以内的语音可在说话停顿时提前识别；如果停下前没有继续说话，直接使用后台结果，减少等待。
- 改进长语音分段衔接，减少接缝处的多余重复、误删真实重复词和中文多余空格。
- 更新 anyio、certifi、filelock 和 typing_extensions 依赖。
- 官网增加页脚链接，并在从作者个人网站进入时显示返回入口；这些改动仅影响官网。

## English

- For recordings under 20 seconds, recognition may run during a pause and reuse the result when no further speech follows.
- Improve long-recording joins to reduce duplicate text, preserve intentional repetitions, and avoid extra spaces at Chinese seams.
- Update anyio, certifi, filelock, and typing_extensions.
- Add a website footer link and a return link for visitors arriving from the author's personal site; these changes affect the website only.

Windows installer is unsigned.
