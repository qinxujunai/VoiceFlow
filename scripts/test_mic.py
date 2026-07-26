"""
麦克风测试脚本
列出音频设备、录制短样本并验证语音活动

使用: python scripts/test_mic.py --duration 5
"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_activity import has_speech_activity


def _parser():
    parser = argparse.ArgumentParser(description="测试 VoiceFlow 麦克风和离线转写")
    parser.add_argument("--duration", type=float, default=5.0, help="录音秒数")
    parser.add_argument("--countdown", type=int, default=3, help="录音前倒计时秒数")
    parser.add_argument("--output", type=Path, help="可选 WAV 保存路径")
    parser.add_argument(
        "--no-transcribe",
        action="store_true",
        help="只测试采集和语音活动，不加载 ASR",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.duration < 0:
        raise SystemExit("--duration 不能小于 0")
    if args.countdown < 0:
        raise SystemExit("--countdown 不能小于 0")

    print("=" * 50)
    print("  麦克风测试")
    print("=" * 50)

    from audio_capture import AudioCapture

    devices = AudioCapture.list_devices()
    print(f"\n找到 {len(devices)} 个输入设备:")
    for d in devices:
        print(f"  [{d['index']}] {d['name']} (通道: {d['channels']}, 采样率: {d['sample_rate']:.0f})")

    if not devices:
        print("\n[错误] 未找到输入设备！")
        return 1

    print(f"\n使用默认设备录音 {args.duration:g} 秒...")
    print("请说话...")
    for remaining in range(args.countdown, 0, -1):
        print(f"{remaining}...")
        time.sleep(1)
    print("开始！")

    audio = AudioCapture()
    audio.start_recording()
    time.sleep(args.duration)
    data = audio.stop_recording()

    if len(data) == 0:
        print("\n[错误] 未采集到音频数据")
        return 1

    duration = len(data) / audio.sample_rate
    max_val = np.max(np.abs(data))
    speech_detected = has_speech_activity(data, audio.sample_rate)
    print("\n录音完成:")
    print(f"  时长: {duration:.1f}s")
    print(f"  采样数: {len(data)}")
    print(f"  最大振幅: {max_val}")
    print(f"  有效语音: {'是' if speech_detected else '否'}")

    if args.output:
        import soundfile as sf

        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, data.astype(np.float32) / 32768.0, audio.sample_rate)
        print(f"\n已保存到: {output_path}")

    if not speech_detected:
        print("\n[失败] 未检测到有效语音，已跳过 ASR，避免静音幻觉")
        return 2
    if args.no_transcribe:
        print("\n麦克风采集与语音活动测试通过")
        return 0

    print("\n尝试转写...")
    try:
        from transcriber import Transcriber

        t = Transcriber()
        t.load_engine()
        text = t.transcribe(data, audio.sample_rate)
        print(f"转写结果: {text}")
        return 0
    except FileNotFoundError:
        print("[跳过] 模型未下载，请先运行: python scripts/download_models.py")
        return 3
    except Exception as e:
        print(f"[转写失败] {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
