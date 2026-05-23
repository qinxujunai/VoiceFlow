"""
热词知识库加载模块
读取 knowledge-base/ 下的词表文件，合并为热词列表
"""

import os
import yaml


class HotwordLoader:
    """热词加载器"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self._hotwords = set()

    def load_all(self):
        """
        加载所有热词文件

        Returns:
            list: 去重后的热词列表
        """
        hw_cfg = self.config.get("hotwords", {})
        if not hw_cfg.get("enabled", False):
            return []

        hw_dir = os.path.join(self.base_dir, hw_cfg.get("directory", "knowledge-base"))
        files = hw_cfg.get("files", [])

        self._hotwords = set()

        for fname in files:
            fpath = os.path.join(hw_dir, fname)
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        word = line.strip()
                        if word and not word.startswith("#"):
                            self._hotwords.add(word)

        return sorted(self._hotwords)

    def add_hotword(self, word, category="user-custom"):
        """
        运行时添加热词

        Args:
            word: 热词
            category: 分类（对应文件名，不含 .txt）
        """
        if not word or not word.strip():
            return

        word = word.strip()
        self._hotwords.add(word)

        # 写入对应文件
        hw_cfg = self.config.get("hotwords", {})
        hw_dir = os.path.join(self.base_dir, hw_cfg.get("directory", "knowledge-base"))
        fpath = os.path.join(hw_dir, f"{category}.txt")

        with open(fpath, "a", encoding="utf-8") as f:
            f.write(f"{word}\n")

    def get_hotwords(self):
        """获取当前热词列表"""
        return sorted(self._hotwords)

    def get_count(self):
        """获取热词数量"""
        return len(self._hotwords)
