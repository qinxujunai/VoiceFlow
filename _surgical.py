# Minimal surgical edits to main.py
path = r'E:\Files\Projects\VoiceFlow\src\main.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

changes = 0

# 1. Add _actively_recording flag
if 'self._actively_recording' not in c:
    c = c.replace(
        'self._is_processing = False\n',
        'self._is_processing = False\n        self._actively_recording = False\n'
    )
    changes += 1
    print('1. Added _actively_recording flag')

# 2. Fix _on_record_start: check _actively_recording
old = '        if self._is_processing:\n            return\n        try:\n            self.session.start()'
new = '        if self._is_processing or self._actively_recording:\n            return\n        self._actively_recording = True\n        try:\n            self.session.start()'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('2. Fixed _on_record_start guard')

# 3. Fix _on_record_stop: use _actively_recording, not audio.is_recording
old = '        if not self.audio.is_recording:\n            return'
new = '        if not self._actively_recording:\n            return\n        self._actively_recording = False'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('3. Fixed _on_record_stop guard')

# 4. Replace cache shortcut with full transcription
old = '''            duration = result.duration or (len(data) / self.audio.sample_rate)
            raw_text, text, cached = self._final_text_from_cache()
            if not cached:
                self.overlay.show_processing()
                raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)
                text = self.cleaner.clean(raw_text) if raw_text else ""'''
new = '''            raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)
            text = self.cleaner.clean(raw_text) if raw_text else ""'''
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('4. Removed cache shortcut, always full transcription')

# 5. Simplify the print line (no more source tracking)
old = '''                rtf = (time.time() - duration) / duration if duration > 0 else 0
                source = \u201c\u7f13\u5b58\u201d if cached else \u201c\u6700\u7ec8\u201d
                print(f\"[\u8f6c\u5199] ({source}) {text} ({duration:.1f}s)\", flush=True)'''
new = '''                duration = result.duration or (len(data) / self.audio.sample_rate)
                print(f\"[\u8f6c\u5199] {text} ({duration:.1f}s)\", flush=True)'''
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('5. Simplified transcription log')

# 6. Add show_result before hide_after
old = '                self.overlay.hide_after(0)'
new = '                self.overlay.show_result(text)\n                self.overlay.hide_after(280)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('6. Added show_result + hide_after(280)')

# 7. Fix _on_record_cancel guard
old = '        if self.audio.is_recording:\n            self._stop_streaming()\n            self.session.cancel()'
new = '        if self._actively_recording:\n            self._actively_recording = False\n            self._stop_streaming()\n            self.session.cancel()'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('7. Fixed _on_record_cancel guard')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print(f'\nTotal: {changes} changes applied')
