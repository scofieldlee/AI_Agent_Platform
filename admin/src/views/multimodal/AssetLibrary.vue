<template>
  <div>
    <!-- 顶部操作栏 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
      <div>
        <h2 style="margin: 0;">素材库</h2>
        <span style="opacity: 0.65; font-size: 13px;">共 {{ total }} 个素材</span>
      </div>
      <a-space>
        <a-button @click="loadAssets">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button @click="showTrash = !showTrash" :type="showTrash ? 'primary' : 'default'">
          <DeleteOutlined /> {{ showTrash ? '返回素材库' : '回收站' }}
        </a-button>
        <a-button type="primary" :disabled="!kbId" @click="router.push(`/multimodal/upload?kb=${kbId}`)">
          <CloudUploadOutlined /> 上传素材
        </a-button>
      </a-space>
    </div>

    <!-- 筛选栏 -->
    <a-card size="small" style="margin-bottom: 16px;">
      <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
        <a-select v-model:value="kbId" style="min-width: 220px;" placeholder="选择知识库"
          :options="kbOptions" @change="onFilterChange" />
        <a-select v-model:value="filters.file_type" style="width: 120px;" allowClear
          placeholder="类型" :options="typeOptions" @change="onFilterChange" />
        <a-select v-if="!showTrash" v-model:value="filters.status" style="width: 130px;" allowClear
          placeholder="状态" :options="statusOptions" @change="onFilterChange" />
        <a-input-search v-model:value="filters.keyword" style="width: 240px;" allowClear
          placeholder="名称 / 编码搜索" @search="onFilterChange" />
        <a-button v-if="selectedIds.length" type="primary" ghost @click="batchAnalyze" :loading="batchLoading">
          <ThunderboltOutlined /> 批量分析 ({{ selectedIds.length }})
        </a-button>
        <a-button v-if="selectedIds.length" type="primary" @click="batchApprove" :loading="batchApproveLoading">
          <CheckOutlined /> 审核通过 ({{ selectedIds.length }})
        </a-button>
      </div>
    </a-card>

    <!-- 素材网格 -->
    <a-spin :spinning="loading">
      <div v-if="assets.length" class="asset-grid">
        <div v-for="asset in assets" :key="asset.id" class="asset-card"
          :class="{ selected: selectedIds.includes(asset.id) }">
          <!-- 选择框 -->
          <div class="select-box" @click.stop="toggleSelect(asset.id)">
            <a-checkbox :checked="selectedIds.includes(asset.id)" v-if="!showTrash" />
            <DeleteOutlined v-else style="color: #ff4d4f;" />
          </div>

          <!-- 缩略图区 -->
          <div class="thumb" @click="openDetail(asset)">
            <img v-if="thumbUrl(asset)" :src="thumbUrl(asset)!" loading="lazy" alt="" />
            <div v-else class="thumb-placeholder">
              <span style="font-size: 36px;">{{ typeInfo(asset).icon }}</span>
            </div>
            <a-tag class="type-tag" :color="typeInfo(asset).color">{{ typeInfo(asset).label }}</a-tag>
          </div>

          <!-- 信息区 -->
          <div class="info">
            <div class="name" :title="asset.name" @click="openDetail(asset)">{{ asset.name }}</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
              <a-tag :color="statusInfo(asset.status).color" size="small">
                {{ statusInfo(asset.status).label }}
              </a-tag>
              <span class="meta">{{ formatSize(asset.file_size) }}</span>
            </div>
            <div v-if="asset.tags?.length" class="tags">
              <a-tag v-for="t in asset.tags.slice(0, 3)" :key="t.id" size="small"
                :color="t.source === 'ai' ? 'purple' : 'blue'">{{ t.name }}</a-tag>
              <span v-if="asset.tags.length > 3" class="meta">+{{ asset.tags.length - 3 }}</span>
            </div>
          </div>

          <!-- 操作 -->
          <div class="actions">
            <template v-if="!showTrash">
              <a-tooltip title="AI 分析"><a-button size="small" type="text" @click.stop="analyze(asset)"><ThunderboltOutlined /></a-button></a-tooltip>
              <a-tooltip title="向量化索引"><a-button size="small" type="text" @click.stop="indexAsset(asset)"><DatabaseOutlined /></a-button></a-tooltip>
              <a-tooltip title="下载"><a-button size="small" type="text" @click.stop="download(asset)"><DownloadOutlined /></a-button></a-tooltip>
              <a-tooltip title="移入回收站">
                <a-popconfirm title="移入回收站？" @confirm="softDelete(asset)">
                  <a-button size="small" type="text" danger @click.stop><DeleteOutlined /></a-button>
                </a-popconfirm>
              </a-tooltip>
            </template>
            <template v-else>
              <a-button size="small" type="link" @click.stop="restore(asset)">恢复</a-button>
              <a-popconfirm title="永久删除（不可恢复）？" okType="danger" @confirm="permanentDelete(asset)">
                <a-button size="small" type="link" danger @click.stop>彻底删除</a-button>
              </a-popconfirm>
            </template>
          </div>
        </div>
      </div>

      <a-empty v-else-if="!loading" :description="showTrash ? '回收站为空' : '暂无素材，点击右上角上传'" style="padding: 60px 0;">
        <a-button v-if="!showTrash" type="primary" :disabled="!kbId"
          @click="router.push(`/multimodal/upload?kb=${kbId}`)">
          <CloudUploadOutlined /> 上传素材
        </a-button>
      </a-empty>
    </a-spin>

    <!-- 分页 -->
    <div style="display: flex; justify-content: flex-end; margin-top: 16px;" v-if="total > pageSize">
      <a-pagination v-model:current="page" :total="total" :pageSize="pageSize"
        show-size-changer :pageSizeOptions="['20', '40', '60', '100']"
        @change="loadAssets" @showSizeChange="onPageSizeChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ReloadOutlined, CloudUploadOutlined, ThunderboltOutlined, DatabaseOutlined,
  DownloadOutlined, DeleteOutlined, CheckOutlined
} from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import { formatSize, fileThumbUrl, ASSET_STATUS, FILE_TYPE, statusTag } from './types'
import type { MmAsset } from './types'

const route = useRoute()
const router = useRouter()

const kbs = ref<Array<{ id: number; name: string; asset_count: number }>>([])
const kbOptions = computed(() => kbs.value.map(k => ({ label: `${k.name}（${k.asset_count}）`, value: k.id })))

const kbId = ref<number | undefined>(undefined)
const showTrash = ref(false)
const filters = ref<{ file_type?: string; status?: string; keyword?: string }>({})
const page = ref(1)
const pageSize = ref(40)
const loading = ref(false)
const assets = ref<MmAsset[]>([])
const total = ref(0)
const selectedIds = ref<number[]>([])
const batchLoading = ref(false)

const typeOptions = Object.entries(FILE_TYPE).map(([value, t]) => ({ label: `${t.icon} ${t.label}`, value }))
const statusOptions = Object.entries(ASSET_STATUS).map(([value, s]) => ({ label: s.label, value }))

function thumbUrl(asset: MmAsset) { return fileThumbUrl(asset) }
function typeInfo(asset: MmAsset) { return FILE_TYPE[asset.file_type] || FILE_TYPE.file }
function statusInfo(status: string) { return statusTag(status) }

async function loadAssets() {
  if (!kbId.value) return
  loading.value = true
  try {
    const params: any = {
      knowledge_base_id: kbId.value,
      page: page.value,
      page_size: pageSize.value
    }
    if (showTrash.value) {
      params.include_deleted = true
    } else {
      if (filters.value.file_type) params.file_type = filters.value.file_type
      if (filters.value.status) params.status = filters.value.status
      if (filters.value.keyword?.trim()) params.keyword = filters.value.keyword.trim()
    }
    const res = await (showTrash.value
      ? multimodalApi.listTrash({ knowledge_base_id: kbId.value, page: page.value, page_size: pageSize.value })
      : multimodalApi.listAssets(params))
    assets.value = res.data.items || []
    total.value = res.data.total || 0
    selectedIds.value = []
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  loadAssets()
}

function onPageSizeChange(_p: number, size: number) {
  pageSize.value = size
  page.value = 1
  loadAssets()
}

function toggleSelect(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter(i => i !== id)
    : [...selectedIds.value, id]
}

function openDetail(asset: MmAsset) {
  router.push(`/multimodal/assets/${asset.id}`)
}

async function analyze(asset: MmAsset) {
  try {
    await multimodalApi.analyze(asset.id)
    message.success('分析任务已提交')
    await loadAssets()
  } catch { /* interceptor 已提示 */ }
}

async function indexAsset(asset: MmAsset) {
  try {
    await multimodalApi.index(asset.id)
    message.success('索引任务已提交')
    await loadAssets()
  } catch { /* interceptor 已提示 */ }
}

async function batchAnalyze() {
  batchLoading.value = true
  try {
    const res = await multimodalApi.batchAnalyze(selectedIds.value)
    message.success(`已提交 ${res.data.total} 个分析任务`)
    selectedIds.value = []
    await loadAssets()
  } catch {
    /* interceptor 已提示 */
  } finally {
    batchLoading.value = false
  }
}

const batchApproveLoading = ref(false)

async function batchApprove() {
  batchApproveLoading.value = true
  try {
    const res = await multimodalApi.batchApprove(selectedIds.value)
    const { approved = 0, skipped = 0, errors = 0 } = res.data || {}
    if (approved > 0) {
      message.success(`已审核通过 ${approved} 个素材，索引任务已提交`)
    }
    if (skipped > 0) {
      message.warning(`${skipped} 个素材非"待审核"状态，已跳过`)
    }
    if (errors > 0) {
      message.error(`${errors} 个素材处理失败`)
    }
    selectedIds.value = []
    await loadAssets()
  } catch {
    /* interceptor 已提示 */
  } finally {
    batchApproveLoading.value = false
  }
}

function download(asset: MmAsset) {
  window.open(multimodalApi.downloadUrl(asset.id), '_blank')
}

async function softDelete(asset: MmAsset) {
  try {
    await multimodalApi.deleteAsset(asset.id)
    message.success('已移入回收站')
    await loadAssets()
  } catch { /* interceptor 已提示 */ }
}

async function restore(asset: MmAsset) {
  try {
    await multimodalApi.restoreAsset(asset.id)
    message.success('已恢复')
    await loadAssets()
  } catch { /* interceptor 已提示 */ }
}

async function permanentDelete(asset: MmAsset) {
  try {
    await multimodalApi.permanentDeleteAsset(asset.id)
    message.success('已彻底删除')
    await loadAssets()
  } catch { /* interceptor 已提示 */ }
}

watch(showTrash, () => {
  page.value = 1
  loadAssets()
})

watch(kbId, () => {
  if (kbId.value) {
    page.value = 1
    loadAssets()
  }
})

onMounted(async () => {
  const kbParam = Number(route.query.kb)
  try {
    const res = await multimodalApi.listKbs()
    kbs.value = res.data
    kbId.value = kbParam || (res.data[0]?.id)
  } catch { /* interceptor 已提示 */ }
})
</script>

<style scoped>
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.asset-card {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  background: var(--ant-card-bg, #fff);
  border: 1px solid rgba(128, 128, 128, 0.18);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.asset-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
.asset-card.selected {
  border-color: #4f46e5;
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.25);
}
.select-box {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 5;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  padding: 2px 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}
.asset-card:hover .select-box,
.asset-card.selected .select-box {
  opacity: 1;
}
.thumb {
  position: relative;
  height: 140px;
  background: rgba(128, 128, 128, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}
.asset-card:hover .thumb img {
  transform: scale(1.05);
}
.thumb-placeholder {
  opacity: 0.45;
}
.type-tag {
  position: absolute;
  bottom: 8px;
  left: 8px;
  margin: 0;
  backdrop-filter: blur(4px);
}
.info {
  padding: 10px 12px 6px;
}
.name {
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.meta {
  font-size: 12px;
  opacity: 0.55;
}
.tags {
  margin-top: 6px;
  overflow: hidden;
  white-space: nowrap;
  height: 22px;
}
.actions {
  display: flex;
  justify-content: space-around;
  border-top: 1px solid rgba(128, 128, 128, 0.12);
  padding: 2px 0;
}
</style>
