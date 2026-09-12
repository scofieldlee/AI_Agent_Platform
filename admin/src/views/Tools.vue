<template>
  <div>
    <!-- Stats Overview -->
    <a-row :gutter="16" style="margin-bottom: 16px;">
      <a-col :span="6">
        <a-card>
          <a-statistic title="注册工具数" :value="tools.length" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="24h 总请求" :value="total24h" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="24h 成功" :value="success24h" style="--stat-color: #52c41a" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="24h 总体成功率" :value="overallRate" suffix="%" :precision="1" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Tools Table -->
    <a-card title="工具列表">
      <template #extra>
        <a-button size="small" @click="fetchTools">
          <ReloadOutlined /> 刷新
        </a-button>
      </template>
      <a-table :columns="columns" :data-source="tools" :loading="loading" row-key="name" size="middle"
        :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a style="font-family: monospace; font-weight: 500;" @click="openDetail(record)">{{ record.name }}</a>
          </template>
          <template v-if="column.key === 'tool_type'">
            <a-tag :color="toolTypeColor(record.tool_type)">{{ toolTypeLabel(record.tool_type) }}</a-tag>
          </template>
          <template v-if="column.key === 'description'">
            <span style="opacity: 0.75;">{{ record.description }}</span>
          </template>
          <template v-if="column.key === 'total_24h'">
            {{ record.total_24h || 0 }}
          </template>
          <template v-if="column.key === 'success_24h'">
            <span :style="{ color: record.error_24h > 0 ? '#faad14' : '#52c41a' }">
              {{ record.success_24h || 0 }}
            </span>
            <span v-if="record.error_24h > 0" style="color: #ff4d4f; margin-left: 6px; font-size: 12px;">
              (失败 {{ record.error_24h }})
            </span>
          </template>
          <template v-if="column.key === 'success_rate_24h'">
            <a-tag v-if="record.total_24h > 0"
              :color="(record.success_rate_24h ?? 0) >= 95 ? 'green' : (record.success_rate_24h ?? 0) >= 80 ? 'orange' : 'red'">
              {{ record.success_rate_24h }}%
            </a-tag>
            <span v-else style="opacity: 0.4;">—</span>
          </template>
          <template v-if="column.key === 'last_executed_24h'">
            {{ record.last_executed_24h ? formatTime(record.last_executed_24h, 'minute') : '24h 内无调用' }}
          </template>
          <template v-if="column.key === 'action'">
            <a-button size="small" type="link" @click="openDetail(record)">详情</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Detail Modal -->
    <a-modal v-model:open="detailOpen" :title="`工具详情：${detail?.name || ''}`" width="720px" :footer="null">
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <!-- 基本信息 -->
          <h4 class="section-title">基本信息</h4>
          <a-descriptions :column="2" size="small" bordered>
            <a-descriptions-item label="工具名称" :span="2">
              <code>{{ detail.name }}</code>
            </a-descriptions-item>
            <a-descriptions-item label="工具类型">
              <a-tag :color="toolTypeColor(detail.tool_type)">{{ toolTypeLabel(detail.tool_type) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag color="green">运行中</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="工具介绍" :span="2">
              {{ detail.description }}
            </a-descriptions-item>
          </a-descriptions>

          <!-- 24h 统计 -->
          <h4 class="section-title">近 24 小时调用统计</h4>
          <a-row :gutter="12">
            <a-col :span="6">
              <a-card size="small"><a-statistic title="请求次数" :value="detail.total_24h" /></a-card>
            </a-col>
            <a-col :span="6">
              <a-card size="small">
                <a-statistic title="成功次数" :value="detail.success_24h"
                  :value-style="{ color: '#52c41a' }" />
              </a-card>
            </a-col>
            <a-col :span="6">
              <a-card size="small">
                <a-statistic title="失败次数" :value="detail.error_24h"
                  :value-style="{ color: detail.error_24h > 0 ? '#ff4d4f' : undefined }" />
              </a-card>
            </a-col>
            <a-col :span="6">
              <a-card size="small">
                <a-statistic title="成功率" :value="detail.success_rate_24h ?? 0" suffix="%" :precision="1"
                  :value-style="{ color: (detail.success_rate_24h ?? 0) >= 95 ? '#52c41a' : '#faad14' }" />
              </a-card>
            </a-col>
          </a-row>
          <div style="margin-top: 8px; font-size: 12px; opacity: 0.65;">
            平均耗时：{{ detail.avg_duration_24h != null ? detail.avg_duration_24h + ' ms' : '—' }}
            · 最近调用：{{ detail.last_executed_24h ? formatTime(detail.last_executed_24h, 'minute') : '—' }}
            · 累计调用：{{ detail.total_all }} 次
          </div>

          <!-- 参数定义 -->
          <h4 class="section-title">参数定义（input_schema）</h4>
          <pre class="schema-pre">{{ formatSchema(detail.input_schema) }}</pre>

          <!-- 最近执行记录 -->
          <h4 class="section-title">最近执行记录</h4>
          <a-table :columns="logColumns" :data-source="detail.recent_logs || []" row-key="id" size="small"
            :pagination="false">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'created_at'">
                {{ formatTime(record.created_at, 'minute') }}
              </template>
              <template v-if="column.key === 'status'">
                <a-tag :color="record.status === 'success' ? 'green' : 'red'">
                  {{ record.status === 'success' ? '成功' : '失败' }}
                </a-tag>
              </template>
              <template v-if="column.key === 'error'">
                <a-tooltip :title="record.error">
                  <span style="font-size: 12px; color: #ff4d4f;">{{ record.error?.substring(0, 40) || '—' }}</span>
                </a-tooltip>
              </template>
            </template>
            <template #emptyText>
              <a-empty description="暂无执行记录" :image-style="{ height: '40px' }" />
            </template>
          </a-table>

          <!-- OCR 在线测试 -->
          <template v-if="detail.name === 'ocr_recognition'">
            <h4 class="section-title">在线测试</h4>
            <a-upload-dragger
              :before-upload="handleOcrFile"
              :show-upload-list="false"
              accept=".png,.jpg,.jpeg,.webp,.gif,.bmp,.pdf,image/*,application/pdf"
              :disabled="ocrRunning"
              style="margin-bottom: 12px;"
            >
              <p style="font-size: 13px; margin: 8px 0 4px;">
                <FileImageOutlined v-if="!ocrFile" style="font-size: 22px; color: #4f46e5;" />
                <CheckCircleOutlined v-else style="font-size: 22px; color: #52c41a;" />
              </p>
              <p style="font-size: 13px; margin: 0;">
                {{ ocrFile ? ocrFile.name : '点击或拖拽文件到此处' }}
              </p>
              <p style="font-size: 12px; opacity: 0.55; margin: 4px 0 8px;">
                支持图片（png/jpg/webp/gif/bmp）与 PDF（默认前 5 页），上限 20MB
              </p>
            </a-upload-dragger>
            <a-space style="margin-bottom: 12px;" wrap>
              <a-radio-group v-model:value="ocrScene" button-style="solid" size="small" :disabled="ocrRunning">
                <a-radio-button value="general">通用文字识别</a-radio-button>
                <a-radio-button value="business_card">名片结构化</a-radio-button>
              </a-radio-group>
              <a-button type="primary" size="small" :loading="ocrRunning" :disabled="!ocrFile"
                @click="runOcrTest">
                <ThunderboltOutlined /> 执行 OCR
              </a-button>
            </a-space>
            <template v-if="ocrResult">
              <a-alert v-if="ocrResult.structured" type="success" show-icon style="margin-bottom: 12px;">
                <template #message>名片结构化结果</template>
                <template #description>
                  <a-descriptions :column="2" size="small">
                    <a-descriptions-item v-for="(v, k) in ocrResult.structured" :key="k" :label="cardFieldLabel(String(k))">
                      {{ v || '—' }}
                    </a-descriptions-item>
                  </a-descriptions>
                </template>
              </a-alert>
              <pre class="schema-pre" style="max-height: 300px;">{{ ocrResult.text || '（空白图片）' }}</pre>
              <div style="margin-top: 6px; font-size: 12px; opacity: 0.6;">
                {{ ocrResult.file_type === 'pdf' ? `PDF 共识别 ${ocrResult.page_count} 页` : '图片识别' }}
                · 耗时 {{ ocrDuration }} ms
              </div>
            </template>
          </template>
        </template>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, FileImageOutlined, CheckCircleOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { toolsApi } from '@/api/client'
import { formatTime } from '@/utils/time'

const loading = ref(false)
const tools = ref<any[]>([])

const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)

const columns = [
  { title: '工具名称', key: 'name', width: 200 },
  { title: '类型', key: 'tool_type', width: 90 },
  { title: '工具介绍', key: 'description', ellipsis: true },
  { title: '24h 请求', key: 'total_24h', width: 90, align: 'center' as const },
  { title: '24h 成功', key: 'success_24h', width: 110, align: 'center' as const },
  { title: '成功率', key: 'success_rate_24h', width: 90, align: 'center' as const },
  { title: '最近执行', key: 'last_executed_24h', width: 150 },
  { title: '操作', key: 'action', width: 70 }
]

const logColumns = [
  { title: '时间', key: 'created_at', width: 140 },
  { title: '状态', key: 'status', width: 70 },
  { title: '耗时(ms)', dataIndex: 'duration_ms', key: 'duration_ms', width: 90 },
  { title: '错误信息', key: 'error', ellipsis: true }
]

const total24h = computed(() => tools.value.reduce((s, t) => s + (t.total_24h || 0), 0))
const success24h = computed(() => tools.value.reduce((s, t) => s + (t.success_24h || 0), 0))
const overallRate = computed(() =>
  total24h.value > 0 ? Math.round((success24h.value / total24h.value) * 1000) / 10 : 0
)

function toolTypeColor(t: string) {
  return { internal: 'blue', business: 'green', api: 'orange', database: 'purple', mcp: 'cyan', agent: 'pink' }[t] || 'default'
}
function toolTypeLabel(t: string) {
  return { internal: '内部', business: '业务', api: 'API', database: '数据库', mcp: 'MCP', agent: 'Agent' }[t] || t
}
function formatSchema(schema: any) {
  if (!schema || !Object.keys(schema).length) return '（未定义）'
  return JSON.stringify(schema, null, 2)
}

async function fetchTools() {
  loading.value = true
  try {
    const res = await toolsApi.stats()
    tools.value = res.data || []
  } catch {
    tools.value = []
  } finally { loading.value = false }
}

async function openDetail(record: any) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = { ...record, recent_logs: [] }
  resetOcrTest()
  try {
    const res = await toolsApi.detailStats(record.name)
    detail.value = res.data
  } catch {
    // 保留列表数据作为降级展示
  } finally { detailLoading.value = false }
}

// ===== OCR 在线测试 =====
const ocrFile = ref<File | null>(null)
const ocrBase64 = ref('')
const ocrScene = ref('general')
const ocrRunning = ref(false)
const ocrResult = ref<any>(null)
const ocrDuration = ref(0)

const CARD_FIELD_LABELS: Record<string, string> = {
  name: '姓名', name_en: '英文名', company: '公司', department: '部门',
  title: '职位', mobile: '手机', tel: '电话', email: '邮箱',
  website: '网址', address: '地址', other: '其他'
}
function cardFieldLabel(k: string) { return CARD_FIELD_LABELS[k] || k }

function resetOcrTest() {
  ocrFile.value = null
  ocrBase64.value = ''
  ocrScene.value = 'general'
  ocrRunning.value = false
  ocrResult.value = null
  ocrDuration.value = 0
}

function handleOcrFile(file: File) {
  if (file.size > 20 * 1024 * 1024) {
    message.error('文件超过 20MB 上限')
    return false
  }
  ocrFile.value = file
  ocrResult.value = null
  const reader = new FileReader()
  reader.onload = () => {
    ocrBase64.value = (reader.result as string).split(',')[1] || ''
  }
  reader.readAsDataURL(file)
  return false // 阻止自动上传
}

async function runOcrTest() {
  if (!ocrBase64.value) return
  ocrRunning.value = true
  ocrResult.value = null
  const start = Date.now()
  try {
    const res = await toolsApi.execute('ocr_recognition', {
      image_base64: ocrBase64.value,
      scene: ocrScene.value
    })
    ocrDuration.value = res.data.duration_ms || Date.now() - start
    if (res.data.success) {
      ocrResult.value = res.data.data
    } else {
      message.error(res.data.error || 'OCR 识别失败')
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'OCR 识别请求失败')
  } finally { ocrRunning.value = false }
}

onMounted(() => fetchTools())
</script>

<style scoped>
.section-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 500;
}
.schema-pre {
  background: rgba(128, 128, 128, 0.08);
  border: 1px solid rgba(128, 128, 128, 0.15);
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 240px;
  overflow: auto;
  margin: 0;
}
</style>
