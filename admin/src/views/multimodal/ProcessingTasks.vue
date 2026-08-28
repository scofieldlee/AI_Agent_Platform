<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
      <div>
        <h2 style="margin: 0;">处理任务</h2>
        <span style="opacity: 0.65; font-size: 13px;">
          AI 分析 / 向量索引异步任务监控 · 共 {{ total }} 条
        </span>
      </div>
      <a-space>
        <a-tag :color="queueDepth > 0 ? 'orange' : 'green'" style="font-size: 13px; padding: 4px 12px;">
          队列深度：{{ queueDepth }}
        </a-tag>
        <a-button :type="autoRefresh ? 'primary' : 'default'" @click="toggleAuto">
          <SyncOutlined :spin="autoRefresh" /> {{ autoRefresh ? '自动刷新中(5s)' : '自动刷新' }}
        </a-button>
        <a-button @click="loadAll"><ReloadOutlined /> 刷新</a-button>
      </a-space>
    </div>

    <!-- 状态统计卡片 -->
    <a-row :gutter="12" style="margin-bottom: 16px;">
      <a-col v-for="(s, key) in TASK_STATUS" :key="key" :span="6">
        <a-card size="small">
          <a-statistic :title="s.label" :value="statusCounts[key] || 0"
            :value-style="{ color: s.color === 'success' ? '#52c41a' : s.color === 'error' ? '#ff4d4f' : s.color === 'processing' ? '#1677ff' : undefined }" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 筛选 -->
    <a-card size="small" style="margin-bottom: 16px;">
      <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <a-select v-model:value="filters.task_type" style="width: 130px;" allowClear placeholder="任务类型"
          :options="[{ label: 'AI 分析', value: 'analysis' }, { label: '向量索引', value: 'index' }]"
          @change="onFilterChange" />
        <a-select v-model:value="filters.status" style="width: 130px;" allowClear placeholder="状态"
          :options="statusOptions" @change="onFilterChange" />
      </div>
    </a-card>

    <!-- 任务表 -->
    <a-table :data-source="tasks" :loading="loading" row-key="id" :pagination="pagination"
      @change="onTableChange" size="middle">
      <a-table-column title="ID" dataIndex="id" :width="70" />
      <a-table-column title="任务" :width="100">
        <template #default="{ record }">
          {{ record.task_type === 'analysis' ? '🤖 AI 分析' : '🧮 向量索引' }}
        </template>
      </a-table-column>
      <a-table-column title="状态" :width="100">
        <template #default="{ record }">
          <a-tag :color="TASK_STATUS[record.status]?.color">
            {{ TASK_STATUS[record.status]?.label || record.status }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="素材" :width="200">
        <template #default="{ record }">
          <a v-if="record.asset_id" @click="router.push(`/multimodal/assets/${record.asset_id}`)">
            #{{ record.asset_id }} {{ record.asset?.name || record.asset_name || '' }}
          </a>
          <span v-else>-</span>
        </template>
      </a-table-column>
      <a-table-column title="模型" :width="150">
        <template #default="{ record }">
          <span style="font-size: 12px; opacity: 0.7;">{{ record.model || '-' }}</span>
        </template>
      </a-table-column>
      <a-table-column title="错误" ellipsis>
        <template #default="{ record }">
          <a-tooltip v-if="record.error" :title="record.error">
            <span style="color: #ff4d4f; font-size: 12px;">{{ record.error }}</span>
          </a-tooltip>
          <span v-else style="opacity: 0.4;">-</span>
        </template>
      </a-table-column>
      <a-table-column title="重试" dataIndex="retry_count" :width="70" />
      <a-table-column title="时间" :width="160">
        <template #default="{ record }">
          <div style="font-size: 12px;">
            <div>创建: {{ fmtTime(record.created_at) }}</div>
            <div v-if="record.completed_at" style="opacity: 0.7;">
              完成: {{ fmtTime(record.completed_at) }}
            </div>
          </div>
        </template>
      </a-table-column>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import { TASK_STATUS } from './types'
import { formatTime } from '@/utils/time'
import type { MmProcessingTask } from './types'

const router = useRouter()
const loading = ref(false)
const tasks = ref<MmProcessingTask[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const queueDepth = ref(0)
const autoRefresh = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const filters = ref<{ task_type?: string; status?: string }>({})
const statusOptions = Object.entries(TASK_STATUS).map(([value, s]) => ({ label: s.label, value }))

const statusCounts = computed(() => {
  const counts: Record<string, number> = {}
  // 近 500 条内统计（当前页数据 + 无过滤时用概略值）
  tasks.value.forEach(t => { counts[t.status] = (counts[t.status] || 0) + 1 })
  return counts
})

const pagination = computed(() => ({
  total: total.value,
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`
}))

async function loadAll() {
  loading.value = true
  try {
    const [taskRes, queueRes] = await Promise.all([
      multimodalApi.tasks({
        task_type: filters.value.task_type,
        status: filters.value.status,
        page: page.value,
        page_size: pageSize.value
      }),
      multimodalApi.queueStatus()
    ])
    tasks.value = taskRes.data.items || []
    total.value = taskRes.data.total || 0
    queueDepth.value = queueRes.data.queue_depth || 0
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  loadAll()
}

function onTableChange(pag: any) {
  page.value = pag.current
  pageSize.value = pag.pageSize
  loadAll()
}

function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    timer = setInterval(loadAll, 5000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function fmtTime(t?: string | null): string {
  // 统一按北京时间显示（后端输出的时间已是北京时间，此处做兜底换算）
  return formatTime(t, 'second')
}

onMounted(loadAll)
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
