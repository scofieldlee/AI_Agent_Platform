<template>
  <div v-if="asset">
    <!-- 顶部 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <a-button @click="router.back()"><ArrowLeftOutlined /></a-button>
        <div>
          <h2 style="margin: 0; display: flex; align-items: center; gap: 8px;">
            {{ asset.name }}
            <a-tag :color="typeInfo.color">{{ typeInfo.icon }} {{ typeInfo.label }}</a-tag>
            <a-tag :color="statusInfo.color">{{ statusInfo.label }}</a-tag>
          </h2>
          <span class="sub">{{ asset.asset_code }} · {{ formatSize(asset.file_size) }} ·
            {{ asset.original_filename }} · {{ asset.created_at?.slice(0, 19).replace('T', ' ') }}</span>
        </div>
      </div>
      <a-space>
        <a-button @click="analyze" :loading="actionLoading"><ThunderboltOutlined /> AI 分析</a-button>
        <a-button @click="indexAsset"><DatabaseOutlined /> 向量索引</a-button>
        <a-button @click="findSimilar"><SearchOutlined /> 相似素材</a-button>
        <a-button type="primary" v-if="asset.status === 'review_required'" @click="approve">
          <CheckCircleOutlined /> 审核通过
        </a-button>
        <a-button @click="download"><DownloadOutlined /> 下载</a-button>
      </a-space>
    </div>

    <a-row :gutter="16">
      <!-- 左列：预览 + 知识单元 -->
      <a-col :xs="24" :lg="14">
        <!-- 预览 -->
        <a-card size="small" title="预览" style="margin-bottom: 16px;">
          <div class="preview-box">
            <img v-if="asset.file_type === 'image' && previewSrc" :src="previewSrc" alt="" />
            <video v-else-if="asset.file_type === 'video' && previewSrc" :src="previewSrc" controls />
            <audio v-else-if="asset.file_type === 'audio' && previewSrc" :src="previewSrc" controls />
            <img v-else-if="asset.preview_path" :src="`/api/v1/multimodal/files/${asset.preview_path}`" alt="" />
            <div v-else class="no-preview">{{ typeInfo.icon }} 该类型暂不支持在线预览</div>
          </div>
        </a-card>

        <!-- 知识单元 -->
        <a-card size="small" style="margin-bottom: 16px;">
          <template #title>
            知识单元
            <a-tag v-if="units.length" style="margin-left: 8px;">{{ units.length }}</a-tag>
          </template>
          <template #extra>
            <a-button size="small" @click="loadUnits" v-if="!units.length && asset.units_count">
              加载
            </a-button>
          </template>
          <a-empty v-if="!units.length" :image-style="{ height: '48px' }"
            description="暂无知识单元（需先完成 AI 分析）" />
          <div v-else class="unit-list">
            <div v-for="u in units" :key="u.id" class="unit-item">
              <img v-if="u.thumbnail_url" :src="u.thumbnail_url" class="unit-thumb" loading="lazy" />
              <div v-else class="unit-thumb unit-thumb-empty">{{ unitIcon(u.unit_type) }}</div>
              <div class="unit-body">
                <div class="unit-head">
                  <a-tag size="small" color="geekblue">{{ UNIT_TYPE[u.unit_type] || u.unit_type }}</a-tag>
                  <span v-if="u.unit_type !== 'image'" class="sub">#{{ u.unit_index + 1 }}</span>
                  <span v-if="u.start_time != null" class="sub">
                    {{ formatTime(u.start_time) }} - {{ formatTime(u.end_time) }}
                  </span>
                </div>
                <div class="unit-content">{{ u.description || u.content || '（无描述）' }}</div>
              </div>
            </div>
          </div>
        </a-card>

        <!-- 处理记录 -->
        <a-card size="small" title="处理记录">
          <a-empty v-if="!tasks.length" :image-style="{ height: '48px' }" description="暂无处理记录" />
          <a-timeline v-else style="margin-top: 8px;">
            <a-timeline-item v-for="t in tasks" :key="t.id"
              :color="TASK_STATUS[t.status]?.color === 'success' ? 'green'
                : TASK_STATUS[t.status]?.color === 'error' ? 'red'
                : TASK_STATUS[t.status]?.color === 'processing' ? 'blue' : 'gray'">
              <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <b>{{ t.task_type === 'analysis' ? 'AI 分析' : '向量索引' }}</b>
                <a-tag :color="TASK_STATUS[t.status]?.color" size="small">
                  {{ TASK_STATUS[t.status]?.label || t.status }}
                </a-tag>
                <span class="sub">{{ (t.created_at || '').slice(0, 19).replace('T', ' ') }}</span>
                <span v-if="t.retry_count" class="sub">重试 {{ t.retry_count }}</span>
              </div>
              <div v-if="t.error" class="err">{{ t.error }}</div>
            </a-timeline-item>
          </a-timeline>
        </a-card>
      </a-col>

      <!-- 右列：标签 + metadata -->
      <a-col :xs="24" :lg="10">
        <!-- AI 分析结果 -->
        <a-card size="small" title="AI 分析结果" style="margin-bottom: 16px;">
          <template #extra>
            <a-tag v-if="asset.metadata?.ai?.analyzed_at" color="purple">
              {{ (asset.metadata.ai.analyzed_at || '').slice(0, 10) }}
            </a-tag>
          </template>
          <div v-if="aiMeta">
            <div v-if="aiMeta.description" class="ai-desc">{{ aiMeta.description }}</div>
            <div v-if="aiMeta.objects?.length" style="margin-top: 10px;">
              <span class="label">识别对象：</span>
              <a-tag v-for="o in aiMeta.objects" :key="o" color="purple">{{ o }}</a-tag>
            </div>
            <div v-if="aiMeta.scene" style="margin-top: 8px;">
              <span class="label">场景：</span>{{ aiMeta.scene }}
            </div>
            <div v-if="aiMeta.ocr_text" style="margin-top: 8px;">
              <span class="label">OCR 文本：</span>
              <div class="ocr-box">{{ aiMeta.ocr_text }}</div>
            </div>
          </div>
          <a-empty v-else :image-style="{ height: '48px' }" description="尚未分析或分析中" />
          <div v-if="asset.ai_tags?.length" style="margin-top: 12px; border-top: 1px dashed rgba(128,128,128,0.2); padding-top: 10px;">
            <span class="label">AI 标签：</span>
            <a-tag v-for="t in asset.ai_tags" :key="t" color="geekblue">{{ t }}</a-tag>
          </div>
        </a-card>

        <!-- 用户标签 -->
        <a-card size="small" title="标签" style="margin-bottom: 16px;">
          <template #extra>
            <a-button size="small" @click="showTagInput = !showTagInput"><PlusOutlined /></a-button>
          </template>
          <div v-if="showTagInput" style="display: flex; gap: 8px; margin-bottom: 10px;">
            <a-input v-model:value="newTag" placeholder="输入标签，回车添加" size="small"
              @pressEnter="addTag" style="flex: 1;" />
            <a-button size="small" type="primary" @click="addTag">添加</a-button>
          </div>
          <template v-if="asset.tags?.length">
            <a-tag v-for="t in asset.tags" :key="t.id" closable
              :color="t.source === 'ai' ? 'purple' : 'blue'" @close="removeTag(t)">
              {{ t.name }}<span class="sub" style="margin-left: 4px;">{{ t.source === 'ai' ? 'AI' : '' }}</span>
            </a-tag>
          </template>
          <span v-else class="sub">暂无标签</span>
        </a-card>

        <!-- 用户 metadata -->
        <a-card size="small" title="业务信息（用户元数据）" style="margin-bottom: 16px;">
          <a-form layout="vertical" size="small">
            <a-form-item label="分类">
              <a-input v-model:value="userMeta.category" placeholder="如：产品图 / 营销素材" />
            </a-form-item>
            <a-form-item label="用途">
              <a-input v-model:value="userMeta.usage" placeholder="如：官网 Banner / 详情页" />
            </a-form-item>
            <a-form-item label="版权说明">
              <a-input v-model:value="userMeta.copyright" placeholder="如：自有素材 / 已授权" />
            </a-form-item>
            <a-form-item label="备注">
              <a-textarea v-model:value="userMeta.remark" :rows="2" />
            </a-form-item>
          </a-form>
          <a-button type="primary" size="small" :loading="metaSaving" @click="saveUserMeta">保存</a-button>
        </a-card>

        <!-- 系统 metadata -->
        <a-card size="small" title="系统元数据">
          <div class="sys-meta">
            <div v-for="(v, k) in sysMeta" :key="k" class="sys-row">
              <span class="label">{{ k }}</span><span>{{ v }}</span>
            </div>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined, ThunderboltOutlined, DatabaseOutlined, SearchOutlined,
  CheckCircleOutlined, DownloadOutlined, PlusOutlined
} from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import { formatSize, formatTime, filePreviewUrl, FILE_TYPE, ASSET_STATUS, TASK_STATUS, UNIT_TYPE, statusTag } from './types'
import type { MmAssetDetail, MmProcessingTask } from './types'

const route = useRoute()
const router = useRouter()
const assetId = Number(route.params.id)

const asset = ref<MmAssetDetail | null>(null)
const units = ref<Array<any>>([])
const tasks = ref<MmProcessingTask[]>([])
const loading = ref(false)
const actionLoading = ref(false)

const showTagInput = ref(false)
const newTag = ref('')
const metaSaving = ref(false)

const typeInfo = computed(() => FILE_TYPE[asset.value?.file_type || 'file'] || FILE_TYPE.file)
const statusInfo = computed(() => statusTag(asset.value?.status || ''))
const previewSrc = computed(() => asset.value ? filePreviewUrl(asset.value) : null)
const aiMeta = computed(() => asset.value?.metadata?.ai || null)
const sysMeta = computed(() => {
  const s = asset.value?.metadata?.system || {}
  return Object.fromEntries(Object.entries(s).filter(([_, v]) => v !== null && v !== undefined))
})
const userMeta = ref<Record<string, string>>({ category: '', usage: '', copyright: '', remark: '' })

async function loadDetail() {
  loading.value = true
  try {
    const res = await multimodalApi.assetDetail(assetId)
    asset.value = res.data
    const um = (res.data.metadata?.user || {}) as Record<string, any>
    userMeta.value = {
      category: um.category || '',
      usage: um.usage || '',
      copyright: um.copyright || '',
      remark: um.remark || ''
    }
    if (res.data.units_count) await loadUnits()
    await loadTasks()
  } finally {
    loading.value = false
  }
}

async function loadUnits() {
  try {
    const res = await multimodalApi.units(assetId)
    units.value = res.data.items || []
  } catch { /* interceptor 已提示 */ }
}

async function loadTasks() {
  try {
    const res = await multimodalApi.processing(assetId, { page_size: 20 })
    tasks.value = res.data.items || []
  } catch { /* interceptor 已提示 */ }
}

async function refresh() {
  await loadDetail()
}

async function analyze() {
  actionLoading.value = true
  try {
    await multimodalApi.analyze(assetId)
    message.success('分析任务已提交，稍后刷新查看结果')
    await refresh()
  } catch { /* interceptor 已提示 */ } finally {
    actionLoading.value = false
  }
}

async function indexAsset() {
  try {
    await multimodalApi.index(assetId)
    message.success('索引任务已提交')
    await refresh()
  } catch { /* interceptor 已提示 */ }
}

async function approve() {
  try {
    await multimodalApi.approve(assetId, userMeta.value)
    message.success('审核通过，已开始向量化索引')
    await refresh()
  } catch { /* interceptor 已提示 */ }
}

async function findSimilar() {
  router.push(`/multimodal/search?kb=${asset.value?.knowledge_base_id}&similar=${assetId}`)
}

function download() {
  window.open(multimodalApi.downloadUrl(assetId), '_blank')
}

async function addTag() {
  const name = newTag.value.trim()
  if (!name) return
  try {
    await multimodalApi.addTags(assetId, [name])
    newTag.value = ''
    message.success('标签已添加')
    await refresh()
  } catch { /* interceptor 已提示 */ }
}

async function removeTag(tag: { id: number }) {
  try {
    await multimodalApi.removeTag(assetId, tag.id)
    await refresh()
  } catch { /* interceptor 已提示 */ }
}

async function saveUserMeta() {
  metaSaving.value = true
  try {
    await multimodalApi.updateMetadata(assetId, userMeta.value)
    message.success('已保存')
    await refresh()
  } catch { /* interceptor 已提示 */ } finally {
    metaSaving.value = false
  }
}

function unitIcon(type: string): string {
  return { image: '🖼️', shot: '🎬', segment: '🎵', slide: '📊' }[type] || '📦'
}

onMounted(loadDetail)
</script>

<style scoped>
.sub {
  font-size: 12px;
  opacity: 0.6;
}
.label {
  font-weight: 500;
  opacity: 0.75;
}
.preview-box {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 260px;
  max-height: 480px;
  background: rgba(128, 128, 128, 0.06);
  border-radius: 8px;
  overflow: auto;
}
.preview-box img, .preview-box video {
  max-width: 100%;
  max-height: 460px;
}
.no-preview {
  opacity: 0.5;
  padding: 40px;
  font-size: 15px;
}
.unit-list {
  max-height: 460px;
  overflow: auto;
}
.unit-item {
  display: flex;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px dashed rgba(128, 128, 128, 0.15);
}
.unit-item:last-child {
  border-bottom: none;
}
.unit-thumb {
  width: 84px;
  height: 56px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}
.unit-thumb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(128, 128, 128, 0.1);
  font-size: 20px;
}
.unit-head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}
.unit-content {
  font-size: 12.5px;
  opacity: 0.85;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ai-desc {
  font-size: 13px;
  line-height: 1.7;
  opacity: 0.9;
}
.ocr-box {
  margin-top: 4px;
  background: rgba(128, 128, 128, 0.08);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 140px;
  overflow: auto;
}
.sys-meta {
  font-size: 12.5px;
}
.sys-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed rgba(128, 128, 128, 0.1);
}
.sys-row:last-child {
  border-bottom: none;
}
.err {
  color: #ff4d4f;
  font-size: 12px;
  margin-top: 4px;
  word-break: break-all;
}
</style>
