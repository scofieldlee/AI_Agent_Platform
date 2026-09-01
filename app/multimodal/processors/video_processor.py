"""视频处理器 — 元数据提取 / 预览 / 缩略图 / 镜头检测 / 关键帧 / 逐镜头 AI 分析（Phase 4）.

工具链: ffmpeg/ffprobe（系统依赖）+ PySceneDetect（可选）+ 通义千问 VL。
"""

import asyncio
import json
import logging
import os
import shutil
from functools import lru_cache
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.multimodal.constants import AssetStatus, UnitType, UnitStatus
from app.multimodal.repositories import asset_repo, knowledge_unit_repo
from app.multimodal.services import analysis_service, storage_service
from app.multimodal.adapters.storage.local_storage import LocalStorageAdapter

logger = logging.getLogger(__name__)

# ffmpeg/ffprobe 常见安装位置（homebrew / 源码编译 / 系统包管理器）
_BIN_SEARCH_DIRS = (
    "/usr/local/bin", "/opt/homebrew/bin", "/opt/local/bin",
    "/usr/bin", "/bin", "/usr/sbin", "/sbin",
)


@lru_cache(maxsize=None)
def _resolve_bin(name: str) -> str:
    """解析外部命令绝对路径。

    ⚠️ 历史坑位：直接 `subprocess_exec("ffmpeg", ...)` 依赖进程继承的 PATH。
    launchd / systemd / cron 拉起的 Worker 的 PATH 通常只有 `/usr/bin:/bin`，
    而 homebrew 装的 ffmpeg 在 `/usr/local/bin` → FileNotFoundError。
    故这里做 which + 常见目录兜底，找到即用绝对路径调用。
    """
    found = shutil.which(name)
    if found:
        return found
    for d in _BIN_SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            logger.debug(f"Resolved {name} -> {p} (not on PATH)")
            return p
    logger.warning(f"Command '{name}' not found on PATH or in {_BIN_SEARCH_DIRS}")
    return name  # 保留原名，由调用方产生明确错误


async def _run(cmd: List[str], timeout: int = 600) -> tuple:
    """执行本地命令，返回 (returncode, stdout, stderr)。

    命令名（非路径）会先经 _resolve_bin 解析为绝对路径。
    """
    if cmd and not os.path.isabs(cmd[0]) and "/" not in cmd[0]:
        cmd = [_resolve_bin(cmd[0])] + list(cmd[1:])
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
    """镜头检测。返回 [{start, end, score}]（秒，按时间升序，首尾闭合）。

    三级策略：
      1. PySceneDetect（可选后端，需 video_shot_backend=scenedetect）
      2. ffmpeg scene filter（**主路径**）
      3. 等间隔兜底（固定 ~10s 一段，优于"整段 1 个镜头"）

    ⚠️ 历史坑位（勿回退）：
      - ffmpeg 的 showinfo / metadata 输出走 **stderr 日志流**，不是 stdout。
        旧实现只读 stdout → 永远匹配不到切点 → 退化为"整段 1 个镜头"。
      - PySceneDetect 0.7.1 + OpenCV 5.0 不兼容：`CAP_PROP_POS_MSEC` 返回 NaN
        → `ValueError: cannot convert float NaN to integer`。故默认走 ffmpeg。

    后处理（_postprocess_shots）：合并过短镜头 → 按场景分数保留 topN → 限幅。
    """
    duration = await _get_duration(abs_path)
    if duration <= 0:
        logger.warning(f"Cannot probe duration for {abs_path}, fallback to single shot")
        return _postprocess_shots([], 0.0)

    shots: List[Dict[str, float]] = []

    # 1. PySceneDetect（可选）
    if settings.video_shot_backend == "scenedetect":
        shots = await _detect_shots_scenedetect(abs_path)

    # 2. ffmpeg scene filter（主路径）
    if not shots:
        shots = await _detect_shots_ffmpeg(abs_path, duration)

    # 3. 等间隔兜底
    if not shots:
        logger.info(f"No scene change detected in {abs_path}, fallback to uniform slicing")
        shots = _uniform_shots(duration)

    return _postprocess_shots(shots, duration)


async def _detect_shots_scenedetect(abs_path: str) -> List[Dict[str, float]]:
    """PySceneDetect ContentDetector。失败返回空列表交由 ffmpeg 兜底。"""
    try:
        from scenedetect import detect, ContentDetector
        scene_list = await asyncio.to_thread(detect, abs_path, ContentDetector())
        return [{"start": float(s[0].get_seconds()), "end": float(s[1].get_seconds()),
                 "score": 0.0} for s in (scene_list or [])]
    except ImportError:
        logger.info("PySceneDetect not installed, fallback to ffmpeg scene filter")
    except Exception as e:
        # OpenCV 5.x 下 CAP_PROP_POS_MSEC 返回 NaN 会在此抛出 ValueError
        logger.warning(f"PySceneDetect failed ({type(e).__name__}: {e}), fallback to ffmpeg")
    return []


async def _detect_shots_ffmpeg(abs_path: str, duration: float) -> List[Dict[str, float]]:
    """ffmpeg scene filter 切片。

    `metadata=print:file=-` 把"pts_time + lavfi.scene_score"写到 stdout，单次扫描即可
    同时拿到切点时间与置信度；旧版 ffmpeg 会写到日志流，故 stdout 无命中时再读 stderr。
    """
    import re
    threshold = settings.video_shot_threshold
    code, out, err = await _run([
        "ffmpeg", "-v", "quiet", "-i", abs_path, "-vf",
        f"select='gt(scene,{threshold})',metadata=print:file=-",
        "-f", "null", "-"], timeout=1800)

    blob = out or ""
    if "pts_time" not in blob:
        blob = err or ""
    if "pts_time" not in blob:
        logger.warning(f"ffmpeg scene detection produced no output (code={code})")
        return []

    # 逐行解析：frame 行给出 pts_time，紧跟的 metadata 行给出 scene_score
    marks: List[tuple] = []
    pending_time: Optional[float] = None
    for line in blob.splitlines():
        m_t = re.search(r"pts_time:([\d.]+)", line)
        if m_t:
            pending_time = float(m_t.group(1))
            continue
        m_s = re.search(r"lavfi\.scene_score=([\d.]+)", line)
        if m_s and pending_time is not None:
            marks.append((pending_time, float(m_s.group(1))))
            pending_time = None

    if not marks:
        return []

    # 去重 + 过滤越界/边界切点
    seen, boundaries = set(), []
    for t, score in sorted(marks, key=lambda x: x[0]):
        key = round(t, 3)
        if key in seen or t <= 0.01 or t >= duration - 0.01:
            continue
        seen.add(key)
        boundaries.append((t, score))

    if not boundaries:
        return []

    edges = [0.0] + [t for t, _ in boundaries] + [duration]
    shots = []
    for i in range(len(edges) - 1):
        score = 0.0 if i == 0 else boundaries[i - 1][1]
        shots.append({"start": edges[i], "end": edges[i + 1], "score": score})
    return shots


def _uniform_shots(duration: float, target_seconds: float = 10.0) -> List[Dict[str, float]]:
    """等间隔兜底切片（无场景变化时至少给出可用粒度）。"""
    import math
    n = max(1, min(settings.video_max_shots, math.ceil(duration / target_seconds)))
    step = duration / n
    return [{"start": round(i * step, 3),
             "end": round(duration if i == n - 1 else (i + 1) * step, 3),
             "score": 0.0} for i in range(n)]


def _postprocess_shots(shots: List[Dict[str, float]], duration: float) -> List[Dict[str, float]]:
    """后处理：去重 → 合并过短镜头 → 按场景分数限幅 → 重新编号。"""
    min_dur = max(0.1, settings.video_min_shot_seconds)
    max_shots = max(1, settings.video_max_shots)

    cleaned: List[Dict[str, float]] = []
    for s in shots:
        start, end = float(s.get("start", 0.0)), float(s.get("end", 0.0))
        if end <= start:
            continue
        cleaned.append({"start": start, "end": end, "score": float(s.get("score", 0.0))})
    cleaned.sort(key=lambda x: x["start"])

    if not cleaned:
        return [{"start": 0.0, "end": duration, "score": 0.0}]

    # 1. 合并过短镜头到前一个（首尾镜头单独处理，避免把片头/片尾吞掉）
    merged: List[Dict[str, float]] = [cleaned[0]]
    for s in cleaned[1:]:
        if s["end"] - s["start"] < min_dur and merged:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    # 首段过短则并入第二段
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < min_dur:
        merged[1]["start"] = merged[0]["start"]
        merged.pop(0)

    # 2. 超过上限：按场景分数保留最显著的边界（首镜头必留）
    if len(merged) > max_shots:
        scored = sorted(range(1, len(merged)),
                        key=lambda i: merged[i]["score"], reverse=True)[:max_shots - 1]
        keep = sorted([0] + scored)
        merged = [merged[i] for i in keep]
        # 保留边界后重新闭合区间，消除空隙
        for i in range(len(merged) - 1):
            merged[i + 1]["start"] = merged[i]["end"]
        merged[-1]["end"] = max(merged[-1]["end"], duration)

    merged[0]["start"] = 0.0
    merged[-1]["end"] = round(max(merged[-1]["end"], duration), 3)
    return merged


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
    logger.info(f"Video asset {asset_id}: {len(shots)} shots detected "
                f"(duration={video_meta.get('duration')}s, "
                f"threshold={settings.video_shot_threshold}, "
                f"min={settings.video_min_shot_seconds}s, max={settings.video_max_shots})")

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
            duration=shot["end"] - shot["start"],
            shot_metadata={"scene_score": round(shot.get("score", 0.0), 4)})

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
        "shot_ranges": [[round(s["start"], 2), round(s["end"], 2)] for s in shots],
    }


async def _has_ffmpeg() -> bool:
    code, _, _ = await _run(["ffmpeg", "-version"], timeout=10)
    return code == 0
