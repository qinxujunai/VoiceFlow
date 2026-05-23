path = r'E:\Files\Projects\VoiceFlow\src\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find _on_record_stop and fix its indentation
for i, line in enumerate(lines):
    if line.strip() == 'def _on_record_stop(self):' and line.startswith('        '):
        # Fix: change from 8 spaces to 4 spaces
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        # The method should be at 4-space indent, body at 8-space
        # Current: method at 8-space, body at 12-space
        # Target: method at 4-space, body at 8-space
        # So we need to shift lines from this point to next def by -4 spaces
        break

# Find next method after _on_record_stop
stop_idx = None
cancel_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith('def _on_record_stop'):
        stop_idx = i
    if stop_idx and i > stop_idx and line.strip().startswith('def _on_record_cancel'):
        cancel_idx = i
        break

if stop_idx and cancel_idx:
    # Shift all lines in this range by -4 spaces
    for i in range(stop_idx, cancel_idx):
        if lines[i].startswith('        '):
            lines[i] = lines[i][4:]
        elif lines[i].startswith('            '):
            lines[i] = lines[i][4:]
    
    print(f'Fixed indentation for lines {stop_idx+1}-{cancel_idx}')
else:
    print(f'Could not find boundaries: stop={stop_idx}, cancel={cancel_idx}')

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('Done')
