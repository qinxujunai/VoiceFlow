# VoiceFlow Eval

Local ASR evaluation lives here. Keep private recordings out of Git.

## Manifest

Create a JSONL manifest such as `eval/local.jsonl`:

```jsonl
{"id":"ai_terms_001","audio":"audio/ai_terms_001.wav","reference":"我现在用 Cursor 和 Codex 调试这个本地语音输入工具","terms":["Cursor","Codex"]}
{"id":"long_pause_001","audio":"audio/long_pause_001.wav","reference":"这是一段带停顿的长句，用来检查结尾是否会丢字","terms":[]}
```

Audio paths are relative to the manifest file. Put private audio under
`eval/audio/` or `eval/private/`; both are ignored by Git.

Fields:

- `id`: stable sample name shown in benchmark output.
- `audio`: WAV path relative to the manifest file.
- `reference`: the text you expected VoiceFlow to produce.
- `terms`: optional important words that must survive recognition and cleanup.

## Run

```bat
venv\Scripts\python.exe scripts\benchmark_models.py --manifest eval\local.jsonl
```

The benchmark reports load time, RTF, raw transcript, cleaned transcript, raw
character error rate, cleaned character error rate, term hits, and missed terms.

## Accuracy workflow

1. Record around 20 private samples that contain the AI or programming terms you
   actually say, such as Cursor, Codex, Qwen, DeepSeek, FastAPI, or project names.
2. Put the WAV files under `eval/private/` and write `eval/private/local.jsonl`
   with `reference` and `terms` for each sample.
3. Run:
   ```bat
   venv\Scripts\python.exe scripts\benchmark_models.py --manifest eval\private\local.jsonl
   ```
4. When the same wrong phrase appears repeatedly, add a deterministic correction:
   ```bat
   venv\Scripts\python.exe scripts\add_correction.py "科瑟" "Cursor"
   ```
5. Re-run the benchmark and compare raw CER vs clean CER plus missed terms.

Important: plain word-list files such as `builtin-ai.txt`, `ai-terms.txt`, and
`user-dictionary.txt` are loaded as vocabulary terms for evaluation and future
work, but the current SenseVoice runtime does not use them as ASR hotword
injection. Today, only `wrong=correct` pairs in `corrections.txt` and built-in
TextCleaner mappings change final output.
