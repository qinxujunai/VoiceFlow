"""
文字输出模块
将转写文字注入到当前活动窗口的光标位置。
支持两种模式：
  - clipboard: 复制到剪贴板 + 模拟 Ctrl+V 粘贴
  - keyboard: 模拟键盘逐字输入
兜底：粘贴失败时自动存入剪贴板和本地历史文件。
"""

import os
import time
import yaml
import pyperclip
import pyautogui

# 禁用 pyautogui 的安全暂停（我们自己控制）
pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE = False


class OutputHandler:
    """文字输出到当前活动窗口，带兜底机制"""

    def __init__(self, config_path=None, base_dir=None, overlay=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        out_cfg = config.get("output", {})
        self.mode = out_cfg.get("mode", "clipboard")
        self.typing_interval = out_cfg.get("typing_interval", 0.01)
        self.auto_space = out_cfg.get("auto_space", True)
        self.auto_period = out_cfg.get("auto_period", False)

        # 兜底
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.history_file = os.path.join(self.base_dir, "logs", "history.txt")
        self.overlay = overlay  # 用于悬浮窗提示
        self.last_text = ""

    def output(self, text):
        """
        将文字输出到当前活动窗口。

        Args:
            text: 要输出的文字
        """
        if not text:
            return "empty"

        text = text.strip()
        if self.auto_period:
            if text and text[-1] not in "。！？.!?,，；;：:":
                text += "。"
        self.last_text = text

        if self.mode == "clipboard":
            return "pasted" if self._paste(text) else "fallback"
        return "typed" if self._type(text) else "fallback"

    def repeat_last(self):
        """重新输出最近一次成功进入输出模块的文本"""
        if not self.last_text:
            return "empty"
        return self.output(self.last_text)

    def _paste(self, text):
        """通过剪贴板粘贴"""
        result = False

        try:

            # 复制新内容到剪贴板
            pyperclip.copy(text)
            time.sleep(0.05)

            # 模拟 Ctrl+V 粘贴
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)

            if self.auto_space:
                pyautogui.press("space")

            result = True


        except Exception as e:
            print(f"[OutputHandler] 粘贴失败: {e}")
            result = False

        if not result:
            self._fallback(text)

        return result

    def _fallback(self, text):
        """兜底：粘贴失败时存入剪贴板 + 本地历史 + 悬浮窗提示"""
        try:
            pyperclip.copy(text)
            print("[OutputHandler] 已存入剪贴板", flush=True)
        except Exception:
            print("[OutputHandler] 剪贴板存入失败", flush=True)

        # 写入本地历史
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")
            print(f"[OutputHandler] 已存入历史: {self.history_file}", flush=True)
        except Exception as e:
            print(f"[OutputHandler] 历史写入失败: {e}", flush=True)

        # 悬浮窗提示
        if self.overlay:
            try:
                self.overlay.show_error("粘贴失败，已存入剪贴板")
                self.overlay.hide_after(2000)
            except Exception:
                pass

        return False

    def _type(self, text):
        """模拟键盘输入"""
        try:
            pyautogui.write(text, interval=self.typing_interval)
            return True
        except Exception:
            # pyautogui.write 不支持中文，用 press 逐字符 fallback
            try:
                for char in text:
                    pyautogui.press(char)
                    time.sleep(self.typing_interval)
                return True
            except Exception:
                # 连键盘输入都失败了，走兜底
                self._fallback(text)
                return False
