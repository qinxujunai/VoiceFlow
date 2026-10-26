"""Synthetic dictation for the stop-latency evaluation (docs/stop-latency-evaluation-2026-10-26.md).

Each utterance is a few phrases read by the Apache-2.0 MeloTTS zh_en voice with 0.6-1.0 s pauses between
phrases, the way people dictate. Synthetic speech checks the pipeline mechanics reproducibly; it is not an
accuracy corpus and no accuracy claim may be made from it.

    python scripts/make_dictation_samples.py <vits-melo-tts-zh_en dir> <output dir>
"""
import json, sys, wave, random
from pathlib import Path
import numpy as np
import sherpa_onnx

m = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(
    model=str(m/'model.onnx'), lexicon=str(m/'lexicon.txt'), tokens=str(m/'tokens.txt'), dict_dir=str(m/'dict')), num_threads=4),
    rule_fsts=f"{m/'date.fst'},{m/'phone.fst'},{m/'number.fst'}"))
U = [
 ["帮我把这个需求整理一下", "先列出现在的问题", "再给出两个方案", "最后估一下每个方案要几天"],
 ["今天下午三点和飞书那边开会", "主要聊多维表格的权限", "还有审批流程怎么迁移"],
 ["这个接口返回太慢了", "我怀疑是数据库没有加索引", "你先帮我看一下慢查询日志"],
 ["我觉得这一版首页还是太长", "用户滑到一半就没耐心了", "能不能把作品区往上提"],
 ["用 Claude Code 写一个脚本", "每天早上九点拉取最新的数据", "然后把结果发到群里"],
 ["这周的目标有三个", "第一是把简历改完", "第二是投十家公司", "第三是每天健身一小时"],
 ["客户说上线时间要提前一周", "我们需要重新排一下优先级", "非核心的功能先往后放"],
 ["把这段话翻译成英文", "语气要正式一点", "不要用太复杂的词"],
 ["模型的输出有时候会编造链接", "所以我们只让它引用编号", "链接由程序回填"],
 ["晚上回来记得买牛奶和鸡蛋", "顺便把快递取了", "明天早上要早点出门"],
 ["这个 bug 只在 Windows 上出现", "Mac 上一切正常", "可能和输入法有关"],
 ["我们下个月要做一次产品发布", "需要准备演示视频和新闻稿", "还要提前通知老客户"],
]
random.seed(7); meta = []
for i, phrases in enumerate(U):
    chunks = []
    for j, p in enumerate(phrases):
        a = tts.generate(p, sid=0, speed=1.0)
        chunks.append(np.asarray(a.samples, np.float32))
        if j < len(phrases) - 1: chunks.append(np.zeros(int(a.sample_rate * random.uniform(0.6, 1.0)), np.float32))
    x = np.concatenate([np.zeros(int(a.sample_rate*0.3), np.float32)] + chunks + [np.zeros(int(a.sample_rate*0.3), np.float32)])
    # resample to 16 kHz
    sr = a.sample_rate; n = int(len(x) * 16000 / sr)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    pcm = (np.clip(y, -1, 1) * 32767 * 0.9).astype(np.int16)
    with wave.open(str(out/f'u{i:02d}.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm.tobytes())
    meta.append({'wav': f'u{i:02d}.wav', 'reference': '，'.join(phrases), 'seconds': round(len(pcm)/16000, 1)})
json.dump(meta, open(out/'meta.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print([m_['seconds'] for m_ in meta])
