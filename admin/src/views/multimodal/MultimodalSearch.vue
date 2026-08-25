<template>
  <div>
    <div style="margin-bottom: 16px;">
      <h2 style="margin: 0;">多模态检索</h2>
      <span style="opacity: 0.65; font-size: 13px;">
        支持文本搜素材 / 以图搜图 / 文本+图片融合检索（基于 1024 维统一向量空间）
      </span>
    </div>

    <!-- 检索面板 -->
    <a-card style="margin-bottom: 16px;">
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :xs="24" :md="8">
            <a-form-item label="知识库">
              <a-select v-model:value="kbId" :options="kbOptions" placeholder="选择知识库" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="素材类型过滤">
              <a-select v-model:value="assetTypes" mode="multiple" allowClear placeholder="不过滤"
                :options="typeOptions" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="返回数量 / 最低相似度">
              <div style="display: flex; gap: 12px; align-items: center;">
                <a-input-number v-model:value="topK" :min="1" :max="50" style="width: 90px;" />
                <a-slider v-model:value="minScore" :min="0" :max="1" :step="0.05"
                  style="flex: 1; margin: 0;" :tooltip-open="false" />
                <span style="white-space: nowrap;">{{ minScore.toFixed(2) }}</span>
              </div>
            </a-form-item>
          </a-col>
        </a-row>

        <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start;">
          <!-- 文本查询 -->
          <div style="flex: 1; min-width: 260px;">
            <a-form-item label="文本查询" style="margin-bottom: 0;">
              <a-textarea v-model:value="query" :rows="2" placeholder="如：蓝色包装的产品图 / 展示操作步骤的 PPT 页"
                @pressEnter="doSearch" />
            </a-form-item>
          </div>
          <!-- 图片查询 -->
          <div>
            <a-form-item label="查询图片（以图搜图）" style="margin-bottom: 0;">
              <div class="img-picker" @click="pickImage">
                <img v-if="queryImagePreview" :src="queryImagePreview" />
                <div v-else class="img-placeholder">
                  <PictureOutlined />
                  <span>点击选择图片</span>
                </div>
              </div>
              <input ref="fileInputRef" type="file" accept="image/*" style="display: none;" @change="onImageChange" />
              <a-button v-if="queryImage" size="small" type="link" danger @click="clearImage">移除图片</a-button>
            </a-form-item>
          </div>
        </div>

        <div style="margin-top: 16px; display: flex; gap: 12px;">
          <a-button type="primary" :loading="searching" :disabled="!canSearch" @click="doSearch">
            <SearchOutlined /> 检索
          </a-button>
          <a-button @click="reset"><ClearOutlined /> 重置</a-button>
          <span v-if="queryTypeLabel" style="align-self: center; opacity: 0.7;">
            检索模式：<a-tag color="geekblue">{{ queryTypeLabel }}</a-tag>
          </span>
        </div>
      </a-form>
    </a-card>

    <!-- 相似素材提示 -->
    <a-alert v-if="similarAssetId" type="info" show-icon closable style="margin-bottom: 16px;"
      :message="`以素材 #${similarAssetId} 为基准查找相似素材`" />

    <!-- 结果 -->
    <a-card size="small">
      <template #title>
        检索结果
        <a-tag v-if="searched">{{ results.length }}</a-tag>
      </template>

      <a-empty v-if="!searched" description="输入文本或选择图片后开始检索" />
      <a-empty v-else-if="!results.length" description="无匹配结果（可尝试降低相似度阈值）" />

      <div v-else class="result-grid">
        <div v-for="r in results" :key="`${r.asset_id}-${r.unit_id || 0}`" class="result-card">
          <div class="result-thumb" @click="router.push(`/multimodal/assets/${r.asset_id}`)">
            <img v-if="r.thumbnail_url || r.preview_url" :src="(r.thumbnail_url || r.preview_url) as string" loading="lazy" />
            <div v-else class="thumb-empty">{{ typeIcon(r.asset_type) }}</div>
            <div class="score-badge" :style="scoreStyle(r.score)">{{ (r.score * 100).toFixed(1) }}%</div>
          </div>
          <div class="result-body">
            <div class="result-name" :title="r.asset_name || ''" @click="router.push(`/multimodal/assets/${r.asset_id}`)">
              {{ r.asset_name || r.asset_code }}
            </div>
            <div class="result-sub">
              <a-tag size="small" :color="FILE_TYPE[r.asset_type || 'file']?.color">
                {{ FILE_TYPE[r.asset_type || 'file']?.label || r.asset_type }}
              </a-tag>
              <span v-if="r.unit_type">{{ UNIT_TYPE[r.unit_type] || r.unit_type }} #{{ (r.unit_index ?? 0) + 1 }}</span>
              <span v-if="r.start_time != null">{{ formatTime(r.start_time) }}</span>
            </div>
            <div v-if="r.description || r.content" class="result-desc">{{ r.description || r.content }}</div>
            <div v-if="r.tags?.length" class="result-tags">
              <a-tag v-for="t in r.tags.slice(0, 4)" :key="t" size="small" color="purple">{{ t }}</a-tag>
            </div>
          </div>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  SearchOutlined, ClearOutlined, PictureOutlined
} from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import { formatTime, FILE_TYPE, UNIT_TYPE } from './types'
import type { MmSearchResult } from './types'

const route = useRoute()
const router = useRouter()

const kbs = ref<Array<{ id: number; name: string; asset_count: number }>>([])
const kbOptions = computed(() => kbs.value.map(k => ({ label: `${k.name}（${k.asset_count}）`, value: k.id })))
const kbId = ref<number | undefined>(undefined)

const query = ref('')
const queryImage = ref<File | null>(null)
const queryImagePreview = ref<string | null>(null)
const assetTypes = ref<string[]>([])
const topK = ref(12)
const minScore = ref(0)
const searching = ref(false)
const searched = ref(false)
const results = ref<MmSearchResult[]>([])
const queryTypeLabel = ref('')
const similarAssetId = ref<number | null>(null)

const fileInputRef = ref<HTMLInputElement | null>(null)

const typeOptions = Object.entries(FILE_TYPE).map(([value, t]) => ({ label: `${t.icon} ${t.label}`, value }))
const canSearch = computed(() => !!kbId.value && (!!query.value.trim() || !!queryImage.value || !!similarAssetId.value))

function pickImage() { fileInputRef.value?.click() }

function onImageChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    queryImage.value = file
    queryImagePreview.value = URL.createObjectURL(file)
  }
}

function clearImage() {
  queryImage.value = null
  queryImagePreview.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function doSearch() {
  if (!canSearch.value) {
    message.warning('请选择知识库并输入文本或图片')
    return
  }
  searching.value = true
  try {
    if (similarAssetId.value && !query.value && !queryImage.value) {
      // 以图搜图模式
      const res = await multimodalApi.similar(similarAssetId.value, topK.value)
      results.value = mapSimilar(res.data)
      queryTypeLabel.value = '以图搜图'
    } else {
      const res = await multimodalApi.search({
        knowledge_base_id: kbId.value!,
        query: query.value.trim() || undefined,
        asset_types: assetTypes.value.join(','),
        top_k: topK.value,
        min_score: minScore.value,
        query_image: queryImage.value
      })
      results.value = res.data.results || []
      const typeLabelMap: Record<string, string> = { text: '文本检索', image: '以图搜图', 'text+image': '图文融合' }
      queryTypeLabel.value = typeLabelMap[res.data.query_type] || res.data.query_type
    }
    searched.value = true
    if (!results.value.length) message.info('无匹配结果')
  } catch {
    /* interceptor 已提示 */
  } finally {
    searching.value = false
  }
}

function mapSimilar(data: any): MmSearchResult[] {
  const items = data?.results || data?.items || []
  return items.map((i: any) => ({
    asset_id: i.asset_id, asset_code: i.asset_code, asset_name: i.asset_name,
    asset_type: i.asset_type || i.file_type, unit_id: i.unit_id, unit_type: i.unit_type,
    unit_index: i.unit_index, score: i.score, description: i.description,
    content: i.content, start_time: i.start_time, end_time: i.end_time,
    thumbnail_url: i.thumbnail_url, preview_url: i.preview_url, tags: i.tags || []
  }))
}

function reset() {
  query.value = ''
  clearImage()
  assetTypes.value = []
  topK.value = 12
  minScore.value = 0
  results.value = []
  searched.value = false
  queryTypeLabel.value = ''
  similarAssetId.value = null
}

function typeIcon(type?: string | null): string {
  return FILE_TYPE[type || 'file'].icon
}

function scoreStyle(score: number) {
  if (score >= 0.75) return { background: '#52c41a' }
  if (score >= 0.5) return { background: '#faad14' }
  return { background: '#8c8c8c' }
}

onMounted(async () => {
  const kbParam = Number(route.query.kb)
  const similarParam = Number(route.query.similar)
  if (similarParam) {
    similarAssetId.value = similarParam
    topK.value = 10
  }
  try {
    const res = await multimodalApi.listKbs()
    kbs.value = res.data
    kbId.value = kbParam || (res.data[0]?.id)
    // 有 similar 参数时自动检索
    if (similarAssetId.value && kbId.value) await doSearch()
  } catch { /* interceptor 已提示 */ }
})
</script>

<style scoped>
.img-picker {
  width: 140px;
  height: 100px;
  border: 1px dashed rgba(128, 128, 128, 0.4);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s;
}
.img-picker:hover {
  border-color: #4f46e5;
}
.img-picker img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.img-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  opacity: 0.5;
  font-size: 12px;
}
.img-placeholder :deep(.anticon) {
  font-size: 22px;
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.result-card {
  border: 1px solid rgba(128, 128, 128, 0.18);
  border-radius: 10px;
  overflow: hidden;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.result-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
.result-thumb {
  position: relative;
  height: 150px;
  background: rgba(128, 128, 128, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.result-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-empty {
  font-size: 32px;
  opacity: 0.4;
}
.score-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  backdrop-filter: blur(4px);
}
.result-body {
  padding: 10px 12px;
}
.result-name {
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.result-sub {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.75;
}
.result-desc {
  margin-top: 6px;
  font-size: 12px;
  opacity: 0.75;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.result-tags {
  margin-top: 6px;
  overflow: hidden;
  height: 22px;
}
</style>
