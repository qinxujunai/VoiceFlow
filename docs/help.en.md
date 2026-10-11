# Using VoiceFlow

[Back to the product](../README.en.md)

## Start speaking

Place your cursor in a text field. Press **F2** to start, then press **F2** again to finish.
Right Ctrl and mouse side buttons also work. Esc cancels a recording without producing text.

If the text does not appear, press **Ctrl+V** to paste. Your dictation also stays in local history, ready to revisit and copy.
Some apps, administrator windows and input method states require manual paste.
Mixed Chinese and English preview may appear later; check the final text after stopping.

## Choose your ending

Open settings from the tray and select Dictation. Keep recognized punctuation, omit the final period, or complete the sentence with a period.
Question marks, exclamation marks and punctuation within the text stay. This changes the ending, without rewriting your words.

## Install and update

[Download for Windows](https://github.com/qinxujunai/VoiceFlow/releases/latest). You need Windows 10 / 11 x64 and a microphone.
The installer includes the files needed for offline dictation. You do not need Python.
The installer is currently unsigned, so Windows may show a security prompt. Download from this project's release page; a SHA256 checksum file is provided.

Exit VoiceFlow from the tray before running a new installer. Your settings, vocabulary and history are kept.
VoiceFlow does not update silently or connect automatically. Check for updates yourself in About VoiceFlow.
The update check offers a download only when the installer and checksum file have matching versions and digests.

## History and recovery

Your dictation is kept in local history, where you can revisit, copy or delete it.
Unfinished recordings can be processed from recovery. Check that you no longer need the content before deleting it.
Clearing local data removes dictation history and undelivered recordings after confirmation. It keeps settings, vocabulary and models.

## Privacy and networking

Recording and recognition run on your computer. Everyday dictation needs no connection, account or audio upload.
Settings, vocabulary, history and recovery recordings live in `%LOCALAPPDATA%\VoiceFlow`.
Normal use does not download models, check updates or call cloud recognition. An explicit update check accesses GitHub.
Preparing source dependencies or an approved model download requires a connection. The installer contains no developer or other user's dictation history.

## Get help

[Share feedback](https://github.com/qinxujunai/VoiceFlow/issues). Describe the app and what happened. You do not need to upload private audio or history.

[Release record](release-evidence-0.3.7.md) · [Development](development.en.md) · [Licenses](../THIRD_PARTY_NOTICES.md)
