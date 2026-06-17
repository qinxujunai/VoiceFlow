"""
模型下载脚本
从 HuggingFace 下载 SenseVoice-Small / Qwen3-ASR ONNX 模型

使用:
  python scripts/download_models.py                    # 下载 SenseVoice（默认）
  python scripts/download_models.py --engine qwen3-asr # 下载 Qwen3-ASR
  python scripts/download_models.py --all              # 下载全部
"""

import os
import sys
import argparse


SENSEVOICE_REQUIRED_FILES = ("model.int8.onnx", "tokens.txt")
QWEN3_ASR_REQUIRED_FILES = ("model.onnx", "tokens.txt")


def _has_required_files(target_dir, filenames):
    return all(os.path.exists(os.path.join(target_dir, filename)) for filename in filenames)


def download_sensevoice(base_dir):
    """下载 SenseVoice-Small ONNX 模型（sherpa-onnx 预导出版）"""
    target_dir = os.path.join(base_dir, "models", "sensevoice")

    if _has_required_files(target_dir, SENSEVOICE_REQUIRED_FILES):
        print("[SenseVoice] 模型已存在，跳过下载")
        return True

    print("[SenseVoice] 下载 sherpa-onnx 预导出 SenseVoice ONNX 模型...")
    print(f"[SenseVoice] 目标目录: {target_dir}")

    try:
        from huggingface_hub import snapshot_download

        # 使用 csukuangfj 预导出的 ONNX 版本（sherpa-onnx 官方推荐）
        snapshot_download(
            repo_id="csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
            local_dir=target_dir,
        )
        if not _has_required_files(target_dir, SENSEVOICE_REQUIRED_FILES):
            raise FileNotFoundError(
                "downloaded SenseVoice files are not sherpa-onnx ready "
                f"(expected {', '.join(SENSEVOICE_REQUIRED_FILES)})"
            )
        print("[SenseVoice] 下载完成")
        return True
    except Exception as e:
        print(f"[SenseVoice] 下载失败: {e}")
        return False


def download_qwen3_asr(base_dir):
    """下载 sherpa-onnx 可直接加载的 Qwen3-ASR 0.6B int8 模型"""
    target_dir = os.path.join(base_dir, "models", "qwen3-asr")

    if _has_required_files(target_dir, QWEN3_ASR_REQUIRED_FILES):
        print("[Qwen3-ASR] 模型已存在，跳过下载")
        return True

    print("[Qwen3-ASR] 下载模型文件...")
    print(f"[Qwen3-ASR] 目标目录: {target_dir}")

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id="pantinor/sherpa-onnx-qwen3-asr-0.6b-int8",
            local_dir=target_dir,
            allow_patterns=["*.onnx", "*.txt", "*.yaml", "*.json", "*.bin", "*.data"],
        )
        if not _has_required_files(target_dir, QWEN3_ASR_REQUIRED_FILES):
            raise FileNotFoundError(
                "downloaded Qwen3-ASR files are not sherpa-onnx ready "
                f"(expected {', '.join(QWEN3_ASR_REQUIRED_FILES)})"
            )
        print("[Qwen3-ASR] 下载完成")
        return True
    except Exception as e:
        print(f"[Qwen3-ASR] 下载失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="下载 ASR 模型")
    parser.add_argument("--engine", choices=["sensevoice", "qwen3-asr"], default="sensevoice")
    parser.add_argument("--all", action="store_true", help="下载全部模型")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(__file__))

    if args.all:
        download_sensevoice(base_dir)
        download_qwen3_asr(base_dir)
    elif args.engine == "sensevoice":
        download_sensevoice(base_dir)
    elif args.engine == "qwen3-asr":
        download_qwen3_asr(base_dir)


if __name__ == "__main__":
    main()
