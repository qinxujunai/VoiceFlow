path = r'E:\Files\Projects\VoiceFlow\src\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# ===== 1. Add _actively_recording flag =====
for i, line in enumerate(lines):
    if line.strip() == 'self._is_processing = False':
        indent = line[:len(line) - len(line.lstrip())]
        lines.insert(i + 1, indent + 'self._actively_recording = False')
        break

# ===== 2. Fix _on_record_start guard =====
for i, line in enumerate(lines):
    if 'if self._is_processing:' in line and i > 70:
        lines[i] = line.replace('if self._is_processing:', 'if self._is_processing or self._actively_recording:')
        indent = line[:len(line) - len(line.lstrip())]
        lines.insert(i + 2, indent + 'self._actively_recording = True')
        break

# ===== 3. Find method boundaries =====
stop_start = None
cancel_start = None
for i, line in enumerate(lines):
    if line.strip().startswith('def _on_record_stop'):
        stop_start = i
    if stop_start and line.strip().startswith('def _on_record_cancel'):
        cancel_start = i
        break

if stop_start and cancel_start:
    # Find except block
    except_start = None
    finally_start = None
    for i in range(stop_start, cancel_start):
        s = lines[i].strip()
        if s.startswith('except Exception'):
            except_start = i
        if s.startswith('finally:'):
            finally_start = i

    IND = '        '
    new_method = []
    new_method.append(IND + 'def _on_record_stop(self):')
    new_method.append(IND + '    if not self._actively_recording:')
    new_method.append(IND + '        return')
    new_method.append(IND + '    self._actively_recording = False')
    new_method.append(IND + '    self._is_processing = True')
    new_method.append(IND + '    self._stop_streaming()')
    new_method.append('')
    new_method.append(IND + '    try:')
    new_method.append(IND + '        result = self.session.stop()')
    new_method.append(IND + '        data = result.audio_data')
    new_method.append(IND + '        if len(data) == 0:')
    new_method.append(IND + '            self.overlay.show_error(\u201c\u65e0\u97f3\u9891\u201d)')
    new_method.append(IND + '            self.overlay.hide_after(2000)')
    new_method.append(IND + '            self._is_processing = False')
    new_method.append(IND + '            return')
    new_method.append('')
    new_method.append(IND + '        raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)')
    new_method.append(IND + '        text = self.cleaner.clean(raw_text) if raw_text else ""')
    new_method.append('')
    new_method.append(IND + '        if text:')
    new_method.append(IND + '            duration = result.duration or (len(data) / self.audio.sample_rate)')
    # Use {0} and {1} to avoid f-string issues, then .format() later... 
    # Actually just use concatenation
    print_line = IND + '            print(f"[\\u8f6c\\u5199] {text} ({duration:.1f}s)", flush=True)'
    new_method.append(print_line)
    new_method.append(IND + '            output_status = self.output_handler.output(text)')
    new_method.append(IND + '            self.history.append(')
    new_method.append(IND + '                raw_text=raw_text,')
    new_method.append(IND + '                clean_text=text,')
    new_method.append(IND + '                output_status=output_status,')
    new_method.append(IND + '            )')
    new_method.append(IND + '            self.overlay.show_result(text)')
    new_method.append(IND + '            self.overlay.hide_after(280)')
    new_method.append(IND + '        else:')
    new_method.append(IND + '            self.overlay.show_error(\u201c\u65e0\u8bc6\u522b\u7ed3\u679c\u201d)')
    new_method.append(IND + '            self.overlay.hide_after(2000)')

    # Add except/finally from original
    if except_start and finally_start:
        new_method.extend(lines[except_start:finally_start])
        new_method.extend(lines[finally_start:cancel_start])
    elif except_start:
        new_method.extend(lines[except_start:cancel_start])

    lines[stop_start:cancel_start] = new_method
    print('Replaced _on_record_stop')

# ===== 4. Fix _on_record_cancel guard =====
for i, line in enumerate(lines):
    if 'if self.audio.is_recording:' in line and i > stop_start:
        lines[i] = line.replace('self.audio.is_recording', 'self._actively_recording')
        break

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('Done')
