# Using VoiceFlow

> Documentation sync: **2026-11-03** · Current contract / guide. Synchronization date is not a new test date. [Current index](README.md).

[Back to the product](../README.en.md)

## Start speaking

Place your cursor in a text field. Hold **F2** while you speak and release to finish, or press **F2** once to start and again to finish.
Right Ctrl and mouse side buttons work the same way. Esc cancels a recording without producing text. To use taps only, change 按键方式 in settings.

If the text does not appear, press **Ctrl+V** to paste. Your dictation also stays in local history, ready to revisit and copy.
Some apps, administrator windows and input method states require manual paste.
Mixed Chinese and English preview may appear later; check the final text after stopping.

## Choose your ending

Open settings from the tray and select Dictation. Keep recognized punctuation, omit the final period, or complete the sentence with a period.
Question marks, exclamation marks and punctuation within the text stay. This changes the ending, without rewriting your words.

Chinese punctuation processing can still split sentences incorrectly; check the final text. Code, URLs and preserve-format input bypass punctuation inference.

## Settings and vocabulary

Dictation settings share one Save changes action, disabled until something changes. Failed saves keep your edits and explain the problem.
Text preferences apply to the next dictation; language and microphone changes require restarting the app.

Vocabulary supports search, checkboxes, deleting selected entries and undo. Clearing a category requires confirmation; built-in entries are read-only.
For a correction, enter the recognized word and the desired word in separate fields.

Closing settings keeps VoiceFlow in the tray. Launch VoiceFlow again or open settings from the tray to return. Use Exit in the tray to quit.

## Install and update

[Download for Windows](https://github.com/qinxujunai/VoiceFlow/releases/latest). You need Windows 10 / 11 x64 and a microphone.
The installer includes the files needed for offline dictation. You do not need Python.
The installer is currently unsigned, so Windows may show a security prompt. Download from this project's release page; a SHA256 checksum file is provided.

Exit VoiceFlow from the tray before running a new installer. Your settings, vocabulary and history are kept.
By default VoiceFlow checks for a new version once a day. It reads only the latest version number; when one is out, the tray shows a single notice and a 下载新版本 (download new version) menu item that opens the download page. Nothing is downloaded or installed automatically.
To stay offline, turn off 每天自动检查更新 (check for updates daily) in 设置 → 输入 (Settings → Input); you can still check by hand in About VoiceFlow.
Through GitHub, a download is offered only when the installer and checksum file have matching versions and digests; when GitHub is unreachable, the version manifest on the China mirror (Tencent Cloud) is read instead.

## History and recovery

Your dictation is kept in local history, where you can revisit, copy or delete it.
Unfinished recordings can be processed from recovery. Check that you no longer need the content before deleting it.
Clearing local data removes dictation history and undelivered recordings after confirmation. It keeps settings, vocabulary and models.

## Privacy and networking

Recording and recognition run on your computer. Everyday dictation needs no connection, account or audio upload.
Settings, vocabulary, history and recovery recordings live in `%LOCALAPPDATA%\VoiceFlow`.
Normal use does not download models or call cloud recognition. The only automatic connection is the daily update check: it contacts GitHub, or Tencent Cloud when GitHub is unreachable, reads the version number and sends no audio, text or personal information. You can turn it off in Settings.
Preparing source dependencies or an approved model download requires a connection. The installer contains no developer or other user's dictation history.

## Get help

[Share feedback](https://github.com/qinxujunai/VoiceFlow/issues). Describe the app and what happened. You do not need to upload private audio or history.

[Release record](https://github.com/qinxujunai/VoiceFlow/releases/latest) · [Development](development.en.md) · [Licenses](../THIRD_PARTY_NOTICES.md)
