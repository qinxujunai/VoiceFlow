"""Phase 3: spinner animation + punctuation strategy + long recording"""
import os, re

base = r"E:\Files\Projects\VoiceFlow"

# ============================================================
# 1. overlay.html: spinner CSS + showCompleting() + clean streaming text
# ============================================================
html_path = os.path.join(base, "src", "overlay.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# 1a. Add spinner keyframes (after existing keyframes, before closing style tag)
spinner_css = '''
.processing .mark span {
    background: var(--blue);
    animation: spinPulse 900ms ease-in-out infinite;
}
.processing .mark span:nth-child(2) { animation-delay: 160ms; }
.processing .mark span:nth-child(3) { animation-delay: 320ms; }

@keyframes spinPulse {
    0%, 70%, 100% { opacity: 0.28; transform: scaleY(0.6); }
    35% { opacity: 1; transform: scaleY(1.0); }
}

.pill.completing {
    border-color: rgba(100, 167, 255, 0.2);
}

.completing .mark span {
    background: var(--blue);
    animation: spinPulse 900ms ease-in-out infinite;
}
.completing .mark span:nth-child(2) { animation-delay: 160ms; }
.completing .mark span:nth-child(3) { animation-delay: 320ms; }

.completing .ticker {
    color: var(--muted);
}'''

# Insert before the closing </style> tag
html = html.replace('</style>', spinner_css + '\n</style>')

# 1b. Add showCompleting() JS function after showProcessing()
old_fn = '''function showProcessing() {
    showState('processing', '处理中');
}'''

new_fn = '''function showProcessing() {
    showState('processing', '处理中');
}

function showCompleting() {
    // Lock current width, switch bars to spinner, text stays or shows "..."
    pill.className = 'pill completing';
    var curWidth = pill.offsetWidth;
    pill.style.setProperty('--target-width', curWidth + 'px');
    pill.style.width = curWidth + 'px';
    if (!txt.textContent) {
        txt.textContent = '';
    }
    pill.style.setProperty('--ticker-offset', '0px');
}'''

html = html.replace(old_fn, new_fn)

# 1c. Add punctuation stripping in updateStreaming
old_update = '''function updateStreaming(text) {
    if (!text) return;
    pill.className = 'pill streaming';
    txt.textContent = text;
    setWidthForText(text);
    updateTickerOffset();
}'''

new_update = '''function updateStreaming(text) {
    if (!text) return;
    // Strip punctuation for clean streaming display
    var display = text.replace(/[，。！？、；：""''…—~.,!?;:'"\\-]/g, '').trim();
    if (!display) return;
    pill.className = 'pill streaming';
    txt.textContent = display;
    setWidthForText(display);
    updateTickerOffset();
}'''

html = html.replace(old_update, new_update)

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print("1. overlay.html: spinner + showCompleting + streaming punctuation strip")

# ============================================================
# 2. text_cleaner.py: add clean_streaming() method
# ============================================================
cleaner_path = os.path.join(base, "src", "text_cleaner.py")
with open(cleaner_path, "r", encoding="utf-8") as f:
    tc = f.read()

# Add clean_streaming() after clean() method - find the end of clean()
# clean() ends with "return text.strip()" and is followed by _strip_fillers or similar
streaming_method = '''
    def clean_streaming(self, text: str) -> str:
        """Clean for streaming display: strip all punctuation for smooth flow."""
        if not text or not text.strip():
            return text
        text = text.strip()
        if self.remove_fillers:
            text = self._strip_fillers(text)
        if self.fix_mistakes:
            text = self._fix_mistakes(text)
        # Strip all punctuation for streaming
        import unicodedata
        text = ''.join(c for c in text if not unicodedata.category(c).startswith('P') and c != '\\uff0c' and c != '\\u3002' and c != '\\uff01' and c != '\\uff1f' and c != '\\u3001' and c != '\\uff1b' and c != '\\uff1a' and c != '\\u2026' and c != '\\u2014' and c != '\\u2018' and c != '\\u2019' and c != '\\u201c' and c != '\\u201d')
        text = re.sub(r" {2,}", " ", text)
        return text.strip()
'''

# Insert before _strip_fillers or after the clean() method
# Find "    def _strip_fillers" and insert before it
tc = tc.replace('    def _strip_fillers(self, text: str) -> str:', streaming_method + '\n    def _strip_fillers(self, text: str) -> str:')

with open(cleaner_path, "w", encoding="utf-8") as f:
    f.write(tc)
print("2. text_cleaner.py: clean_streaming() method")

# ============================================================
# 3. main.py: long recording support + completing state
# ============================================================
main_path = os.path.join(base, "src", "main.py")
with open(main_path, "r", encoding="utf-8") as f:
    main = f.read()

# 3a. Replace streaming loop with incremental accumulation
old_loop = '''        last_len = 0
        def loop():
            nonlocal last_len
            while self._streaming:
                try:
                    buf = self.audio._audio_buffer
                    if buf:
                        chunk = np.concatenate(buf, axis=0).flatten()
                        new_samples = len(chunk) - last_len
                        # Only transcribe when 0.5s+ of new audio, or first chunk
                        if new_samples > self.audio.sample_rate * 0.5 or last_len == 0:
                            text = self.transcriber.transcribe(chunk, self.audio.sample_rate)
                            last_len = len(chunk)
                            if text:
                                self._latest_text = text
                                clean = self.cleaner.clean(text)
                                self.overlay.update_streaming(clean)
                except Exception:
                    pass
                time.sleep(0.22)'''

new_loop = '''        last_len = 0
        def loop():
            nonlocal last_len
            while self._streaming:
                try:
                    buf = self.audio._audio_buffer
                    if buf:
                        chunk = np.concatenate(buf, axis=0).flatten()
                        new_samples = len(chunk) - last_len
                        if new_samples > self.audio.sample_rate * 0.6 or last_len == 0:
                            text = self.transcriber.transcribe(chunk, self.audio.sample_rate)
                            last_len = len(chunk)
                            if text:
                                self._latest_text = text
                                # Use streaming-specific clean (no punctuation)
                                clean = self.cleaner.clean_streaming(text)
                                if clean:
                                    self.overlay.update_streaming(clean)
                except Exception:
                    pass
                time.sleep(0.25)'''

main = main.replace(old_loop, new_loop)

# 3b. Add show_completing to overlay_webview.py
# First check if it exists
if 'show_completing' not in main:
    # Add method to OverlayWindow class in overlay_webview.py
    ov_path = os.path.join(base, "src", "overlay_webview.py")
    with open(ov_path, "r", encoding="utf-8") as f:
        ov = f.read()
    
    completing_method = '''
    def show_completing(self):
        self._tray_state(TRAY_ICON_PROCESSING)
        self._js("showCompleting()")
'''
    # Insert after show_processing method
    ov = ov.replace(
        '    def show_result(self, text):',
        completing_method + '\n    def show_result(self, text):'
    )
    
    with open(ov_path, "w", encoding="utf-8") as f:
        f.write(ov)
    print("3a. overlay_webview.py: show_completing() method")

# 3c. Modify _on_record_stop to use completing state for long recordings
old_stop_final = '''            raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)
            text = self.cleaner.clean(raw_text) if raw_text else ""

            if text:'''

new_stop_final = '''            raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)
            text = self.cleaner.clean(raw_text) if raw_text else ""

            # If streaming had text but final differs (tail processed), show completing
            if text and self._latest_text and text != self._latest_text:
                self.overlay.show_completing()

            if text:'''

main = main.replace(old_stop_final, new_stop_final)

with open(main_path, "w", encoding="utf-8") as f:
    f.write(main)
print("3b. main.py: completing state for long recordings")

print("\nAll phase 3 changes applied")
