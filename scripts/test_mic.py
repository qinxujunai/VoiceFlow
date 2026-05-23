"""
麦克风测试脚本
列出音频设备、录制 5 秒、回放验证

使用: python scripts/test_mic.py
"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    print("=" * 50)
    print("  麦克风测试")
    print("=" * 50)

    # 1. 列出设备
    from audio_capture import AudioCapture
    devices = AudioCapture.list_devices()
    print(f"\n找到 {len(devices)} 个输入设备:")
    for d in devices:
        print(f"  [{d['index']}] {d['name']} (通道: {d['channels']}, 采样率: {d['sample_rate']:.0f})")

    if not devices:
        print("\n[错误] 未找到输入设备！")
        return

    # 2. 录音测试
    print(f"\n使用默认设备录音 5 秒...")
    print("请说话...")
    print("3...")
    time.sleep(1)
    print("2...")
    time.sleep(1)
    print("1...")
    time.sleep(1)
    print("开始！")

    audio = AudioCapture()
    audio.start_recording()
    time.sleep(5)
    data = audio.stop_recording()

    if len(data) == 0:
        print("\n[错误] 未采集到音频数据")
        return

    duration = len(data) / audio.sample_rate
    max_val = np.max(np.abs(data))
    print(f"\n录音完成:")
    print(f"  时长: {duration:.1f}s")
    print(f"  采样数: {len(data)}")
    print(f"  最大振幅: {max_val}")
    print(f"  是否有声音: {'是' if max_val > 500 else '否（可能静音）'}")

    # 3. 保存到文件
    output_path = os.path.join(os.path.dirname(__file__), "..", "test_recording.wav")
    import soundfile as sf
    sf.write(output_path, data.astype(np.float32) / 32768.0, audio.sample_rate)
    print(f"\n已保存到: {os.path.abspath(output_path)}")

    # 4. 尝试转写
    print("\n尝试转写...")
    try:
        from transcriber import Transcriber
        t = Transcriber()
        t.load_engine()
        text = t.transcribe(data, audio.sample_rate)
        print(f"转写结果: {text}")
    except FileNotFoundError:
        print("[跳过] 模型未下载，请先运行: python scripts/download_models.py")
    except Exception as e:
        print(f"[转写失败] {e}")


if __name__ == "__main__":
    main()
