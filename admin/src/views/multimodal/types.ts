/** 多模态知识库 — 前端共享类型与工具 */

export interface MmKnowledgeBase {
  id: number
  name: string
  code: string
  description?: string | null
  kb_type: string
  status: string
  asset_count: number
  created_by?: number | null
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
  type_stats?: Record<string, number>
  status_stats?: Record<string, number>
}

export interface MmTag {
  id: number
  name: string
  source: string
}

export interface MmAsset {
  id: number
  knowledge_base_id: number
  asset_code: string
  name: string
  original_filename?: string | null
  file_type: string
  mime_type?: string | null
  file_size: number
  storage_path?: string | null
  thumbnail_path?: string | null
  preview_path?: string | null
  status: string
  version: number
  attributes?: Record<string, any> | null
  tags: MmTag[]
  created_at?: string | null
  updated_at?: string | null
  deleted_at?: string | null
}

export interface MmAssetDetail extends MmAsset {
  metadata: Record<string, Record<string, any>>
  units_count: number
  units: Array<{
    id: number
    unit_type: string
    unit_index: number
    content?: string | null
    description?: string | null
    start_time?: number | null
    end_time?: number | null
    thumbnail_url?: string | null
  }>
  relations: Array<{
    id: number
    direction?: string
    relation_type: string
    source_asset_id?: number
    target_asset_id?: number
    other_asset_id?: number
    other_asset_name?: string | null
    other_asset_code?: string | null
    other_file_type?: string | null
    [key: string]: any
  }>
  processing_summary: Record<string, number>
  ai_tags: string[]
}

export interface MmProcessingTask {
  id: number
  task_type: string
  status: string
  model?: string | null
  error?: string | null
  retry_count?: number
  started_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  asset_id?: number | null
  [key: string]: any
}

export interface MmSearchResult {
  asset_id: number
  asset_code?: string | null
  asset_name?: string | null
  asset_type?: string | null
  unit_id?: number | null
  unit_type?: string | null
  unit_index?: number | null
  score: number
  description?: string | null
  content?: string | null
  start_time?: number | null
  end_time?: number | null
  thumbnail_url?: string | null
  preview_url?: string | null
  tags: string[]
}

// ---------- 状态映射 ----------

export const ASSET_STATUS: Record<string, { label: string; color: string }> = {
  uploaded: { label: '已上传', color: 'default' },
  processing: { label: '处理中', color: 'processing' },
  analyzing: { label: 'AI 分析中', color: 'processing' },
  review_required: { label: '待审核', color: 'warning' },
  indexing: { label: '索引中', color: 'processing' },
  ready: { label: '就绪', color: 'success' },
  failed: { label: '失败', color: 'error' },
  deleted: { label: '回收站', color: 'default' }
}

export const TASK_STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: '排队中', color: 'default' },
  processing: { label: '处理中', color: 'processing' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' }
}

export const FILE_TYPE: Record<string, { label: string; icon: string; color: string }> = {
  image: { label: '图片', icon: '🖼️', color: 'blue' },
  video: { label: '视频', icon: '🎬', color: 'purple' },
  audio: { label: '音频', icon: '🎵', color: 'cyan' },
  ppt: { label: 'PPT', icon: '📊', color: 'orange' },
  pdf: { label: 'PDF', icon: '📄', color: 'red' },
  doc: { label: '文档', icon: '📝', color: 'green' },
  file: { label: '文件', icon: '📦', color: 'default' }
}

export const UNIT_TYPE: Record<string, string> = {
  image: '整图',
  shot: '视频镜头',
  segment: '音频分段',
  slide: 'PPT 页'
}

export const RELATION_TYPE: Record<string, string> = {
  related: '相关',
  derived_from: '衍生自',
  variant_of: '变体',
  part_of: '组成部分',
  used_with: '配套使用'
}

// ---------- 工具函数 ----------

export function formatSize(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatTime(seconds?: number | null): string {
  if (seconds == null) return '-'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function fileThumbUrl(asset: MmAsset): string | null {
  return asset.thumbnail_path ? `/api/v1/multimodal/files/${asset.thumbnail_path}` : null
}

export function filePreviewUrl(asset: MmAsset): string | null {
  if (asset.file_type === 'image' && asset.storage_path) {
    return `/api/v1/multimodal/files/${asset.storage_path}`
  }
  if (asset.preview_path) return `/api/v1/multimodal/files/${asset.preview_path}`
  return null
}

export function statusTag(status: string) {
  return ASSET_STATUS[status] || { label: status, color: 'default' }
}
