"""视频处理器 — 元数据提取 / 预览 / 缩略图 / 镜头检测 / 关键帧 / 逐镜头 AI 分析（Phase 4）.

工具链: ffmpeg/ffprobe（系统依赖）+ PySceneDetect（可选）+ 通义千问 VL。
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.constants import AssetStatus, UnitType, UnitStatus
from app.multimodal.repositories import asset_repo, knowledge_unit_repo
from app.multimodal.services import analysis_service, storage_service
from app.multimodal.adapters.storage.local_storage import LocalStorageAdapter

logger = logging.getLogger(__name__)


async def _run(cmd: List[str], timeout: int = 600) -> tuple:
    """执行本地命令，返回 (returncode, stdout, stderr)。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode("utf-8", errors="ignore"), stderr.decode("utf-8", errors="ignore")
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"Command timeout after {timeout}s: {' '.join(cmd[:3])}...")


async def probe_video(abs_path: str) -> Dict[str, Any]:
    """ffprobe 提取视频元数据。"""
    code, out, err = await _run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", abs_path])
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err[:300]}")
    data = json.loads(out)
    fmt = data.get("format", {})
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    duration = float(fmt.get("duration", 0) or 0)
    width, height = video_stream.get("width"), video_stream.get("height")
    return {
        "duration": duration,
        "width": width, "height": height,
        "resolution": f"{width}x{height}" if width else None,
        "fps": _parse_fps(video_stream.get("avg_frame_rate")),
        "codec": video_stream.get("codec_name"),
        "aspect_ratio": _parse_aspect(width, height),
        "has_audio": bool(audio_stream),
        "audio_codec": audio_stream.get("codec_name"),
        "bit_rate": fmt.get("bit_rate"),
    }


def _parse_fps(rate: Optional[str]) -> Optional[float]:
    if not rate or rate == "0/0":
        return None
    try:
        num, den = rate.split("/")
        return round(float(num) / float(den), 2) if float(den) else None
    except (ValueError, ZeroDivisionError):
        return None


def _parse_aspect(w: Optional[int], h: Optional[int]) -> Optional[str]:
    if not w or not h:
        return None
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


async def generate_preview(db_asset, abs_path: str) -> Optional[str]:
    """生成 720p 预览视频。"""
    preview_rel = LocalStorageAdapter.preview_path(
        db_asset.knowledge_base_id, db_asset.id) + ".mp4"
    preview_abs = storage_service.abs_file_path(preview_rel)
    os.makedirs(os.path.dirname(preview_abs), exist_ok=True)
    code, _, err = await _run([
        "ffmpeg", "-y", "-i", abs_path,
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k", preview_abs], timeout=1800)
    if code != 0:
        logger.warning(f"Preview generation failed: {err[:200]}")
        return None
    return preview_rel


async def generate_thumbnail(db_asset, abs_path: str) -> Optional[str]:
    """抽取第1秒视频帧作为缩略图。"""
    thumb_rel = LocalStorageAdapter.thumbnail_path(db_asset.knowledge_base_id, db_asset.id)
    thumb_abs = storage_service.abs_file_path(thumb_rel)
    os.makedirs(os.path.dirname(thumb_abs), exist_ok=True)
    code, _, err = await _run([
        "ffmpeg", "-y", "-ss", "1", "-i", abs_path,
        "-frames:v", "1", "-vf", "scale=320:-2", thumb_abs], timeout=120)
    if code != 0:
        # 视频短于1秒，从第0秒抽
        code, _, err = await _run([
            "ffmpeg", "-y", "-i", abs_path,
            "-frames:v", "1", "-vf", "scale=320:-2", thumb_abs], timeout=120)
        if code != 0:
            logger.warning(f"Thumbnail generation failed: {err[:200]}")
            return None
    return thumb_rel


async def detect_shots(abs_path: str) -> List[Dict[str, float]]:
    """镜头检测。优先 PySceneDetect，降级 ffmpeg 场景阈值。

    返回 [{start, end}]（秒）。
    """
    # 1. PySceneDetect
    try:
        from scenedetect import detect, ContentDetector
        scene_list = detect(abs_path, ContentDetector())
        shots = [{"start": s[0].get_seconds(), "end": s[1].get_seconds()}
                 for s in scene_list]
        if shots:
            return shots
    except ImportError:
        logger.info("PySceneDetect not installed, fallback to ffmpeg scene filter")
    except Exception as e:
        logger.warning(f"PySceneDetect failed: {e}, fallback to ffmpeg")

    # 2. ffmpeg scene filter（select 场景分数 > 0.3）
    code, out, _ = await _run([
        "ffmpeg", "-i", abs_path, "-vf",
        "select='gt(scene,0.3)',showinfo", "-f", "null", "-"], timeout=1800)
    shots = []
    import re
    times = [float(m) for m in re.findall(r"pts_time:([\d.]+)", out)]
    duration = await _get_duration(abs_path)
    if times:
        boundaries = [0.0] + times + [duration]
        for i in range(len(boundaries) - 1):
            if boundaries[i + 1] - boundaries[i] >= 0.5:  # 忽略过短镜头
                shots.append({"start": boundaries[i], "end": boundaries[i + 1]})
    if not shots:
        shots = [{"start": 0.0, "end": duration}]
    return shots


async def _get_duration(abs_path: str) -> float:
    code, out, _ = await _run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-print_format", "json", abs_path])
    try:
        return float(json.loads(out)["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return 0.0


async def extract_keyframe(db_asset, abs_path: str, shot: Dict[str, float],
                           shot_index: int) -> Optional[str]:
    """抽取镜头中间帧作为关键帧。"""
    mid = (shot["start"] + shot["end"]) / 2
    kf_rel = storage_service.derived_file_path(
        db_asset.knowledge_base_id, db_asset.id, f"keyframe_{shot_index:03d}.jpg")
    kf_abs = storage_service.abs_file_path(kf_rel)
    os.makedirs(os.path.dirname(kf_abs), exist_ok=True)
    code, _, _ = await _run([
        "ffmpeg", "-y", "-ss", str(mid), "-i", abs_path,
        "-frames:v", "1", "-vf", "scale=640:-2", kf_abs], timeout=120)
    return kf_rel if code == 0 else None


async def process(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """视频素材处理主流程（Worker 调用）:
    probe → preview → thumbnail → shot detect → keyframes → 逐镜头分析 → units
    """
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}

    # 0. 工具检查
    if not await _has_ffmpeg():
        return {"success": False, "error": "服务器未安装 ffmpeg，无法处理视频"}

    abs_path = storage_service.abs_file_path(asset.storage_path)
    kb_id, aid = asset.knowledge_base_id, asset.id

    # 1. 元数据提取
    try:
        video_meta = await probe_video(abs_path)
    except RuntimeError as e:
        return {"success": False, "error": f"视频解析失败: {e}"}

    system_meta = (await asset_repo.get_all_metadata(db, asset_id)).get("system", {})
    system_meta.update(video_meta)
    await asset_repo.upsert_metadata(db, asset_id, "system", system_meta)

    # 2. 预览 + 缩略图
    updates = {}
    preview_rel = await generate_preview(asset, abs_path)
    if preview_rel:
        updates["preview_path"] = preview_rel
    thumb_rel = await generate_thumbnail(asset, abs_path)
    if thumb_rel:
        updates["thumbnail_path"] = thumb_rel
    if updates:
        asset = await asset_repo.update_asset(db, asset, updates)

    # 3. 镜头检测 + 关键帧
    shots = await detect_shots(abs_path)
    logger.info(f"Video asset {asset_id}: {len(shots)} shots detected")

    # 4. 重建知识单元（清除旧 units）
    await knowledge_unit_repo.delete_units_by_asset(db, asset_id)

    analyzed = 0
    analysis_errors = 0
    for i, shot in enumerate(shots):
        # 创建 unit
        unit = await knowledge_unit_repo.create_unit(
            db, knowledge_base_id=kb_id, asset_id=aid,
            unit_type=UnitType.SHOT, unit_index=i,
            start_time=shot["start"], end_time=shot["end"],
            status=UnitStatus.PENDING)
        await knowledge_unit_repo.create_video_shot(
            db, unit_id=unit.id, asset_id=aid, shot_index=i,
            start_time=shot["start"], end_time=shot["end"],
            duration=shot["end"] - shot["start"])

        # 抽关键帧
        kf_rel = await extract_keyframe(asset, abs_path, shot, i)
        if kf_rel:
            await knowledge_unit_repo.update_unit(db, unit, {"thumbnail_path": kf_rel})
            from sqlalchemy import update
            from app.multimodal.models import VideoShot
            await db.execute(update(VideoShot).where(VideoShot.unit_id == unit.id)
                             .values(keyframe_path=kf_rel, thumbnail_path=kf_rel))
            await db.flush()

        # 逐镜头 AI 分析（Vision Adapter；失败不中断整体流程）
        if kf_rel:
            try:
                await analysis_service.analyze_visual_unit(
                    db, asset_id, storage_service.abs_file_path(kf_rel), unit)
                analyzed += 1
            except Exception as e:
                analysis_errors += 1
                logger.warning(f"Shot {i} analysis failed: {e}")

    # 5. 状态流转
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})
    return {
        "success": True,
        "shots": len(shots), "analyzed": analyzed,
        "analysis_errors": analysis_errors,
        "duration": video_meta.get("duration"),
        "has_preview": bool(preview_rel),
    }


async def _has_ffmpeg() -> bool:
    code, _, _ = await _run(["ffmpeg", "-version"], timeout=10)
    return code == 0
