<template>
  <div>
    <!-- Stat Cards -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 24px;">
      <a-col v-if="canViewTickets" :xs="24" :sm="12" :lg="statColSpan">
        <a-card class="stat-card" :loading="loading">
          <a-statistic title="待处理工单" :value="taskStats.by_status?.pending || 0" :value-style="{ color: '#cf1322' }">
            <template #prefix><ClockCircleOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col v-if="canViewTickets" :xs="24" :sm="12" :lg="statColSpan">
        <a-card class="stat-card" :loading="loading">
          <a-statistic title="已解决工单" :value="taskStats.by_status?.resolved || 0" :value-style="{ color: '#3f8600' }">
            <template #prefix><CheckCircleOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col v-if="canViewAnalytics" :xs="24" :sm="12" :lg="statColSpan">
        <a-card class="stat-card" :loading="loading">
          <a-statistic title="总对话数" :value="analyticsStats.total_traces || 0" :value-style="{ color: '#4f46e5' }">
            <template #prefix><MessageOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col v-if="canViewAnalytics" :xs="24" :sm="12" :lg="statColSpan">
        <a-card class="stat-card" :loading="loading">
          <a-statistic title="成功率" :value="successRate" suffix="%" :value-style="{ color: '#7c3aed' }">
            <template #prefix><RiseOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]">
      <!-- Intent Distribution -->
      <a-col v-if="canViewAnalytics" :xs="24" :lg="12">
        <a-card title="意图分布" :loading="loading">
          <div v-if="intentDist.length > 0">
            <div v-for="item in intentDist" :key="item.intent" style="margin-bottom: 12px;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span>{{ intentLabel(item.intent) }}</span>
                <span style="color: #999;">{{ item.count }}</span>
              </div>
              <a-progress :percent="intentPercent(item.count)" :stroke-color="intentColor(item.intent)" :show-info="false" />
            </div>
          </div>
          <a-empty v-else description="暂无数据" />
        </a-card>
      </a-col>

      <!-- Recent Tasks -->
      <a-col v-if="canViewTickets" :xs="24" :lg="12">
        <a-card title="最近工单" :loading="loading">
          <a-list v-if="recentTasks.length > 0" :data-source="recentTasks" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta>
                  <template #title>
                    <span>{{ item.ticket_number }}</span>
                    <a-tag :color="priorityColor(item.priority)" style="margin-left: 8px;">
                      {{ priorityLabel(item.priority) }}
                    </a-tag>
                  </template>
                  <template #description>{{ item.transfer_reason }}</template>
                </a-list-item-meta>
                <template #actions>
                  <a-tag :color="statusColor(item.status)">{{ statusLabel(item.status) }}</a-tag>
                </template>
              </a-list-item>
            </template>
          </a-list>
          <a-empty v-else description="暂无工单" />
        </a-card>
      </a-col>
    </a-row>

    <a-row v-if="canViewAnalytics" :gutter="[16, 16]" style="margin-top: 16px;">
      <!-- Recent Traces -->
      <a-col :span="24">
        <a-card title="最近执行追踪" :loading="loading">
          <a-table :columns="traceColumns" :data-source="recentTraces" :pagination="false" row-key="trace_id" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="traceStatusColor(record.status)">{{ traceStatusLabel(record.status) }}</a-tag>
              </template>
              <template v-if="column.key === 'duration'">
                {{ record.duration_ms ? (record.duration_ms / 1000).toFixed(2) + 's' : '-' }}
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import {
  ClockCircleOutlined, CheckCircleOutlined, MessageOutlined, RiseOutlined
} from '@ant-design/icons-vue'
import { analyticsApi, tasksApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import dayjs from 'dayjs'

const authStore = useAuthStore()
const loading = ref(true)
const analyticsStats = ref<any>({})
const taskStats = ref<any>({})
const recentTasks = ref<any[]>([])
const recentTraces = ref<any[]>([])

const canViewAnalytics = computed(() => authStore.hasPermission('analytics:view'))
const canViewTickets = computed(() => authStore.hasPermission('ticket:view'))
const statColSpan = computed(() => {
  if (canViewTickets.value && canViewAnalytics.value) return 6
  return 12
})

const successRate = computed(() => {
  if (!analyticsStats.value.total_traces) return 0
  const success = analyticsStats.value.success_count || 0
  return Math.round((success / analyticsStats.value.total_traces) * 100)
})

const intentDist = computed(() => {
  const dist = analyticsStats.value.intent_distribution
  if (Array.isArray(dist)) return dist
  if (dist && typeof dist === 'object') {
    return Object.entries(dist).map(([intent, count]) => ({ intent, count: count as number }))
  }
  return []
})

const intentPercent = (count: number) => {
  const total = intentDist.value.reduce((sum: number, i: any) => sum + i.count, 0)
  return total > 0 ? Math.round((count / total) * 100) : 0
}

function intentLabel(intent: string) {
  const map: Record<string, string> = {
    product_info: '商品咨询', product_compare: '商品对比', purchase_advice: '购买建议',
    order_query: '订单查询', after_sale: '售后问题', complaint: '投诉', greeting: '问候', unknown: '未知'
  }
  return map[intent] || intent
}

function intentColor(intent: string) {
  const map: Record<string, string> = {
    product_info: '#4f46e5', product_compare: '#7c3aed', purchase_advice: '#06b6d4',
    order_query: '#f59e0b', after_sale: '#ef4444', complaint: '#dc2626', greeting: '#10b981', unknown: '#9ca3af'
  }
  return map[intent] || '#9ca3af'
}

function priorityColor(p: string) {
  return { urgent: 'red', high: 'orange', normal: 'blue', low: 'default' }[p] || 'default'
}
function priorityLabel(p: string) {
  return { urgent: '紧急', high: '高', normal: '普通', low: '低' }[p] || p
}
function statusColor(s: string) {
  return { pending: 'orange', assigned: 'blue', resolved: 'green', closed: 'default' }[s] || 'default'
}
function statusLabel(s: string) {
  return { pending: '待处理', assigned: '已分配', resolved: '已解决', closed: '已关闭' }[s] || s
}
function traceStatusColor(s: string) {
  return { success: 'green', failed: 'red', running: 'blue', human_transfer: 'orange' }[s] || 'default'
}
function traceStatusLabel(s: string) {
  return { success: '成功', failed: '失败', running: '运行中', human_transfer: '转人工' }[s] || s
}

const traceColumns = [
  { title: 'Trace ID', dataIndex: 'trace_id', key: 'trace_id', ellipsis: true },
  { title: '意图', dataIndex: 'intent', key: 'intent', customRender: ({ text }: any) => intentLabel(text) },
  { title: '置信度', dataIndex: 'confidence', key: 'confidence', customRender: ({ text }: any) => text ? (text * 100).toFixed(0) + '%' : '-' },
  { title: '状态', key: 'status' },
  { title: '耗时', key: 'duration' },
  { title: '时间', dataIndex: 'created_at', key: 'created_at', customRender: ({ text }: any) => text ? dayjs(text).format('MM-DD HH:mm') : '-' }
]

const dataLoaded = ref(false)

async function loadDashboardData() {
  if (dataLoaded.value) return
  loading.value = true
  try {
    const tasks: Promise<void>[] = []

    if (canViewAnalytics.value) {
      tasks.push(
        analyticsApi.getStats().then(res => { analyticsStats.value = res.data }).catch(() => {}),
        analyticsApi.getTraces({ limit: 10 }).then(res => { recentTraces.value = res.data }).catch(() => {})
      )
    }

    if (canViewTickets.value) {
      tasks.push(
        tasksApi.stats().then(res => { taskStats.value = res.data }).catch(() => {}),
        tasksApi.list({ page: 1, page_size: 5 }).then(res => {
          recentTasks.value = res.data.tasks || res.data || []
        }).catch(() => {})
      )
    }

    await Promise.allSettled(tasks)
    dataLoaded.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadDashboardData()
})

// Re-load when user state becomes available (e.g., after fetchUser in AdminLayout)
watch(() => authStore.user, (newUser) => {
  if (newUser && !dataLoaded.value) {
    loadDashboardData()
  }
})
</script>
