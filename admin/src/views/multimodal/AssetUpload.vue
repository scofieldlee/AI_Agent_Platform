<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="margin: 0;">素材上传</h2>
        <span style="opacity: 0.65; font-size: 13px;">
          支持图片 / 视频 / 音频 / PPT / PDF / Word / Excel，可批量拖拽
        </span>
      </div>
      <a-button @click="router.back()">
        <ArrowLeftOutlined /> 返回
      </a-button>
    </div>

    <!-- 知识库选择 -->
    <a-card size="small" style="margin-bottom: 16px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-weight: 500;">目标知识库：</span>
        <a-select v-model:value="kbId" style="min-width: 280px;" placeholder="选择要上传到的知识库"
          :options="kbOptions" @change="onKbChange" />
        <a-alert v-if="!kbId" type="warning" show-icon message="请先选择目标知识库" style="flex: 1;" />
      </div>
    </a-card>

    <!-- 拖拽区 -->
    <a-upload-dragger
      v-model:fileList="fileList"
      :multiple="true"
      :before-upload="beforeUpload"
      :show-upload-list="false"
      accept="image/*,video/*,audio/*,.ppt,.pptx,.pdf,.doc,.docx,.xls,.xlsx"
      :disabled="!kbId"
      @drop="onDrop"
    >
      <p class="ant-upload-drag-icon"><InboxOutlined /></p>
      <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
      <p class="ant-upload-hint">
        单文件限制：图片 50MB · 视频 500MB · 音频 200MB · PPT/PDF/文档 100MB
      </p>
    </a-upload-dragger>

    <!-- 待上传文件列表 -->
    <a-card v-if="pendingFiles.length" size="small" style="margin-top: 16px;" title="待上传文件">
      <template #extra>
        <a-space>
          <a-button size="small" @click="clearAll">清空</a-button>
          <a-button type="primary" size="small" :loading="uploading" @click="doUpload">
            <CloudUploadOutlined /> 上传 {{ pendingFiles.length }} 个文件
          </a-button>
        </a-space>
      </template>
      <div class="pending-list">
        <div v-for="(f, idx) in pendingFiles" :key="idx" class="pending-item">
          <span class="type-icon">{{ typeIcon(f.name) }}</span>
          <span class="fname" :title="f.name">{{ f.name }}</span>
          <span class="fsize">{{ formatSize(f.size) }}</span>
          <a-button type="text" danger size="small" @click="removeFile(idx)">
            <DeleteOutlined />
          </a-button>
        </div>
      </div>
    </a-card>

    <!-- 上传结果 -->
    <a-card v-if="results.length" size="small" style="margin-top: 16px;" title="上传结果">
      <template #extra>
        <a-tag color="green">成功 {{ successCount }}</a-tag>
        <a-tag v-if="failCount" color="red">失败 {{ failCount }}</a-tag>
      </template>
      <div class="pending-list">
        <div v-for="(r, idx) in results" :key="idx" class="pending-item">
          <span :class="r.success ? 'ok' : 'fail'">{{ r.success ? '✓' : '✗' }}</span>
          <span class="fname" :title="r.filename">{{ r.filename }}</span>
          <span v-if="r.success" style="opacity: 0.6;">{{ r.asset_code }}</span>
          <span v-else class="err">{{ r.error }}</span>
        </div>
      </div>
      <a-alert type="info" show-icon style="margin-top: 12px;"
        message="上传完成后系统将自动入队 AI 分析（需 Worker 运行 + DASHSCOPE_API_KEY 配置）。可在「处理任务」页面监控进度。" />
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  InboxOutlined, CloudUploadOutlined, DeleteOutlined, ArrowLeftOutlined
} from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import { formatSize, FILE_TYPE } from './types'

const route = useRoute()
const router = useRouter()

const kbId = ref<number | undefined>(undefined)
const kbs = ref<Array<{ id: number; name: string; asset_count: number }>>([])
const kbOptions = computed(() =>
  kbs.value.map(k => ({ label: `${k.name}（${k.asset_count} 素材）`, value: k.id })))

const fileList = ref<any[]>([])
const pendingFiles = ref<File[]>([])
const uploading = ref(false)

interface UploadItem { success: boolean; filename: string; asset_code?: string | null; error?: string | null }
const results = ref<UploadItem[]>([])
const successCount = computed(() => results.value.filter(r => r.success).length)
const failCount = computed(() => results.value.filter(r => !r.success).length)

function beforeUpload(file: File) {
  pendingFiles.value = [...pendingFiles.value, file]
  return false // 阻止自动上传
}

function onDrop(e: DragEvent) {
  const files = e.dataTransfer?.files
  if (files) pendingFiles.value = [...pendingFiles.value, ...Array.from(files)]
}

function removeFile(idx: number) {
  pendingFiles.value = pendingFiles.value.filter((_, i) => i !== idx)
}

function clearAll() {
  pendingFiles.value = []
  results.value = []
}

function typeIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', webp: 'image', bmp: 'image',
    mp4: 'video', mov: 'video', avi: 'video', mkv: 'video', webm: 'video',
    mp3: 'audio', wav: 'audio', m4a: 'audio', aac: 'audio', flac: 'audio',
    ppt: 'ppt', pptx: 'ppt', pdf: 'pdf',
    doc: 'doc', docx: 'doc', xls: 'doc', xlsx: 'doc'
  }
  return FILE_TYPE[map[ext] || 'file'].icon
}

async function doUpload() {
  if (!kbId.value) {
    message.warning('请先选择目标知识库')
    return
  }
  if (!pendingFiles.value.length) return
  uploading.value = true
  results.value = []
  try {
    const res = await multimodalApi.upload(kbId.value, pendingFiles.value)
    results.value = res.data.items || []
    if (res.data.failed_count === 0) {
      message.success(`全部 ${res.data.success_count} 个文件上传成功`)
      pendingFiles.value = []
      fileList.value = []
    } else {
      message.warning(`成功 ${res.data.success_count} 个，失败 ${res.data.failed_count} 个`)
    }
  } finally {
    uploading.value = false
  }
}

function onKbChange() {
  results.value = []
}

onMounted(async () => {
  const kbParam = Number(route.query.kb)
  if (kbParam) kbId.value = kbParam
  try {
    const res = await multimodalApi.listKbs()
    kbs.value = res.data
    if (!kbId.value && res.data.length === 1) kbId.value = res.data[0].id
  } catch { /* interceptor 已提示 */ }
})
</script>

<style scoped>
.pending-list {
  max-height: 320px;
  overflow: auto;
}
.pending-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 4px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.12);
}
.pending-item:last-child {
  border-bottom: none;
}
.fname {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fsize {
  opacity: 0.6;
  font-size: 12px;
  white-space: nowrap;
}
.ok { color: #52c41a; }
.fail { color: #ff4d4f; }
.err {
  color: #ff4d4f;
  font-size: 12px;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
