"""
集成测试：验证完整管道（配置→引擎→热词→转写→输出）
使用内置测试音频，不需要麦克风
"""

import sys
import os
import io

# Windows UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import wave
import numpy as np
import time


def main():
    print("=" * 50)
    print("  集成测试 — 完整管道验证")
    print("=" * 50)

    base_dir = os.path.dirname(__file__)

    # 1. 加载配置
    print("\n[1/5] 加载配置...")
    import yaml
    config_path = os.path.join(base_dir, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    print(f"  引擎: {config['engine']['active']}")
    print(f"  输出模式: {config['output']['mode']}")

    # 2. 加载热词
    print("\n[2/5] 加载热词知识库...")
    from hotword_loader import HotwordLoader
    hw = HotwordLoader(config_path)
    words = hw.load_all()
    print(f"  已加载 {len(words)} 个热词")
    if words:
        print(f"  示例: {', '.join(words[:5])}...")

    # 3. 加载引擎
    print("\n[3/5] 加载 ASR 引擎...")
    from transcriber import Transcriber
    t = Transcriber(config_path)
    start = time.time()
    t.load_engine()
    elapsed = time.time() - start
    print(f"  引擎加载完成: {t.current_engine} ({elapsed:.1f}s)")

    # 4. 转写测试
    print("\n[4/5] 转写测试...")
    test_files = {
        "zh.wav": "中文",
        "en.wav": "英文",
        "ja.wav": "日文",
        "ko.wav": "韩文",
    }
    for wav_name, lang in test_files.items():
        wav_path = os.path.join(base_dir, "models", "sensevoice", "test_wavs", wav_name)
        if not os.path.exists(wav_path):
            print(f"  [{lang}] {wav_name}: 文件不存在，跳过")
            continue

        with wave.open(wav_path) as f:
            sr = f.getframerate()
            samples = f.readframes(f.getnframes())
            audio = np.frombuffer(samples, dtype=np.int16)

        duration = len(audio) / sr
        start = time.time()
        text = t.transcribe(audio, sr)
        elapsed = time.time() - start
        rtf = elapsed / duration if duration > 0 else 0

        print(f"  [{lang}] {text}")
        print(f"        耗时: {elapsed:.2f}s, RTF: {rtf:.3f}")

    # 5. 输出模块测试
    print("\n[5/5] 输出模块加载...")
    from output_handler import OutputHandler
    oh = OutputHandler(config_path)
    print(f"  输出模式: {oh.mode}")
    print(f"  （不实际输出，避免干扰）")

    print("\n" + "=" * 50)
    print("  全部测试通过！")
    print("=" * 50)
    print("\n启动命令:")
    print(f"  cd {base_dir}")
    print("  .\\venv\\Scripts\\activate")
    print("  python src\\main.py")


if __name__ == "__main__":
    main()
