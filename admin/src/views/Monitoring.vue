<template>
  <div class="monitoring-page">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 style="margin: 0; font-size: 20px;">系统监控</h2>
        <span class="sub-text">
          实时平台健康状态与运行指标
          <template v-if="lastUpdate"> · 更新于 {{ lastUpdate }}</template>
        </span>
      </div>
      <a-space>
        <a-switch v-model:checked="autoRefresh" checked-children="自动" un-checked-children="手动" @change="toggleAutoRefresh" />
        <a-button @click="loadData" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <!-- ===== Service Status Cards ===== -->
      <a-row :gutter="16" style="margin-bottom: 16px;">
        <a-col v-for="svc in serviceCards" :key="svc.name" :xs="24" :sm="12" :lg="6">
          <div class="service-card" :class="svc.statusClass">
            <div class="service-card-inner">
              <div class="service-icon" :class="svc.statusClass">
                <component :is="svc.icon" />
              </div>
              <div class="service-info">
                <div class="service-name">{{ svc.name }}</div>
                <div class="service-latency">{{ svc.latency }}</div>
              </div>
              <div class="service-badge" :class="svc.statusClass">
                {{ svc.statusText }}
              </div>
            </div>
          </div>
        </a-col>
      </a-row>

      <!-- ===== System Resources (Gauges) ===== -->
      <a-row :gutter="16" style="margin-bottom: 16px;">
        <a-col :xs="24" :sm="8">
          <div class="metric-card">
            <div class="metric-title">CPU</div>
            <SvgGauge :value="systemData?.cpu?.percent || 0" label="CPU" />
            <div class="metric-details">
              <span>{{ systemData?.cpu?.logical_cores || 0 }} 逻辑核</span>
              <span>负载 {{ systemData?.cpu?.load_avg_1m?.toFixed(2) || 'N/A' }}</span>
            </div>
          </div>
        </a-col>
        <a-col :xs="24" :sm="8">
          <div class="metric-card">
            <div class="metric-title">内存</div>
            <SvgGauge :value="systemData?.memory?.percent || 0" label="内存" />
            <div class="metric-details">
              <span>{{ formatMB(systemData?.memory?.used_mb) }} / {{ formatMB(systemData?.memory?.total_mb) }}</span>
              <span>Swap {{ systemData?.swap?.percent || 0 }}%</span>
            </div>
          </div>
        </a-col>
        <a-col :xs="24" :sm="8">
          <div class="metric-card">
            <div class="metric-title">磁盘</div>
            <SvgGauge :value="systemData?.disk?.percent || 0" label="磁盘" />
            <div class="metric-details">
              <span>{{ systemData?.disk?.used_gb || 0 }} / {{ systemData?.disk?.total_gb || 0 }} GB</span>
              <span>可用 {{ systemData?.disk?.free_gb || 0 }} GB</span>
            </div>
          </div>
        </a-col>
      </a-row>

      <!-- ===== Agent Runtime + Node Performance ===== -->
      <a-row :gutter="16" style="margin-bottom: 16px;">
        <a-col :xs="24" :lg="12">
          <div class="metric-card">
            <div class="metric-title">Agent 运行时</div>
            <a-row :gutter="16" style="margin-bottom: 16px;">
              <a-col :span="6"><a-statistic title="总 Trace" :value="agentStats?.traces?.total || 0" /></a-col>
              <a-col :span="6"><a-statistic title="成功率" :value="agentStats?.traces?.success_rate || 0" suffix="%" :value-style="{ color: '#52c41a' }" /></a-col>
              <a-col :span="6"><a-statistic title="平均耗时" :value="agentStats?.traces?.avg_duration_ms || 0" suffix="ms" /></a-col>
              <a-col :span="6"><a-statistic title="转人工" :value="agentStats?.traces?.human_transfer || 0" :value-style="{ color: '#faad14' }" /></a-col>
            </a-row>
            <div class="chart-label">意图分布</div>
            <SvgDonut :data="intentChartData" :height="200" />
          </div>
        </a-col>
        <a-col :xs="24" :lg="12">
          <div class="metric-card">
            <div class="metric-title">节点性能</div>
            <a-row :gutter="16" style="margin-bottom: 16px;">
              <a-col :span="6"><a-statistic title="总调用" :value="llmStats?.total_calls || 0" /></a-col>
              <a-col :span="6"><a-statistic title="总 Tokens" :value="llmStats?.total_tokens || 0" /></a-col>
              <a-col :span="6"><a-statistic title="平均延迟" :value="llmStats?.avg_latency_ms || 0" suffix="ms" /></a-col>
              <a-col :span="6"><a-statistic title="错误率" :value="llmStats?.error_rate || 0" suffix="%" :value-style="{ color: (llmStats?.error_rate || 0) > 0 ? '#ff4d4f' : '#52c41a' }" /></a-col>
            </a-row>
            <div class="chart-label">各节点平均耗时</div>
            <SvgBars :data="nodePerfData" :height="200" />
          </div>
        </a-col>
      </a-row>

      <!-- ===== Database + Redis ===== -->
      <a-row :gutter="16" style="margin-bottom: 16px;">
        <a-col :xs="24" :lg="14">
          <div class="metric-card">
            <div class="metric-title" style="display: flex; justify-content: space-between; align-items: center;">
              <span>数据库</span>
              <a-tag color="blue">{{ dbStats?.database_size || 'N/A' }}</a-tag>
            </div>
            <a-descriptions :column="3" size="small" style="margin-bottom: 16px;">
              <a-descriptions-item label="连接池">{{ dbStats?.pool?.checked_out || 0 }} / {{ (dbStats?.pool?.pool_size || 0) + Math.max(dbStats?.pool?.overflow || 0, 0) }}</a-descriptions-item>
              <a-descriptions-item label="活跃连接">{{ dbStats?.connections?.active || 0 }}</a-descriptions-item>
              <a-descriptions-item label="空闲连接">{{ dbStats?.connections?.idle || 0 }}</a-descriptions-item>
            </a-descriptions>
            <a-table
              :dataSource="dbStats?.tables || []"
              :columns="tableColumns"
              :pagination="{ pageSize: 8, size: 'small' }"
              size="small"
              :rowKey="(r: any) => r.table"
            />
          </div>
        </a-col>
        <a-col :xs="24" :lg="10">
          <div class="metric-card">
            <div class="metric-title" style="display: flex; justify-content: space-between; align-items: center;">
              <span>Redis</span>
              <a-tag :color="redisStats?.status === 'healthy' ? 'green' : 'red'">
                {{ redisStats?.status === 'healthy' ? '健康' : '异常' }}
              </a-tag>
            </div>
            <a-descriptions :column="2" size="small">
              <a-descriptions-item label="版本">{{ redisStats?.version || 'N/A' }}</a-descriptions-item>
              <a-descriptions-item label="模式">{{ redisStats?.mode || 'N/A' }}</a-descriptions-item>
              <a-descriptions-item label="内存">{{ redisStats?.used_memory_mb || 0 }} MB</a-descriptions-item>
              <a-descriptions-item label="峰值">{{ redisStats?.used_memory_peak_mb || 0 }} MB</a-descriptions-item>
              <a-descriptions-item label="Key 数量">{{ redisStats?.total_keys || 0 }}</a-descriptions-item>
              <a-descriptions-item label="客户端">{{ redisStats?.connected_clients || 0 }}</a-descriptions-item>
              <a-descriptions-item label="命中率">{{ redisStats?.hit_rate || 0 }}%</a-descriptions-item>
              <a-descriptions-item label="OPS/sec">{{ redisStats?.ops_per_sec || 0 }}</a-descriptions-item>
            </a-descriptions>
          </div>
        </a-col>
      </a-row>

      <!-- ===== Process Info ===== -->
      <div class="metric-card" v-if="systemData?.process">
        <div class="metric-title">进程信息</div>
        <a-descriptions :column="4" size="small">
          <a-descriptions-item label="PID">{{ systemData.process.pid }}</a-descriptions-item>
          <a-descriptions-item label="RSS 内存">{{ systemData.process.rss_mb }} MB</a-descriptions-item>
          <a-descriptions-item label="CPU">{{ systemData.process.cpu_percent }}%</a-descriptions-item>
          <a-descriptions-item label="线程数">{{ systemData.process.threads }}</a-descriptions-item>
          <a-descriptions-item label="系统运行时间">{{ formatUptime(systemData.uptime_seconds) }}</a-descriptions-item>
          <a-descriptions-item label="进程启动">{{ formatTime(systemData.process.create_time) }}</a-descriptions-item>
        </a-descriptions>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, shallowRef, h } from 'vue'
import { ReloadOutlined, ApiOutlined, DatabaseOutlined, CloudServerOutlined, RobotOutlined } from '@ant-design/icons-vue'
import { monitoringApi } from '@/api/client'
import SvgGauge from '@/components/charts/SvgGauge.vue'
import SvgDonut from '@/components/charts/SvgDonut.vue'
import SvgBars from '@/components/charts/SvgBars.vue'

// ── State ──
const loading = ref(false)
const autoRefresh = ref(true)
const lastUpdate = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const overviewData = shallowRef<any>(null)
const systemData = computed(() => overviewData.value?.system)
const dbStats = computed(() => overviewData.value?.database)
const redisStats = computed(() => overviewData.value?.redis)
const llmStats = computed(() => overviewData.value?.llm)
const agentStats = computed(() => overviewData.value?.agents)

// ── Service Cards ──
const serviceCards = computed(() => {
  const h = overviewData.value?.services || {}
  const items = [
    { key: 'fastapi', name: 'FastAPI', icon: ApiOutlined, data: h.fastapi },
    { key: 'postgresql', name: 'PostgreSQL', icon: DatabaseOutlined, data: h.postgresql },
    { key: 'redis', name: 'Redis', icon: CloudServerOutlined, data: h.redis },
    { key: 'embedding', name: 'Embedding', icon: RobotOutlined, data: h.embedding },
  ]
  return items.map(item => {
    const isHealthy = item.data?.status === 'healthy'
    return {
      name: item.name,
      icon: item.icon,
      statusClass: isHealthy ? 'healthy' : 'unhealthy',
      statusText: isHealthy ? '健康' : '异常',
      latency: item.data?.latency_ms != null ? `${item.data.latency_ms} ms` : (item.data?.error?.slice(0, 30) || 'N/A'),
    }
  })
})

// ── Chart Data ──
const intentColorMap: Record<string, string> = {
  product_info: '#5b8def', product_compare: '#36cfc9', purchase_advice: '#73d13d',
  order_query: '#ffc53d', after_sale: '#ff9c6e', complaint: '#ff4d4f',
  greeting: '#b37feb', unknown: '#bfbfbf',
}

const intentChartData = computed(() => {
  const dist = agentStats.value?.intent_distribution || []
  return dist.map((item: any) => ({
    label: item.intent,
    value: item.count,
    color: intentColorMap[item.intent] || '#888',
  }))
})

const nodeColorMap: Record<string, string> = {
  intent: '#5b8def', knowledge: '#36cfc9', memory: '#73d13d',
  tool: '#ffc53d', llm: '#ff9c6e', human: '#ff4d4f',
}

const nodePerfData = computed(() => {
  const perf = agentStats.value?.node_performance || []
  return perf.map((p: any) => ({
    label: p.node,
    value: p.avg_ms || 0,
    color: nodeColorMap[p.node] || '#888',
  }))
})

// ── Table Columns ──
const tableColumns = [
  { title: '表名', dataIndex: 'table', key: 'table', ellipsis: true, width: 200 },
  { title: '大小', dataIndex: 'size', key: 'size', width: 100 },
  { title: '行数', dataIndex: 'rows', key: 'rows', width: 100, sorter: (a: any, b: any) => a.rows - b.rows },
]

// ── Helpers ──
function formatMB(val?: number): string { return val ? `${val} MB` : 'N/A' }
function formatUptime(seconds: number): string {
  if (!seconds) return 'N/A'
  const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}天 ${h}小时`
  if (h > 0) return `${h}小时 ${m}分钟`
  return `${m}分钟`
}
function formatTime(iso: string): string { return iso ? new Date(iso).toLocaleString('zh-CN') : 'N/A' }

// ── Data Loading ──
async function loadData() {
  loading.value = true
  try {
    const resp = await monitoringApi.overview()
    overviewData.value = resp.data
    lastUpdate.value = new Date().toLocaleTimeString('zh-CN')
  } catch (e: any) {
    console.error('Failed to load monitoring data:', e)
  } finally {
    loading.value = false
  }
}

function toggleAutoRefresh(checked: boolean) {
  if (checked) startTimer()
  else stopTimer()
}
function startTimer() { stopTimer(); timer = setInterval(loadData, 15000) }
function stopTimer() { if (timer) { clearInterval(timer); timer = null } }

onMounted(() => { loadData(); if (autoRefresh.value) startTimer() })
onUnmounted(() => stopTimer())
</script>

<style scoped>
.monitoring-page { padding: 4px; }
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 24px;
}
.sub-text { color: var(--text-color-secondary); font-size: 13px; }

/* Service cards */
.service-card {
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 8px;
  transition: all 0.3s;
  background: var(--card-bg, #fff);
  border: 1px solid var(--card-border, #f0f0f0);
}
.service-card.healthy { border-left: 3px solid #52c41a; }
.service-card.unhealthy { border-left: 3px solid #ff4d4f; }
.service-card-inner { display: flex; align-items: center; gap: 12px; }
.service-icon {
  width: 40px; height: 40px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.service-icon.healthy { background: rgba(82, 196, 26, 0.12); color: #52c41a; }
.service-icon.unhealthy { background: rgba(255, 77, 79, 0.12); color: #ff4d4f; }
.service-info { flex: 1; }
.service-name { font-size: 16px; font-weight: 600; }
.service-latency { font-size: 12px; color: var(--text-color-secondary); }
.service-badge {
  padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500;
}
.service-badge.healthy { background: rgba(82, 196, 26, 0.1); color: #52c41a; }
.service-badge.unhealthy { background: rgba(255, 77, 79, 0.1); color: #ff4d4f; }

/* Metric cards */
.metric-card {
  border-radius: 10px; padding: 20px;
  background: var(--card-bg, #fff);
  border: 1px solid var(--card-border, #f0f0f0);
  margin-bottom: 8px;
}
.metric-title { font-size: 15px; font-weight: 600; margin-bottom: 16px; }
.metric-details {
  display: flex; justify-content: space-between;
  font-size: 12px; color: var(--text-color-secondary);
  margin-top: 8px; padding: 0 12px;
}
.chart-label { font-size: 13px; font-weight: 500; margin-bottom: 8px; color: var(--text-color-secondary); }

:deep(.ant-statistic-title) { font-size: 12px; }
:deep(.ant-statistic-content) { font-size: 20px; }
</style>
