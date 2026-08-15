<template>
  <div>
    <!-- Stats Overview -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 16px;">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="总 Trace" :value="stats.total_traces || 0" :value-style="{ color: '#4f46e5' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="成功" :value="stats.success_count || 0" :value-style="{ color: '#3f8600' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="平均耗时" :value="avgDuration" suffix="s" :value-style="{ color: '#1677ff' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="转人工" :value="stats.human_transfer_count || 0" :value-style="{ color: '#fa8c16' }" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Trace List -->
    <a-card title="执行追踪列表">
      <a-table :columns="columns" :data-source="traces" :loading="loading" row-key="trace_id"
        :pagination="{ pageSize: 15 }" size="middle"
        :expanded-row-keys="expandedKeys"
        @expand="onExpand">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'intent'">
            {{ intentLabel(record.intent) }}
          </template>
          <template v-if="column.key === 'confidence'">
            <a-progress v-if="record.confidence" type="circle" :size="40"
              :percent="Math.round(record.confidence * 100)"
              :stroke-color="record.confidence > 0.7 ? '#52c41a' : record.confidence > 0.5 ? '#faad14' : '#ff4d4f'" />
            <span v-else>-</span>
          </template>
          <template v-if="column.key === 'duration'">
            {{ record.duration_ms ? (record.duration_ms / 1000).toFixed(2) + 's' : '-' }}
          </template>
          <template v-if="column.key === 'tokens'">
            {{ record.total_tokens || '-' }}
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
        </template>

        <!-- Expanded Row: Spans -->
        <template #expandedRowRender="{ record }">
          <div v-if="spanMap[record.trace_id]" style="padding: 8px 0;">
            <a-timeline>
              <a-timeline-item v-for="span in spanMap[record.trace_id]" :key="span.span_id"
                :color="span.status === 'success' ? 'green' : span.status === 'failed' ? 'red' : 'blue'">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <strong>{{ span.node_name }}</strong>
                  <a-tag size="small">{{ span.node_type }}</a-tag>
                  <span style="color: #999; font-size: 12px;">
                    {{ span.duration_ms ? (span.duration_ms / 1000).toFixed(2) + 's' : '-' }}
                  </span>
                  <a-tag v-if="span.token_usage" size="small" color="purple">{{ span.token_usage }} tokens</a-tag>
                </div>
                <div v-if="span.metadata" style="margin-top: 4px; font-size: 12px; color: #666; max-height: 60px; overflow: hidden;">
                  {{ JSON.stringify(span.metadata).substring(0, 200) }}
                </div>
              </a-timeline-item>
            </a-timeline>
          </div>
          <div v-else style="text-align: center; padding: 20px;">
            <a-spin />
          </div>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { analyticsApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const stats = ref<any>({})
const traces = ref<any[]>([])
const expandedKeys = ref<string[]>([])
const spanMap = reactive<Record<string, any[]>>({})

const avgDuration = computed(() => {
  if (!stats.value.avg_duration_ms) return 0
  return (stats.value.avg_duration_ms / 1000).toFixed(2)
})

const columns = [
  { title: 'Trace ID', dataIndex: 'trace_id', key: 'trace_id', ellipsis: true, width: 200 },
  { title: '意图', key: 'intent', width: 100 },
  { title: '置信度', key: 'confidence', width: 70 },
  { title: '状态', key: 'status', width: 90 },
  { title: '耗时', key: 'duration', width: 80 },
  { title: 'Tokens', key: 'tokens', width: 80 },
  { title: '时间', key: 'created_at', width: 160 }
]

function statusColor(s: string) { return { success: 'green', failed: 'red', running: 'blue', human_transfer: 'orange' }[s] || 'default' }
function statusLabel(s: string) { return { success: '成功', failed: '失败', running: '运行中', human_transfer: '转人工' }[s] || s }
function intentLabel(i: string) {
  const map: Record<string, string> = { product_info: '商品咨询', product_compare: '商品对比', purchase_advice: '购买建议', order_query: '订单查询', after_sale: '售后', complaint: '投诉', greeting: '问候', unknown: '未知' }
  return map[i] || i || '-'
}
function formatDate(d: string) { return d ? dayjs(d).format('YYYY-MM-DD HH:mm:ss') : '-' }

async function onExpand(expanded: boolean, record: any) {
  if (expanded) {
    expandedKeys.value = [...expandedKeys.value, record.trace_id]
    if (!spanMap[record.trace_id]) {
      try {
        const res = await analyticsApi.getSpans(record.trace_id)
        spanMap[record.trace_id] = res.data || []
      } catch {
        spanMap[record.trace_id] = []
      }
    }
  } else {
    expandedKeys.value = expandedKeys.value.filter(k => k !== record.trace_id)
  }
}

async function fetchStats() {
  try { const res = await analyticsApi.getStats(); stats.value = res.data } catch {}
}

async function fetchTraces() {
  loading.value = true
  try {
    const res = await analyticsApi.getTraces({ limit: 50 })
    traces.value = res.data || []
  } finally { loading.value = false }
}

onMounted(() => { fetchStats(); fetchTraces() })
</script>
