"""多模态知识库 API 端点 — /api/v1/multimodal/*

覆盖: 知识库 CRUD / 素材上传管理 / AI 处理触发 / 人工审核 / 多模态检索 / 素材关联 / 文件服务
权限: multimodal:view（查看/检索） / multimodal:manage（上传/编辑/分析/删除）
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission, get_current_user
from app.database.session import get_db
from app.multimodal.schemas import (
    MultimodalKBCreate, MultimodalKBUpdate, MultimodalKBResponse,
    MultimodalKBDetailResponse, KBStatsResponse,
    AssetListParams, AssetListResponse, AssetDetailResponse, AssetUpdate,
    AssetUserMetadataUpdate, TagAddRequest, UploadResponse,
    RelationCreate, ApproveRequest, BatchAnalyzeRequest,
    ProcessingTaskListResponse, SearchRequest, SearchResponse,
)
from app.multimodal.repositories import (
    knowledge_base_repo, asset_repo, processing_repo,
)
from app.multimodal.services import (
    asset_service, review_service, search_service, storage_service,
    task_queue_service,
)
from app.multimodal.constants import RelationType

logger = logging.getLogger(__name__)

router = APIRouter()

ViewPerm = Depends(require_permission("multimodal:view"))
ManagePerm = Depends(require_permission("multimodal:manage"))


# ============================================================
# 知识库管理
# ============================================================

@router.post("/knowledge-bases", response_model=MultimodalKBResponse,
             status_code=201, dependencies=[ManagePerm])
async def create_kb(data: MultimodalKBCreate,
                    db: AsyncSession = Depends(get_db),
                    current_user=Depends(get_current_user)):
    """创建多模态知识库。"""
    code = data.code
    if not code:
        code = await knowledge_base_repo.generate_kb_code(db, data.name)
    elif await knowledge_base_repo.get_kb_by_code(db, code):
        raise HTTPException(409, f"知识库编码已存在: {code}")

    kb = await knowledge_base_repo.create_kb(
        db, name=data.name, code=code, description=data.description,
        storage_config=data.storage_config, embedding_config=data.embedding_config,
        vision_model_config=data.vision_model_config,
        analysis_config=data.analysis_config, created_by=current_user.id)
    await db.commit()
    await db.refresh(kb)
    return kb


@router.get("/knowledge-bases", response_model=List[MultimodalKBResponse],
            dependencies=[ViewPerm])
async def list_kbs(include_archived: bool = False,
                   db: AsyncSession = Depends(get_db)):
    """多模态知识库列表。"""
    return await knowledge_base_repo.list_kbs(db, include_archived)


@router.get("/knowledge-bases/{kb_id}", response_model=MultimodalKBDetailResponse,
            dependencies=[ViewPerm])
async def get_kb_detail(kb_id: int, db: AsyncSession = Depends(get_db)):
    """知识库详情（含统计）。"""
    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    stats = await knowledge_base_repo.get_kb_stats(db, kb_id)
    detail = {c.name: getattr(kb, c.name) for c in kb.__table__.columns}
    detail["type_stats"] = stats["type_stats"]
    detail["status_stats"] = stats["status_stats"]
    return detail


@router.get("/knowledge-bases/{kb_id}/stats", response_model=KBStatsResponse,
            dependencies=[ViewPerm])
async def get_kb_stats(kb_id: int, db: AsyncSession = Depends(get_db)):
    """知识库统计。"""
    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return await knowledge_base_repo.get_kb_stats(db, kb_id)


@router.put("/knowledge-bases/{kb_id}", response_model=MultimodalKBResponse,
            dependencies=[ManagePerm])
async def update_kb(kb_id: int, data: MultimodalKBUpdate,
                    db: AsyncSession = Depends(get_db)):
    """更新知识库配置。"""
    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    kb = await knowledge_base_repo.update_kb(db, kb, data.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(kb)
    return kb


@router.delete("/knowledge-bases/{kb_id}", dependencies=[ManagePerm])
async def delete_kb(kb_id: int, db: AsyncSession = Depends(get_db)):
    """删除知识库（需无素材，含回收站）。"""
    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    count = await asset_repo.count_assets_in_kb(db, kb_id, include_trash=True)
    if count > 0:
        raise HTTPException(409, f"知识库仍有 {count} 个素材（含回收站），请先清空")
    await knowledge_base_repo.delete_kb(db, kb)
    await db.commit()
    return {"status": "deleted", "kb_id": kb_id}


# ============================================================
# 素材上传与管理
# ============================================================

@router.post("/assets/upload", response_model=UploadResponse, dependencies=[ManagePerm])
async def upload_assets(knowledge_base_id: int = Query(...),
                        files: List[UploadFile] = File(...),
                        db: AsyncSession = Depends(get_db),
                        current_user=Depends(get_current_user)):
    """批量上传素材（multipart）。上传后自动入队 AI 分析。"""
    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")

    items = []
    for f in files:
        data = await f.read()
        result = await asset_service.upload_asset(
            db, kb_id, f.filename or "unnamed", data, current_user.id)
        items.append(result)
    await db.commit()

    return UploadResponse(
        total=len(items),
        success_count=sum(1 for i in items if i["success"]),
        failed_count=sum(1 for i in items if not i["success"]),
        items=items)


@router.get("/assets", response_model=AssetListResponse, dependencies=[ViewPerm])
async def list_assets(knowledge_base_id: int = Query(...),
                      file_type: Optional[str] = None,
                      status: Optional[str] = None,
                      tag: Optional[str] = None,
                      keyword: Optional[str] = None,
                      include_deleted: bool = False,
                      page: int = Query(1, ge=1),
                      page_size: int = Query(20, ge=1, le=100),
                      db: AsyncSession = Depends(get_db)):
    """素材列表（分页 + 类型/状态/标签/关键词过滤）。include_deleted=true 查回收站。"""
    params = AssetListParams(knowledge_base_id=knowledge_base_id, file_type=file_type,
                             status=status, tag=tag, keyword=keyword,
                             include_deleted=include_deleted,
                             page=page, page_size=page_size)
    return await asset_service.list_assets(db, params)


@router.get("/trash", response_model=AssetListResponse, dependencies=[ViewPerm])
async def list_trash(knowledge_base_id: int = Query(...),
                     page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100),
                     db: AsyncSession = Depends(get_db)):
    """回收站列表。"""
    params = AssetListParams(knowledge_base_id=knowledge_base_id,
                             include_deleted=True, page=page, page_size=page_size)
    return await asset_service.list_assets(db, params)


@router.get("/assets/{asset_id}", response_model=AssetDetailResponse,
            dependencies=[ViewPerm])
async def get_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    """素材详情。"""
    detail = await asset_service.get_asset_detail(db, asset_id)
    if not detail:
        raise HTTPException(404, "素材不存在")
    return detail


@router.put("/assets/{asset_id}", response_model=AssetDetailResponse,
            dependencies=[ManagePerm])
async def update_asset(asset_id: int, data: AssetUpdate,
                       db: AsyncSession = Depends(get_db)):
    """编辑素材（名称 / attributes）。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    updates = data.model_dump(exclude_unset=True)
    if updates:
        asset = await asset_repo.update_asset(db, asset, updates)
    await db.commit()
    detail = await asset_service.get_asset_detail(db, asset_id)
    return detail


@router.delete("/assets/{asset_id}", dependencies=[ManagePerm])
async def soft_delete_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    """软删除素材 → 回收站。"""
    asset = await asset_service.soft_delete_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在或已在回收站")
    await db.commit()
    return {"status": "deleted", "asset_id": asset_id}


@router.post("/assets/{asset_id}/restore", dependencies=[ManagePerm])
async def restore_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    """从回收站恢复。"""
    asset = await asset_service.restore_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在或不在回收站")
    await db.commit()
    return {"status": "restored", "asset_id": asset_id, "asset_status": asset.status}


@router.delete("/assets/{asset_id}/permanent", dependencies=[ManagePerm])
async def permanent_delete_asset(asset_id: int, db: AsyncSession = Depends(get_db)):
    """永久删除（DB 记录 + 向量索引 + 文件目录）。"""
    result = await asset_service.permanent_delete_asset(db, asset_id)
    if not result:
        raise HTTPException(404, "素材不存在")
    await db.commit()
    return {"status": "permanently_deleted", **result}


# ============================================================
# 文件服务（预览/缩略图/原始文件）
# ============================================================

@router.get("/files/{file_path:path}")
async def serve_file(file_path: str):
    """静态文件服务: 缩略图/预览/原始文件。
    注意: V1.0 内部部署暂不加密（URL 直接可访问），公网部署需加签名机制。
    """
    try:
        abs_path = storage_service.abs_file_path(file_path)
    except ValueError:
        raise HTTPException(400, "非法路径")

    import os
    if not os.path.isfile(abs_path):
        raise HTTPException(404, "文件不存在")

    media_type = storage_service.guess_mime(abs_path)
    # 图片/视频直接内联展示
    return FileResponse(abs_path, media_type=media_type)


@router.get("/assets/{asset_id}/download")
async def download_asset(asset_id: int, db: AsyncSession = Depends(get_db),
                         _perm=ViewPerm):
    """下载原始文件。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset or not asset.storage_path:
        raise HTTPException(404, "素材不存在")
    abs_path = storage_service.abs_file_path(asset.storage_path)
    import os
    if not os.path.isfile(abs_path):
        raise HTTPException(404, "文件不存在")
    filename = asset.original_filename or f"{asset.asset_code}"
    return FileResponse(abs_path, media_type=asset.mime_type or "application/octet-stream",
                        filename=filename)


# ============================================================
# AI 处理触发
# ============================================================

@router.post("/assets/{asset_id}/analyze", dependencies=[ManagePerm])
async def trigger_analysis(asset_id: int, db: AsyncSession = Depends(get_db)):
    """触发/重新触发 AI 分析（异步任务）。"""
    result = await asset_service.trigger_analysis(db, asset_id)
    if result is None:
        raise HTTPException(404, "素材不存在")
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(409, result["error"])
    await db.commit()
    return {"task_id": result.id, "asset_id": asset_id,
            "task_type": "analysis", "status": "queued",
            "message": "分析任务已提交"}


@router.post("/assets/{asset_id}/index", dependencies=[ManagePerm])
async def trigger_index(asset_id: int, db: AsyncSession = Depends(get_db)):
    """触发/重新触发向量化索引（异步任务）。"""
    result = await asset_service.trigger_index(db, asset_id)
    if result is None:
        raise HTTPException(404, "素材不存在")
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(409, result["error"])
    await db.commit()
    return {"task_id": result.id, "asset_id": asset_id,
            "task_type": "index", "status": "queued",
            "message": "索引任务已提交"}


@router.post("/assets/batch-analyze", dependencies=[ManagePerm])
async def batch_analyze(data: BatchAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """批量触发 AI 分析。"""
    results = await asset_service.batch_analyze(db, data.asset_ids)
    await db.commit()
    return {"results": results, "total": len(results)}


@router.get("/assets/{asset_id}/units", dependencies=[ViewPerm])
async def list_units(asset_id: int, db: AsyncSession = Depends(get_db)):
    """素材知识单元列表。"""
    from app.multimodal.repositories import knowledge_unit_repo
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    units = await knowledge_unit_repo.list_units_by_asset(db, asset_id)
    items = []
    for u in units:
        items.append({
            "id": u.id, "asset_id": u.asset_id, "knowledge_base_id": u.knowledge_base_id,
            "unit_type": u.unit_type, "unit_index": u.unit_index,
            "content": u.content, "description": u.description, "metadata": u.meta,
            "start_time": u.start_time, "end_time": u.end_time,
            "thumbnail_url": storage_service.file_url(u.thumbnail_path),
            "frame_index": u.frame_index, "status": u.status,
        })
    return {"total": len(items), "items": items}


@router.get("/assets/{asset_id}/processing", response_model=ProcessingTaskListResponse,
            dependencies=[ViewPerm])
async def list_processing(asset_id: int, page: int = Query(1, ge=1),
                          page_size: int = Query(20, ge=1, le=100),
                          db: AsyncSession = Depends(get_db)):
    """素材处理任务记录。"""
    total, tasks = await processing_repo.list_tasks(
        db, asset_id=asset_id, page=page, page_size=page_size)
    return {"total": total, "items": tasks}


@router.get("/tasks", response_model=ProcessingTaskListResponse,
            dependencies=[ViewPerm])
async def list_tasks(kb_id: Optional[int] = None,
                     asset_id: Optional[int] = None,
                     task_type: Optional[str] = None,
                     status: Optional[str] = None,
                     page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100),
                     db: AsyncSession = Depends(get_db)):
    """全部处理任务监控（含队列深度）。"""
    total, tasks = await processing_repo.list_tasks(
        db, asset_id=asset_id, kb_id=kb_id, task_type=task_type,
        status=status, page=page, page_size=page_size)
    return {"total": total, "items": tasks}


# ============================================================
# 人工审核
# ============================================================

@router.post("/assets/{asset_id}/approve", dependencies=[ManagePerm])
async def approve_asset(asset_id: int, data: ApproveRequest,
                        db: AsyncSession = Depends(get_db),
                        current_user=Depends(get_current_user)):
    """审核通过 → 自动入队向量化索引。"""
    result = await review_service.approve_asset(
        db, asset_id, data.user_metadata, current_user.id)
    if result is None:
        raise HTTPException(404, "素材不存在")
    if "error" in result:
        raise HTTPException(409, result["error"])
    await db.commit()
    return {"status": "approved", **result}


@router.put("/assets/{asset_id}/metadata", dependencies=[ManagePerm])
async def update_user_metadata(asset_id: int, data: AssetUserMetadataUpdate,
                               db: AsyncSession = Depends(get_db)):
    """更新用户 metadata（category/usage/copyright/remark）。"""
    result = await review_service.update_user_metadata(db, asset_id, data.metadata)
    if result is None:
        raise HTTPException(404, "素材不存在")
    await db.commit()
    return {"asset_id": asset_id, "metadata": result}


@router.post("/assets/{asset_id}/tags", dependencies=[ManagePerm])
async def add_tags(asset_id: int, data: TagAddRequest,
                   db: AsyncSession = Depends(get_db),
                   current_user=Depends(get_current_user)):
    """添加标签。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    tags = await asset_service.add_tags(
        db, asset_id, data.tags, data.source, current_user.id)
    await db.commit()
    return {"asset_id": asset_id, "tags": tags}


@router.delete("/assets/{asset_id}/tags/{tag_id}", dependencies=[ManagePerm])
async def remove_tag(asset_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    """删除素材标签。"""
    ok = await asset_service.remove_tag(db, asset_id, tag_id)
    if not ok:
        raise HTTPException(404, "标签不存在或未挂载")
    await db.commit()
    return {"status": "removed", "tag_id": tag_id}


@router.get("/tags", dependencies=[ViewPerm])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """标签字典（含使用计数）。"""
    return {"items": await asset_repo.list_all_tags(db)}


# ============================================================
# 多模态检索
# ============================================================

@router.post("/search", response_model=SearchResponse, dependencies=[ViewPerm])
async def multimodal_search(data: SearchRequest,
                            query_image: Optional[UploadFile] = File(None),
                            db: AsyncSession = Depends(get_db)):
    """多模态检索: 文本 / 图片（以图搜图）/ 文本+图片 融合。"""
    image_bytes, image_ext = None, "jpg"
    if query_image is not None:
        image_bytes = await query_image.read()
        ext = (query_image.filename or "img.jpg").rsplit(".", 1)[-1].lower()
        image_ext = ext if ext in ("jpg", "jpeg", "png", "webp", "bmp") else "jpg"

    result = await search_service.search(
        db, knowledge_base_id=data.knowledge_base_id, query=data.query,
        query_image_data=image_bytes, query_image_ext=image_ext,
        asset_types=data.asset_types or None, top_k=data.top_k,
        min_score=data.min_score)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/assets/{asset_id}/similar", dependencies=[ViewPerm])
async def similar_assets(asset_id: int, top_k: int = Query(10, ge=1, le=50),
                         db: AsyncSession = Depends(get_db)):
    """以图搜图：基于指定素材找相似素材。"""
    result = await search_service.search_by_asset(db, asset_id, top_k)
    return result


# ============================================================
# 素材关联
# ============================================================

@router.post("/assets/{asset_id}/relations", dependencies=[ManagePerm])
async def create_relation(asset_id: int, data: RelationCreate,
                          db: AsyncSession = Depends(get_db),
                          current_user=Depends(get_current_user)):
    """建立素材关联。"""
    if data.relation_type not in RelationType.ALL:
        raise HTTPException(400, f"relation_type 必须是 {RelationType.ALL} 之一")
    source = await asset_repo.get_asset(db, asset_id)
    target = await asset_repo.get_asset(db, data.target_asset_id)
    if not source:
        raise HTTPException(404, "源素材不存在")
    if not target:
        raise HTTPException(404, "目标素材不存在")
    if source.knowledge_base_id != target.knowledge_base_id:
        raise HTTPException(400, "不支持跨知识库关联")
    if source.id == target.id:
        raise HTTPException(400, "不能与自身建立关联")

    rel = await asset_repo.create_relation(
        db, asset_id, data.target_asset_id, data.relation_type,
        data.metadata, current_user.id)
    await db.commit()
    return {"relation_id": rel.id, "source_asset_id": asset_id,
            "target_asset_id": data.target_asset_id,
            "relation_type": data.relation_type}


@router.get("/assets/{asset_id}/relations", dependencies=[ViewPerm])
async def list_relations(asset_id: int, db: AsyncSession = Depends(get_db)):
    """素材关联列表（双向）。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    return {"items": await asset_repo.list_relations(db, asset_id)}


@router.delete("/relations/{relation_id}", dependencies=[ManagePerm])
async def delete_relation(relation_id: int, db: AsyncSession = Depends(get_db)):
    """删除素材关联。"""
    ok = await asset_repo.delete_relation(db, relation_id)
    if not ok:
        raise HTTPException(404, "关联不存在")
    await db.commit()
    return {"status": "deleted", "relation_id": relation_id}


# ============================================================
# 队列状态
# ============================================================

@router.get("/queue/status", dependencies=[ViewPerm])
async def queue_status():
    """任务队列状态。"""
    depth = await task_queue_service.get_queue_depth()
    return {"queue_depth": depth, "queue_key": "mm:task:queue"}
