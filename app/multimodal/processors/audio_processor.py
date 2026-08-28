"""音频处理器 — ASR 转写 / 分段 / 知识单元生成（Phase 5）.

ASR: DashScope Recognition API (paraformer-realtime-v2)，支持本地文件，
逐句返回 begin_time/end_time/text，天然形成 Segment。
"""

import logging
from typing import Dict, Any, List, Optional

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
        # dashscope >=1.20 的签名为 call(file, ...)，旧写法 audio_file= 会 TypeError
        recognition.call(abs_path)
    except TypeError:
        # 兼容极旧版本 SDK 的关键字参数
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
    """音频素材处理主流程: ASR → 分段 → Segment units → REVIEW_REQUIRED.

    ASR 不可用（无 Key / 模型无权限 / SDK 异常）时降级为「元数据分段」，
    按时长切分生成可检索的文本单元，保证音频仍能被向量化索引。
    """
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}
    if not asset.storage_path:
        return {"success": False, "error": "Asset has no storage_path"}

    abs_path = storage_service.abs_file_path(asset.storage_path)
    kb_id, aid = asset.knowledge_base_id, asset.id
    filename = asset.original_filename or asset.name or ""

    # 1. ASR 转写（失败不直接失败，降级处理）
    asr_error: Optional[str] = None
    sentences: List[Dict] = []
    try:
        sentences = await transcribe_audio(abs_path)
    except Exception as e:  # RuntimeError / SDK 异常统一降级
        asr_error = str(e)
        logger.warning(f"ASR unavailable for asset {asset_id}, "
                       f"degrade to metadata units: {e}")

    # 2a. 正常路径：全文存 derived 文件 + 分段单元
    if sentences:
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

        await asset_repo.upsert_metadata(db, asset_id, "ai", {
            "description": f"音频素材，共 {len(segments)} 段转写，总字数 {len(full_transcript)}",
            "tags": ["音频", "语音转写"],
        })
        await asset_repo.replace_ai_tags(db, asset_id, ["音频", "语音转写"])
        await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})
        return {"success": True, "segments": len(segments),
                "transcript_chars": len(full_transcript), "asr": True}

    # 2b. 降级路径：无转写 → 按时长切元数据分段（仍可被文本 Embedding 检索）
    duration = await _audio_duration(abs_path)
    seg_len = 30.0
    seg_count = max(1, min(int((duration or 30.0) / seg_len) + 1, 200))
    await knowledge_unit_repo.delete_units_by_asset(db, asset_id)
    for i in range(seg_count):
        start = i * seg_len
        end = min((i + 1) * seg_len, duration or (i + 1) * seg_len)
        content = (
            f"音频素材: {filename} · 第 {i + 1}/{seg_count} 段 "
            f"({start:.0f}s-{end:.0f}s)。该段暂无语音转写文本，"
            f"可通过文件名与时间段检索。"
        )
        unit = await knowledge_unit_repo.create_unit(
            db, knowledge_base_id=kb_id, asset_id=aid,
            unit_type=UnitType.SEGMENT, unit_index=i,
            start_time=start, end_time=end, status=UnitStatus.PENDING)
        await knowledge_unit_repo.create_audio_segment(
            db, unit_id=unit.id, asset_id=aid, segment_index=i,
            start_time=start, end_time=end, transcript="")
        await analysis_service.analyze_audio_unit(
            db, aid, unit, content,
            segment_meta={"degraded": True, "asr_error": (asr_error or "")[:200]})

    await asset_repo.upsert_metadata(db, asset_id, "ai", {
        "description": f"音频素材（{duration:.0f} 秒），语音转写不可用，已按时长分段建立可检索索引",
        "tags": ["音频"],
        "asr_available": False,
    })
    await asset_repo.replace_ai_tags(db, asset_id, ["音频"])
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})
    return {"success": True, "segments": seg_count, "asr": False,
            "asr_error": (asr_error or "")[:500]}


async def _audio_duration(abs_path: str) -> Optional[float]:
    """ffprobe 读取音频时长（秒）。不可用返回 None。"""
    import shutil as _shutil
    import asyncio as _asyncio
    ffprobe = _shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = await _asyncio.create_subprocess_exec(
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", abs_path,
            stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE)
        out, _ = await _asyncio.wait_for(proc.communicate(), timeout=30)
        return float(out.decode().strip())
    except Exception:
        return None
