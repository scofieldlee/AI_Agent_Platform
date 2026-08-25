"""音频处理器 — ASR 转写 / 分段 / 知识单元生成（Phase 5）.

ASR: DashScope Recognition API (paraformer-realtime-v2)，支持本地文件，
逐句返回 begin_time/end_time/text，天然形成 Segment。
"""

import logging
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.multimodal.constants import AssetStatus, UnitType, UnitStatus, FileType
from app.multimodal.repositories import asset_repo, knowledge_unit_repo
from app.multimodal.services import storage_service, analysis_service

logger = logging.getLogger(__name__)


async def transcribe_audio(abs_path: str, model: str = None) -> List[Dict]:
    """本地音频文件转写。返回 [{begin_time, end_time, text}]（毫秒时间戳）。"""
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置：无法执行语音识别")

    import dashscope
    from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

    sentences: List[Dict] = []

    class _Callback(RecognitionCallback):
        def on_result(self, result: RecognitionResult):
            payload = result.get("output", {}).get("sentence", {})
            if payload.get("text"):
                sentences.append({
                    "begin_time": payload.get("begin_time", 0),
                    "end_time": payload.get("end_time", 0),
                    "text": payload.get("text", ""),
                })

    callback = _Callback()
    recognition = Recognition(
        model=model or settings.qwen_asr_model,
        format=_audio_format(abs_path),
        sample_rate=16000,
        callback=callback,
    )
    try:
        recognition.call(audio_file=abs_path)
    except Exception as e:
        raise RuntimeError(f"ASR 转写失败: {e}")
    return sentences


def _audio_format(path: str) -> str:
    """路径 → DashScope 音频格式。"""
    ext = path.rsplit(".", 1)[-1].lower()
    return {
        "mp3": "mp3", "wav": "wav", "flac": "flac",
        "aac": "aac", "ogg": "ogg", "m4a": "m4a",
        "wma": "wma",
    }.get(ext, "wav")


def merge_sentences(sentences: List[Dict], max_segment_sec: float = 30.0) -> List[Dict]:
    """把 ASR 句子合并为语义分段（目标 15-30 秒/段，按停顿切分）。"""
    segments = []
    current = None
    for s in sentences:
        if current is None:
            current = {"begin_time": s["begin_time"], "end_time": s["end_time"],
                       "texts": [s["text"]]}
            continue
        seg_len = (s["end_time"] - current["begin_time"]) / 1000.0
        gap = (s["begin_time"] - current["end_time"]) / 1000.0
        if seg_len >= max_segment_sec or gap > 2.0:  # 超长 或 停顿>2s → 断段
            segments.append(current)
            current = {"begin_time": s["begin_time"], "end_time": s["end_time"],
                       "texts": [s["text"]]}
        else:
            current["end_time"] = s["end_time"]
            current["texts"].append(s["text"])
    if current:
        segments.append(current)
    return segments


async def process(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """音频素材处理主流程: ASR → 分段 → Segment units → REVIEW_REQUIRED."""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}
    if not asset.storage_path:
        return {"success": False, "error": "Asset has no storage_path"}

    abs_path = storage_service.abs_file_path(asset.storage_path)
    kb_id, aid = asset.knowledge_base_id, asset.id

    # 1. ASR 转写
    try:
        sentences = await transcribe_audio(abs_path)
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    if not sentences:
        return {"success": False, "error": "ASR 未返回任何转写内容"}

    # 2. 全文存 derived 文件 + system metadata
    full_transcript = "".join(s["text"] for s in sentences)
    import aiofiles
    transcript_rel = storage_service.derived_file_path(kb_id, aid, "transcript.txt")
    async with aiofiles.open(storage_service.abs_file_path(transcript_rel), "w",
                             encoding="utf-8") as f:
        await f.write(full_transcript)

    system_meta = (await asset_repo.get_all_metadata(db, asset_id)).get("system", {})
    system_meta.update({"transcript_chars": len(full_transcript),
                        "sentence_count": len(sentences)})
    await asset_repo.upsert_metadata(db, asset_id, "system", system_meta)

    # 3. 分段 → 知识单元
    await knowledge_unit_repo.delete_units_by_asset(db, asset_id)
    segments = merge_sentences(sentences)
    for i, seg in enumerate(segments):
        transcript = "".join(seg["texts"])
        unit = await knowledge_unit_repo.create_unit(
            db, knowledge_base_id=kb_id, asset_id=aid,
            unit_type=UnitType.SEGMENT, unit_index=i,
            start_time=seg["begin_time"] / 1000.0, end_time=seg["end_time"] / 1000.0,
            status=UnitStatus.PENDING)
        await knowledge_unit_repo.create_audio_segment(
            db, unit_id=unit.id, asset_id=aid, segment_index=i,
            start_time=seg["begin_time"] / 1000.0, end_time=seg["end_time"] / 1000.0,
            transcript=transcript)
        await analysis_service.analyze_audio_unit(db, aid, unit, transcript)

    # 4. AI metadata（整体描述）
    await asset_repo.upsert_metadata(db, asset_id, "ai", {
        "description": f"音频素材，共 {len(segments)} 段转写，总字数 {len(full_transcript)}",
        "tags": [FileType.AUDIO, "转写"],
    })
    await asset_repo.replace_ai_tags(db, asset_id, ["音频", "语音转写"])

    # 5. 状态
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})
    return {"success": True, "segments": len(segments),
            "transcript_chars": len(full_transcript)}
