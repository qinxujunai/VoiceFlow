"""
模型下载脚本
从 HuggingFace 下载 SenseVoice-Small / Qwen3-ASR ONNX 模型

使用:
  python scripts/download_models.py                    # 下载 SenseVoice（默认）
  python scripts/download_models.py --engine qwen3-asr # 下载 Qwen3-ASR
  python scripts/download_models.py --all              # 下载全部
"""

import argparse
import os
import shutil
import sys
import tarfile
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from model_registry import load_model_manifest, sha256_file, verify_model_assets


SENSEVOICE_REQUIRED_FILES = ("model.int8.onnx", "tokens.txt")
QWEN3_ASR_REQUIRED_FILES = (
    "conv_frontend.onnx",
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "tokenizer",
)
FUN_ASR_NANO_REQUIRED_FILES = (
    "embedding.int8.onnx",
    "encoder_adaptor.int8.onnx",
    "llm.int8.onnx",
    "Qwen3-0.6B",
)
WHISPER_TURBO_REQUIRED_FILES = (
    "turbo-encoder.int8.onnx",
    "turbo-decoder.int8.onnx",
    "turbo-tokens.txt",
)

MANIFEST = load_model_manifest(ROOT / "model-manifest.json")


def _has_required_files(target_dir, filenames):
    return all(os.path.exists(os.path.join(target_dir, filename)) for filename in filenames)


def _download_pinned_model(base_dir, model_id):
    model = MANIFEST["models"][model_id]
    if model["source"].get("provider") == "github_release_archive":
        return _download_archive_model(base_dir, model_id)

    target_dir = Path(base_dir) / model["target_dir"]
    errors = verify_model_assets(target_dir, model) if target_dir.exists() else ["missing"]
    if not errors:
        print(f"[{model_id}] 模型已校验，跳过下载")
        return True

    partial_dir = target_dir.with_name(f"{target_dir.name}.partial")
    print(f"[{model_id}] 下载固定版本到: {partial_dir}")
    try:
        from huggingface_hub import snapshot_download

        source = model["source"]
        snapshot_download(
            repo_id=source["repo_id"],
            revision=source["revision"],
            local_dir=partial_dir,
            allow_patterns=[asset["path"] for asset in model["files"]],
        )
        errors = verify_model_assets(partial_dir, model)
        if errors:
            raise RuntimeError("; ".join(errors))

        if target_dir.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target_dir.with_name(f"{target_dir.name}.previous-{timestamp}")
            target_dir.rename(backup)
            print(f"[{model_id}] 旧目录保留为: {backup}")
        partial_dir.rename(target_dir)
        print(f"[{model_id}] 下载与 SHA-256 校验完成")
        return True
    except Exception as exc:
        print(f"[{model_id}] 下载失败，现有模型未被覆盖: {exc}")
        return False


def _download_archive_model(base_dir, model_id):
    model = MANIFEST["models"][model_id]
    source = model["source"]
    target_dir = Path(base_dir) / model["target_dir"]
    errors = verify_model_assets(target_dir, model) if target_dir.exists() else ["missing"]
    if not errors:
        print(f"[{model_id}] 模型已校验，跳过下载")
        return True

    partial_dir = target_dir.with_name(f"{target_dir.name}.partial")
    archive = partial_dir.with_suffix(".tar.bz2")
    print(f"[{model_id}] 下载固定归档到: {archive}")
    try:
        if partial_dir.exists():
            shutil.rmtree(partial_dir)
        if archive.exists():
            archive.unlink()
        partial_dir.mkdir(parents=True)
        urllib.request.urlretrieve(source["url"], archive)
        if archive.stat().st_size != int(source["archive_size"]):
            raise RuntimeError("archive size mismatch")
        if sha256_file(archive).lower() != source["archive_sha256"].lower():
            raise RuntimeError("archive sha256 mismatch")

        archive_root = source["archive_root"].rstrip("/")
        with tarfile.open(archive, "r:bz2") as bundle:
            members = {
                member.name.removeprefix("./"): member
                for member in bundle.getmembers()
            }
            for asset in model["files"]:
                member_name = f"{archive_root}/{asset['path']}"
                member = members.get(member_name)
                if member is None:
                    raise RuntimeError(f"archive member not found: {member_name}")
                if not member.isfile():
                    raise RuntimeError(f"archive member is not a file: {member_name}")
                destination = partial_dir / asset["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                source_file = bundle.extractfile(member)
                if source_file is None:
                    raise RuntimeError(f"cannot read archive member: {member_name}")
                with source_file, destination.open("wb") as output:
                    shutil.copyfileobj(source_file, output)

        errors = verify_model_assets(partial_dir, model)
        if errors:
            raise RuntimeError("; ".join(errors))
        if target_dir.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target_dir.with_name(f"{target_dir.name}.previous-{timestamp}")
            target_dir.rename(backup)
            print(f"[{model_id}] 旧目录保留为: {backup}")
        partial_dir.rename(target_dir)
        print(f"[{model_id}] 下载与 SHA-256 校验完成")
        return True
    except Exception as exc:
        print(f"[{model_id}] 下载失败，现有模型未被覆盖: {exc}")
        return False
    finally:
        if archive.exists():
            archive.unlink()


def download_sensevoice(base_dir):
    """下载 SenseVoice-Small ONNX 模型（sherpa-onnx 预导出版）"""
    return _download_pinned_model(base_dir, "sensevoice-small-int8")


def download_streaming_preview(base_dir):
    """下载胶囊使用的中英双语实时预览模型。"""
    return _download_pinned_model(
        base_dir,
        "streaming-zipformer-small-bilingual-zh-en-int8",
    )


def download_streaming_paraformer(base_dir):
    """下载双语 Paraformer 实时预览实验模型。"""
    return _download_pinned_model(
        base_dir,
        "streaming-paraformer-bilingual-zh-en-int8",
    )


def download_streaming_zipformer_2025_06_30(base_dir):
    """下载 2025-06-30 中文 Zipformer CTC 实验模型。"""
    return _download_pinned_model(
        base_dir,
        "streaming-zipformer-ctc-zh-int8-2025-06-30",
    )


def download_qwen3_asr(base_dir):
    """下载 sherpa-onnx 可直接加载的 Qwen3-ASR 0.6B int8 模型"""
    return _download_pinned_model(base_dir, "qwen3-asr-0.6b-int8")


def download_fun_asr_nano(base_dir):
    """下载 sherpa-onnx Fun-ASR-Nano 0.8B int8 模型。"""
    return _download_pinned_model(base_dir, "fun-asr-nano-0.8b-int8")


def download_whisper_turbo(base_dir):
    """下载 Whisper large-v3-turbo int8 多语言对照模型。"""
    return _download_pinned_model(base_dir, "whisper-large-v3-turbo-int8")


def main():
    parser = argparse.ArgumentParser(description="下载 ASR 模型")
    parser.add_argument(
        "--engine",
        choices=[
            "sensevoice",
            "streaming-preview",
            "streaming-paraformer",
            "streaming-zipformer-2025-06-30",
            "qwen3-asr",
            "fun-asr-nano",
            "whisper-turbo",
        ],
        default="sensevoice",
    )
    parser.add_argument("--all", action="store_true", help="下载全部模型")
    parser.add_argument(
        "--base-dir",
        default=str(ROOT),
        help="模型写入根目录；桌面运行时使用用户数据目录",
    )
    args = parser.parse_args()

    base_dir = os.path.abspath(args.base_dir)

    if args.all:
        succeeded = all((
            download_sensevoice(base_dir),
            download_streaming_preview(base_dir),
            download_qwen3_asr(base_dir),
            download_fun_asr_nano(base_dir),
            download_whisper_turbo(base_dir),
        ))
    elif args.engine == "sensevoice":
        succeeded = download_sensevoice(base_dir)
    elif args.engine == "streaming-preview":
        succeeded = download_streaming_preview(base_dir)
    elif args.engine == "streaming-paraformer":
        succeeded = download_streaming_paraformer(base_dir)
    elif args.engine == "streaming-zipformer-2025-06-30":
        succeeded = download_streaming_zipformer_2025_06_30(base_dir)
    elif args.engine == "qwen3-asr":
        succeeded = download_qwen3_asr(base_dir)
    elif args.engine == "fun-asr-nano":
        succeeded = download_fun_asr_nano(base_dir)
    elif args.engine == "whisper-turbo":
        succeeded = download_whisper_turbo(base_dir)
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
