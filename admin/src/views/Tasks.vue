<template>
  <div>
    <!-- Filter Bar -->
    <a-card style="margin-bottom: 16px;">
      <a-space wrap>
        <a-select v-model:value="filters.status" style="width: 140px" placeholder="状态" allowClear>
          <a-select-option value="">全部状态</a-select-option>
          <a-select-option value="pending">待处理</a-select-option>
          <a-select-option value="assigned">已分配</a-select-option>
          <a-select-option value="resolved">已解决</a-select-option>
          <a-select-option value="closed">已关闭</a-select-option>
        </a-select>
        <a-select v-model:value="filters.priority" style="width: 140px" placeholder="优先级" allowClear>
          <a-select-option value="">全部优先级</a-select-option>
          <a-select-option value="urgent">紧急</a-select-option>
          <a-select-option value="high">高</a-select-option>
          <a-select-option value="normal">普通</a-select-option>
          <a-select-option value="low">低</a-select-option>
        </a-select>
        <a-button type="primary" @click="fetchTasks">查询</a-button>
        <a-button @click="resetFilters">重置</a-button>
      </a-space>
    </a-card>

    <!-- Stats Summary -->
    <a-row :gutter="[16, 16]" style="margin-bottom: 16px;">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="待处理" :value="stats.by_status?.pending || 0" :value-style="{ color: '#cf1322' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="已分配" :value="stats.by_status?.assigned || 0" :value-style="{ color: '#1677ff' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="已解决" :value="stats.by_status?.resolved || 0" :value-style="{ color: '#3f8600' }" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic title="总计" :value="stats.total || 0" :value-style="{ color: '#7c3aed' }" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Task Table -->
    <a-card title="工单列表">
      <a-table :columns="columns" :data-source="tasks" :loading="loading" row-key="id"
        :pagination="pagination" @change="handleTableChange" size="middle">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'ticket_number'">
            <a @click="showDetail(record)">{{ record.ticket_number }}</a>
          </template>
          <template v-if="column.key === 'priority'">
            <a-tag :color="priorityColor(record.priority)">{{ priorityLabel(record.priority) }}</a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button size="small" type="link" @click="showDetail(record)">详情</a-button>
              <a-button v-if="record.status === 'pending'" size="small" type="link" @click="showAssign(record)">分配</a-button>
              <a-button v-if="record.status === 'assigned'" size="small" type="link" @click="showResolve(record)">解决</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Detail Modal -->
    <a-modal v-model:open="detailVisible" title="工单详情" width="640px" :footer="null">
      <a-descriptions v-if="currentTask" :column="2" bordered size="small">
        <a-descriptions-item label="工单号">{{ currentTask.ticket_number }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="statusColor(currentTask.status)">{{ statusLabel(currentTask.status) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="优先级">
          <a-tag :color="priorityColor(currentTask.priority)">{{ priorityLabel(currentTask.priority) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="分配给">{{ currentTask.assigned_to || '未分配' }}</a-descriptions-item>
        <a-descriptions-item label="对话ID">{{ currentTask.conversation_id }}</a-descriptions-item>
        <a-descriptions-item label="意图">{{ currentTask.intent }}</a-descriptions-item>
        <a-descriptions-item label="置信度">{{ currentTask.confidence ? (currentTask.confidence * 100).toFixed(0) + '%' : '-' }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatDate(currentTask.created_at) }}</a-descriptions-item>
        <a-descriptions-item label="转接原因" :span="2">{{ currentTask.transfer_reason }}</a-descriptions-item>
        <a-descriptions-item label="用户消息" :span="2">
          <div style="max-height: 120px; overflow-y: auto; white-space: pre-wrap;">{{ currentTask.user_message }}</div>
        </a-descriptions-item>
        <a-descriptions-item label="AI预答" :span="2">
          <div style="max-height: 120px; overflow-y: auto; white-space: pre-wrap;">{{ currentTask.ai_pre_answer }}</div>
        </a-descriptions-item>
        <a-descriptions-item v-if="currentTask.resolution_note" label="解决记录" :span="2">
          {{ currentTask.resolution_note }}
        </a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <!-- Assign Modal -->
    <a-modal v-model:open="assignVisible" title="分配工单" @ok="doAssign" :confirm-loading="actionLoading">
      <a-form>
        <a-form-item label="分配给">
          <a-input v-model:value="assignForm.assigneeId" placeholder="输入客服ID，如 1001" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Resolve Modal -->
    <a-modal v-model:open="resolveVisible" title="解决工单" @ok="doResolve" :confirm-loading="actionLoading">
      <a-form>
        <a-form-item label="解决类型">
          <a-select v-model:value="resolveForm.resolution_type" style="width: 100%">
            <a-select-option value="resolved">已解决</a-select-option>
            <a-select-option value="cannot_resolve">无法解决</a-select-option>
            <a-select-option value="duplicate">重复工单</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="解决记录">
          <a-textarea v-model:value="resolveForm.resolution_note" :rows="4" placeholder="输入解决说明..." />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { tasksApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const actionLoading = ref(false)
const tasks = ref<any[]>([])
const stats = ref<any>({})
const currentTask = ref<any>(null)

const filters = reactive({ status: '', priority: '' })
const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

const detailVisible = ref(false)
const assignVisible = ref(false)
const resolveVisible = ref(false)
const assignForm = reactive({ assigneeId: '' })
const resolveForm = reactive({ resolution_type: 'resolved', resolution_note: '' })

const columns = [
  { title: '工单号', key: 'ticket_number', width: 160 },
  { title: '转接原因', dataIndex: 'transfer_reason', key: 'transfer_reason', ellipsis: true },
  { title: '优先级', key: 'priority', width: 80 },
  { title: '状态', key: 'status', width: 90 },
  { title: '分配给', dataIndex: 'assigned_to', key: 'assigned_to', width: 100 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 160, fixed: 'right' }
]

function priorityColor(p: string) { return { urgent: 'red', high: 'orange', normal: 'blue', low: 'default' }[p] || 'default' }
function priorityLabel(p: string) { return { urgent: '紧急', high: '高', normal: '普通', low: '低' }[p] || p }
function statusColor(s: string) { return { pending: 'orange', assigned: 'blue', resolved: 'green', closed: 'default' }[s] || 'default' }
function statusLabel(s: string) { return { pending: '待处理', assigned: '已分配', resolved: '已解决', closed: '已关闭' }[s] || s }
function formatDate(d: string) { return d ? dayjs(d).format('YYYY-MM-DD HH:mm:ss') : '-' }

async function fetchTasks() {
  loading.value = true
  try {
    const params: any = { page: pagination.current, page_size: pagination.pageSize }
    if (filters.status) params.status = filters.status
    if (filters.priority) params.priority = filters.priority
    const res = await tasksApi.list(params)
    tasks.value = res.data.tasks || res.data || []
    if (res.data.total !== undefined) pagination.total = res.data.total
  } finally { loading.value = false }
}

async function fetchStats() {
  try { const res = await tasksApi.stats(); stats.value = res.data } catch {}
}

function handleTableChange(pag: any) {
  pagination.current = pag.current; pagination.pageSize = pag.pageSize
  fetchTasks()
}

function resetFilters() { filters.status = ''; filters.priority = ''; pagination.current = 1; fetchTasks() }

function showDetail(task: any) { currentTask.value = task; detailVisible.value = true }
function showAssign(task: any) { currentTask.value = task; assignForm.assigneeId = ''; assignVisible.value = true }
function showResolve(task: any) { currentTask.value = task; resolveForm.resolution_note = ''; resolveForm.resolution_type = 'resolved'; resolveVisible.value = true }

async function doAssign() {
  if (!assignForm.assigneeId) { message.warning('请输入客服ID'); return }
  actionLoading.value = true
  try {
    await tasksApi.assign(currentTask.value.id, assignForm.assigneeId)
    message.success('分配成功')
    assignVisible.value = false
    fetchTasks(); fetchStats()
  } finally { actionLoading.value = false }
}

async function doResolve() {
  if (!resolveForm.resolution_note) { message.warning('请输入解决记录'); return }
  actionLoading.value = true
  try {
    await tasksApi.resolve(currentTask.value.id, { resolution_note: resolveForm.resolution_note, resolution_type: resolveForm.resolution_type })
    message.success('工单已解决')
    resolveVisible.value = false
    fetchTasks(); fetchStats()
  } finally { actionLoading.value = false }
}

onMounted(() => { fetchTasks(); fetchStats() })
</script>
