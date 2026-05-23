path = r'E:\Files\Projects\VoiceFlow\src\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix curly quotes in show_error calls
content = content.replace('\u201c\u65e0\u97f3\u9891\u201d', '\"无音频\"')
content = content.replace('\u201c\u65e0\u8bc6\u522b\u7ed3\u679c\u201d', '\"无识别结果\"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed quotes')
