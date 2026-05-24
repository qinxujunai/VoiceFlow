# VoiceFlow Eval

Local ASR evaluation lives here. Keep private recordings out of Git.

## Manifest

Create a JSONL manifest such as `eval/local.jsonl`:

```jsonl
{"id":"ai_terms_001","audio":"audio/ai_terms_001.wav","reference":"我现在用 Cursor 和 Codex 调试这个本地语音输入工具"}
{"id":"long_pause_001","audio":"audio/long_pause_001.wav","reference":"这是一段带停顿的长句，用来检查结尾是否会丢字"}
```

Audio paths are relative to the manifest file. Put private audio under
`eval/audio/` or `eval/private/`; both are ignored by Git.

## Run

```bat
venv\Scripts\python.exe scripts\benchmark_models.py --manifest eval\local.jsonl
```

The benchmark reports load time, RTF, transcription text, character error
rate when a reference exists, and domain vocabulary hits.
