<template>
  <div>
    <!-- Stats Overview -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 16px;">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="日志总数" :value="stats.total || 0" :value-style="{ color: '#4f46e5' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="今日" :value="stats.today_count || 0" :value-style="{ color: '#1677ff' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="成功" :value="stats.success_count || 0" :value-style="{ color: '#3f8600' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="失败" :value="stats.failed_count || 0" :value-style="{ color: '#cf1322' }" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Filter + Table -->
    <a-card>
      <!-- Filter Bar -->
      <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">
        <a-input v-model:value="filters.keyword" placeholder="搜索摘要/资源/用户/路径" allow-clear
          style="width: 220px;" @press-enter="load(1)" />
        <a-select v-model:value="filters.action" placeholder="动作" allow-clear style="width: 120px;" @change="load(1)">
          <a-select-option v-for="(label, value) in actionOptions" :key="value" :value="value">{{ label }}</a-select-option>
        </a-select>
        <a-select v-model:value="filters.resource_type" placeholder="资源类型" allow-clear style="width: 140px;" @change="load(1)">
          <a-select-option v-for="(label, value) in resourceOptions" :key="value" :value="value">{{ label }}</a-select-option>
        </a-select>
        <a-input v-model:value="filters.username" placeholder="操作人" allow-clear style="width: 120px;" @press-enter="load(1)" />
        <a-select v-model:value="filters.success" placeholder="结果" allow-clear style="width: 110px;" @change="load(1)">
          <a-select-option :value="true">成功</a-select-option>
          <a-select-option :value="false">失败</a-select-option>
        </a-select>
        <a-range-picker v-model:value="timeRange" :show-time="{ format: 'HH:mm:ss' }" format="YYYY-MM-DD HH:mm:ss"
          style="width: 360px;" @change="onTimeChange" />
        <a-button type="primary" @click="load(1)">查询</a-button>
        <a-button @click="resetFilters">重置</a-button>
        <a-button @click="refresh">刷新</a-button>
      </div>

      <a-table :columns="columns" :data-source="items" :loading="loading" row-key="id" size="middle"
        :pagination="pagination" @change="onTableChange"
        :scroll="{ x: 1200 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'created_at'">
            {{ fmtTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-tag :color="actionColor(record.action)">{{ actionLabel(record.action) }}</a-tag>
          </template>
          <template v-else-if="column.key === 'resource'">
            <template v-if="record.resource_name">
              <div>{{ record.resource_name }}</div>
              <div style="font-size: 12px; color: #999;">{{ resourceLabel(record.resource_type) }}<span v-if="record.resource_id"> #{{ record.resource_id }}</span></div>
            </template>
            <span v-else style="color: #999;">{{ resourceLabel(record.resource_type) || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'user'">
            <span>{{ record.username || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'path'">
            <div>
              <a-tag size="small" :color="methodColor(record.method)">{{ record.method }}</a-tag>
              <span style="font-size: 12px; word-break: break-all;">{{ record.path }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.success ? 'green' : 'red'">{{ record.status_code || '-' }} {{ record.success ? '成功' : '失败' }}</a-tag>
          </template>
          <template v-else-if="column.key === 'duration'">
            {{ record.duration_ms != null ? record.duration_ms + 'ms' : '-' }}
          </template>
          <template v-else-if="column.key === 'ip'">
            {{ record.ip_address || '-' }}
          </template>
          <template v-else-if="column.key === 'detail'">
            <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Detail Drawer -->
    <a-drawer :open="drawerOpen" :title="drawerTitle" width="560" @close="drawerOpen = false">
      <template v-if="detail">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="操作人">{{ detail.username || '-' }}
            <span v-if="detail.user_id" style="color:#999;"> (ID: {{ detail.user_id }})</span>
          </a-descriptions-item>
          <a-descriptions-item label="动作">
            <a-tag :color="actionColor(detail.action)">{{ actionLabel(detail.action) }}</a-tag>
            <a-tag style="margin-left:4px;">{{ resourceLabel(detail.resource_type) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="资源">
            {{ detail.resource_name || '-' }} <span v-if="detail.resource_id" style="color:#999;">#{{ detail.resource_id }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="摘要">{{ detail.summary || '-' }}</a-descriptions-item>
          <a-descriptions-item label="时间">{{ fmtTime(detail.created_at) }}</a-descriptions-item>
          <a-descriptions-item label="接口">
            <a-tag size="small">{{ detail.method }}</a-tag> {{ detail.path }}
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="detail.success ? 'green' : 'red'">{{ detail.status_code }}</a-tag>
            <span v-if="detail.duration_ms != null" style="margin-left: 8px;">{{ detail.duration_ms }}ms</span>
          </a-descriptions-item>
          <a-descriptions-item label="IP">{{ detail.ip_address || '-' }}</a-descriptions-item>
          <a-descriptions-item label="Request ID">
            <span style="word-break: break-all; font-size: 12px;">{{ detail.request_id }}</span>
          </a-descriptions-item>
          <a-descriptions-item v-if="detail.error_message" label="错误信息" :content-style="{ color: '#cf1322' }">
            {{ detail.error_message }}
          </a-descriptions-item>
        </a-descriptions>

        <!-- Changes diff -->
        <div v-if="detail.changes && Object.keys(detail.changes).length" style="margin-top: 16px;">
          <h4 style="margin-bottom: 8px;">字段变更</h4>
          <a-table :columns="changeColumns" :data-source="changeRows" size="small" row-key="field" :pagination="false" />
        </div>

        <!-- Request body -->
        <div v-if="detail.request_body" style="margin-top: 16px;">
          <h4 style="margin-bottom: 8px;">请求体</h4>
          <pre class="json-block">{{ JSON.stringify(detail.request_body, null, 2) }}</pre>
        </div>
      </template>
      <a-empty v-else description="加载中..." />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { auditApi } from '@/api/client'
import { fmtTime } from '@/utils/time'

const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const stats = ref<any>({})
const drawerOpen = ref(false)
const detail = ref<any>(null)

const filters = reactive({
  keyword: '',
  action: undefined as string | undefined,
  resource_type: undefined as string | undefined,
  username: '',
  success: undefined as boolean | undefined,
  start_time: undefined as string | undefined,
  end_time: undefined as string | undefined
})
const timeRange = ref<any>(null)

const actionOptions: Record<string, string> = {
  create: '创建', update: '修改', delete: '删除', login: '登录', logout: '登出',
  approve: '审核通过', reject: '驳回', export: '导出', execute: '执行',
  publish: '发布', disable: '停用', restore: '恢复', upload: '上传',
  set_default: '设为默认', bind: '绑定'
}
const resourceOptions: Record<string, string> = {
  user: '用户', role: '角色', permission: '权限', agent: 'Agent', workflow: '工作流',
  knowledge: '知识库', document: '文档', chunk: '知识分块', asset: '素材',
  knowledge_base: '多模态知识库', model_config: '模型配置', provider: '模型供应商',
  task: '处理任务', tool: '工具', conversation: '对话', memory: '记忆'
}

const columns = [
  { title: '时间', key: 'created_at', width: 160 },
  { title: '操作人', key: 'user', width: 110 },
  { title: '动作', key: 'action', width: 90 },
  { title: '资源', key: 'resource', width: 180 },
  { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
  { title: 'IP', key: 'ip', width: 130 },
  { title: '接口', key: 'path', width: 260 },
  { title: '状态', key: 'status', width: 100 },
  { title: '耗时', key: 'duration', width: 80 },
  { title: '操作', key: 'detail', width: 70, fixed: 'right' }
]

const changeColumns = [
  { title: '字段', dataIndex: 'field', key: 'field', width: 140 },
  { title: '变更前', key: 'before' },
  { title: '变更后', key: 'after' }
]

const changeRows = computed(() => {
  if (!detail.value?.changes) return []
  return Object.entries(detail.value.changes).map(([field, v]: any) => ({
    field,
    before: formatChangeValue(v?.before),
    after: formatChangeValue(v?.after)
  }))
})

const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`
}))

const page = ref(1)
const pageSize = ref(20)
const drawerTitle = computed(() => {
  const d = detail.value
  return d ? `${actionLabel(d.action)} · ${d.summary || d.path || ''}` : '日志详情'
})

function actionLabel(a?: string | null): string {
  return (a && actionOptions[a]) || a || '未知'
}
function resourceLabel(r?: string | null): string {
  return (r && resourceOptions[r]) || r || ''
}
function actionColor(a?: string | null): string {
  const map: Record<string, string> = {
    create: 'blue', update: 'geekblue', delete: 'red', login: 'green', logout: 'default',
    approve: 'cyan', reject: 'volcano', export: 'purple', execute: 'processing',
    publish: 'orange', disable: 'red', restore: 'green', upload: 'blue', set_default: 'gold', bind: 'purple'
  }
  return map[a || ''] || 'default'
}
function methodColor(m?: string | null): string {
  return { GET: 'green', POST: 'blue', PUT: 'orange', PATCH: 'gold', DELETE: 'red' }[m || ''] || 'default'
}
function formatChangeValue(v: any): string {
  if (v === null || v === undefined) return '-'
  if (Array.isArray(v)) return v.length ? v.join(', ') : '[]'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function load(p = 1) {
  loading.value = true
  try {
    page.value = p
    const params: any = { page: p, page_size: pageSize.value }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.action) params.action = filters.action
    if (filters.resource_type) params.resource_type = filters.resource_type
    if (filters.username) params.username = filters.username
    if (filters.success !== undefined) params.success = filters.success
    if (filters.start_time) params.start_time = filters.start_time
    if (filters.end_time) params.end_time = filters.end_time
    const res = await auditApi.list(params)
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await auditApi.stats(30)
    stats.value = res.data
  } catch { /* stats 非关键 */ }
}

function onTableChange(pg: any) {
  page.value = pg.current
  pageSize.value = pg.pageSize
  load(pg.current)
}

function onTimeChange(_dates: any, dateStrings: [string, string]) {
  filters.start_time = dateStrings[0] ? `${dateStrings[0]}:00` : undefined
  filters.end_time = dateStrings[1] ? `${dateStrings[1]}:59` : undefined
  load(1)
}

function resetFilters() {
  filters.keyword = ''
  filters.action = undefined
  filters.resource_type = undefined
  filters.username = ''
  filters.success = undefined
  filters.start_time = undefined
  filters.end_time = undefined
  timeRange.value = null
  load(1)
}

async function openDetail(record: any) {
  drawerOpen.value = true
  detail.value = null
  try {
    const res = await auditApi.detail(record.id)
    detail.value = res.data
  } catch {
    detail.value = record
  }
}

function refresh() {
  load(page.value)
  loadStats()
}

onMounted(() => {
  load(1)
  loadStats()
})
</script>

<style scoped>
.stat-card { border-radius: 8px; }
.json-block {
  background: #f5f5f5;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
