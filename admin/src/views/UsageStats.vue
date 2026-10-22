<template>
  <div class="usage-page">
    <!-- Filters -->
    <a-card :bordered="false" class="filter-card">
      <a-space wrap :size="12">
        <span style="font-size: 13px; color: #666;">时间范围</span>
        <a-radio-group v-model:value="rangeKey" button-style="solid" size="small" @change="reload">
          <a-radio-button value="7d">近 7 天</a-radio-button>
          <a-radio-button value="30d">近 30 天</a-radio-button>
          <a-radio-button value="90d">近 90 天</a-radio-button>
          <a-radio-button value="all">全部</a-radio-button>
        </a-radio-group>
        <a-divider type="vertical" />
        <span style="font-size: 13px; color: #666;">粒度</span>
        <a-radio-group v-model:value="granularity" button-style="solid" size="small" @change="loadTimeline">
          <a-radio-button value="hour">小时</a-radio-button>
          <a-radio-button value="day">日</a-radio-button>
          <a-radio-button value="month">月</a-radio-button>
        </a-radio-group>
        <a-button size="small" @click="reloadAll">
          <ReloadOutlined /> 刷新
        </a-button>
      </a-space>
    </a-card>

    <!-- Summary cards -->
    <a-row :gutter="12" class="cards-row">
      <a-col :xs="12" :lg="6">
        <a-card :bordered="false" class="stat-card">
          <a-statistic title="总 Token 量" :value="summary.total_tokens"
            :value-style="{ color: '#4f46e5', fontWeight: 600 }" />
          <div class="stat-sub">输入 {{ fmtNum(summary.prompt_tokens) }} · 输出 {{ fmtNum(summary.completion_tokens) }}</div>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card :bordered="false" class="stat-card">
          <a-statistic title="总费用 ($)" :value="summary.total_cost" :precision="4" />
          <div class="stat-sub">按模型单价（$/1K tokens）自动计算</div>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card :bordered="false" class="stat-card">
          <a-statistic title="模型调用次数" :value="summary.calls" />
          <div class="stat-sub">平均耗时 {{ Math.round(summary.avg_duration_ms || 0) }} ms</div>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card :bordered="false" class="stat-card">
          <a-statistic title="错误率" :value="(summary.error_rate || 0) * 100" :precision="2" suffix="%" />
          <div class="stat-sub">失败 {{ summary.error_calls || 0 }} 次调用</div>
        </a-card>
      </a-col>
    </a-row>

    <!-- Timeline chart -->
    <a-card :bordered="false" title="Token 用量趋势" class="chart-card">
      <template #extra>
        <a-space :size="12" style="font-size: 12px; color: #666;">
          <span><span class="dot" style="background:#4f46e5"></span> 输入 tokens</span>
          <span><span class="dot" style="background:#22c55e"></span> 输出 tokens</span>
        </a-space>
      </template>
      <div ref="timelineChartEl" class="chart-box" />
      <a-empty v-if="!timelineLoading && timeline.length === 0" description="所选时间范围内暂无调用记录" />
    </a-card>

    <a-row :gutter="12">
      <!-- By model -->
      <a-col :xs="24" :lg="14">
        <a-card :bordered="false" title="按模型统计" class="chart-card">
          <a-table :data-source="byModel" :loading="byModelLoading" row-key="_rk" size="small" :pagination="false">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'model'">
                <div style="font-weight: 500;">{{ record.model_name }}</div>
                <div style="font-size: 11px; color: #999;">{{ record.provider_name }} / {{ record.model_type }}</div>
              </template>
              <template v-if="column.key === 'tokens'">
                <div>{{ fmtNum(record.total_tokens) }}</div>
                <div style="font-size: 11px; color: #999;">{{ fmtNum(record.prompt_tokens) }} / {{ fmtNum(record.completion_tokens) }}</div>
              </template>
              <template v-if="column.key === 'cost'">${{ (record.cost || 0).toFixed(4) }}</template>
              <template v-if="column.key === 'calls'">{{ record.calls }}<span v-if="record.error_calls" style="color:#ef4444"> ({{ record.error_calls }} 失败)</span></template>
            </template>
          </a-table>
        </a-card>
      </a-col>

      <!-- Model share pie + by agent -->
      <a-col :xs="24" :lg="10">
        <a-card :bordered="false" title="模型占比" class="chart-card">
          <div ref="pieChartEl" class="chart-box pie" />
        </a-card>
        <a-card :bordered="false" title="按 Agent 统计" class="chart-card">
          <a-table :data-source="byAgent" :loading="byAgentLoading" row-key="_rk" size="small" :pagination="false">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'agent'">{{ record.agent_name }}</template>
              <template v-if="column.key === 'tokens'">{{ fmtNum(record.total_tokens) }}</template>
              <template v-if="column.key === 'cost'">${{ (record.cost || 0).toFixed(4) }}</template>
              <template v-if="column.key === 'calls'">{{ record.calls }}</template>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { usageApi } from '@/api/client'

echarts.use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const rangeKey = ref<'7d' | '30d' | '90d' | 'all'>('30d')
const granularity = ref<'hour' | 'day' | 'month'>('day')

const summary = ref<Record<string, any>>({
  total_tokens: 0, prompt_tokens: 0, completion_tokens: 0,
  total_cost: 0, calls: 0, avg_duration_ms: 0, error_calls: 0, error_rate: 0,
})
const timeline = ref<any[]>([])
const byModel = ref<any[]>([])
const byAgent = ref<any[]>([])
const timelineLoading = ref(false)
const byModelLoading = ref(false)
const byAgentLoading = ref(false)

const timelineChartEl = ref<HTMLElement>()
const pieChartEl = ref<HTMLElement>()
let timelineChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null
let resizeHandler: (() => void) | null = null

const summaryLoading = ref(false)

function windowParams(): { start?: string; end?: string } {
  if (rangeKey.value === 'all') return {}
  const days = { '7d': 7, '30d': 30, '90d': 90 }[rangeKey.value] || 30
  const end = new Date()
  const start = new Date(end.getTime() - days * 86400_000)
  return { start: start.toISOString(), end: end.toISOString() }
}

function fmtNum(n: number | string | undefined): string {
  const v = Number(n || 0)
  return v.toLocaleString('zh-CN')
}

function rangeLabel(): string {
  if (rangeKey.value === 'all') return '全部'
  return { '7d': '近7天', '30d': '近30天', '90d': '近90天' }[rangeKey.value] || ''
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    const res = await usageApi.summary(windowParams())
    summary.value = res.data || {}
  } catch (err: any) {
    message.error('加载汇总失败: ' + (err.response?.data?.detail || err.message))
  } finally { summaryLoading.value = false }
}

async function loadTimeline() {
  timelineLoading.value = true
  try {
    const res = await usageApi.timeline({ ...windowParams(), granularity: granularity.value })
    timeline.value = res.data || []
    renderTimeline()
  } catch (err: any) {
    message.error('加载趋势失败: ' + (err.response?.data?.detail || err.message))
  } finally { timelineLoading.value = false }
}

async function loadByModel() {
  byModelLoading.value = true
  try {
    const res = await usageApi.byModel(windowParams())
    byModel.value = (res.data || []).map((r: any, i: number) => ({ ...r, _rk: r.model_config_id ?? `m${i}` }))
    renderPie()
  } catch (err: any) {
    message.error('加载模型统计失败: ' + (err.response?.data?.detail || err.message))
  } finally { byModelLoading.value = false }
}

async function loadByAgent() {
  byAgentLoading.value = true
  try {
    const res = await usageApi.byAgent(windowParams())
    byAgent.value = (res.data || []).map((r: any, i: number) => ({ ...r, _rk: r.agent_id ?? `a${i}` }))
  } catch (err: any) {
    message.error('加载 Agent 统计失败: ' + (err.response?.data?.detail || err.message))
  } finally { byAgentLoading.value = false }
}

function renderTimeline() {
  if (!timelineChartEl.value) return
  if (!timelineChart) timelineChart = echarts.init(timelineChartEl.value)
  const xs = timeline.value.map(t => {
    const d = new Date(t.bucket)
    if (granularity.value === 'hour') {
      return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:00`
    }
    if (granularity.value === 'month') {
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    }
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
  timelineChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { show: false },
    grid: { left: 56, right: 24, top: 20, bottom: 28 },
    xAxis: { type: 'category', data: xs, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v) } },
    series: [
      { name: '输入 tokens', type: 'line', smooth: true, showSymbol: false, data: timeline.value.map(t => t.prompt_tokens), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#4f46e5', width: 2 }, itemStyle: { color: '#4f46e5' } },
      { name: '输出 tokens', type: 'line', smooth: true, showSymbol: false, data: timeline.value.map(t => t.completion_tokens), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#22c55e', width: 2 }, itemStyle: { color: '#22c55e' } },
    ],
  }, true)
}

function renderPie() {
  if (!pieChartEl.value) return
  if (!pieChart) pieChart = echarts.init(pieChartEl.value)
  const data = byModel.value.map(m => ({ name: m.model_name, value: m.total_tokens }))
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['38%', '66%'], center: ['50%', '44%'],
      label: { formatter: '{d}%', fontSize: 11 },
      data,
    }],
  }, true)
}

function reload() { reloadAll() }
function reloadAll() {
  loadSummary()
  loadTimeline()
  loadByModel()
  loadByAgent()
}

onMounted(async () => {
  reloadAll()
  await nextTick()
  resizeHandler = () => { timelineChart?.resize(); pieChart?.resize() }
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  timelineChart?.dispose()
  pieChart?.dispose()
})
</script>

<style scoped>
.usage-page {
  padding-bottom: 24px;
}
.filter-card {
  margin-bottom: 12px;
}
.cards-row {
  margin-bottom: 12px;
}
.stat-card {
  border-radius: 12px;
}
.stat-sub {
  font-size: 12px; color: #999; margin-top: 4px;
}
.chart-card {
  border-radius: 12px; margin-bottom: 12px;
}
.chart-box {
  height: 300px; width: 100%;
}
.chart-box.pie {
  height: 240px;
}
.dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 4px; vertical-align: middle;
}
</style>
