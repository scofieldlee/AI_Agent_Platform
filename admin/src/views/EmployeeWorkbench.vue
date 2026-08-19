<template>
  <div class="workbench-page">
    <a-row :gutter="16" class="workbench-layout">
      <!-- Left: employee select + task history -->
      <a-col :span="7">
        <a-card title="AI 员工" size="small">
          <a-select
            v-model:value="selectedEmployeeId"
            style="width: 100%;"
            placeholder="选择 AI 员工"
            :options="employeeOptions"
            show-search
            option-filter-prop="label"
            @change="loadTasks"
          />
        </a-card>

        <a-card title="历史任务" size="small" style="margin-top: 16px;">
          <a-spin :spinning="tasksLoading">
            <div v-if="tasks.length === 0" class="empty-hint">暂无任务</div>
            <div
              v-for="t in tasks"
              :key="t.id"
              class="task-item"
              :class="{ active: t.id === currentTask?.id }"
              @click="selectTask(t.id)"
            >
              <div class="task-item-head">
                <a-badge :status="taskBadge(t.status)" />
                <span class="task-item-title">#{{ t.id }} {{ t.title || '未命名任务' }}</span>
              </div>
              <div class="task-item-meta">
                <span>{{ t.employee_name }}</span>
                <span>{{ t.step_count ? `${t.completed_steps}/${t.step_count} 步` : '' }}</span>
              </div>
            </div>
          </a-spin>
        </a-card>
      </a-col>

      <!-- Right: input + steps + result -->
      <a-col :span="17">
        <!-- Task input -->
        <a-card size="small">
          <template #title>任务输入</template>
          <a-textarea
            v-model:value="taskMessage"
            :rows="3"
            placeholder="描述你要完成的工作，例如：为新款无人机生成亚马逊 Listing 文案…"
            :disabled="!selectedEmployee"
          />
          <div style="margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px;">
            <a-button
              v-if="currentTask && ['pending', 'running'].includes(currentTask.status)"
              danger
              @click="handleCancel"
            >取消任务</a-button>
            <a-button
              type="primary"
              :loading="executing"
              :disabled="!selectedEmployee || !taskMessage.trim()"
              @click="handleExecute"
            >
              <PlayCircleOutlined /> 开始工作
            </a-button>
          </div>
        </a-card>

        <!-- Execution steps -->
        <a-card v-if="currentTask" size="small" style="margin-top: 16px;">
          <template #title>
            执行过程
            <a-tag style="margin-left: 8px;" :color="taskStatusColor(currentTask.status)">
              {{ taskStatusLabel(currentTask.status) }}
            </a-tag>
            <a-spin v-if="isRunning" :size="'small'" style="margin-left: 8px;" />
          </template>

          <!-- Supervisor decision log -->
          <div v-if="decisions.length" class="decision-log">
            <div v-for="(d, i) in decisions" :key="i" class="decision-item">
              <a-tag :color="decisionColor(d.action)">{{ decisionLabel(d.action) }}</a-tag>
              <span v-if="d.round" class="decision-round">R{{ d.round }}</span>
              <span class="decision-reason">{{ d.reason || '' }}</span>
            </div>
          </div>

          <!-- Steps timeline -->
          <a-timeline style="margin-top: 16px;">
            <a-timeline-item
              v-for="s in currentTask.steps"
              :key="s.id"
              :color="stepColor(s.status)"
            >
              <div class="step-row" @click="openStepDetail(s)">
                <span class="step-icon">{{ stepIcon(s.status) }}</span>
                <span class="step-name">{{ s.agent_name || `Agent#${s.agent_id}` }}</span>
                <a-tag v-if="s.role" style="margin-left: 6px;">{{ s.role }}</a-tag>
                <span class="step-status" :style="{ color: stepStatusColor(s.status) }">
                  {{ stepStatusLabel(s.status) }}
                </span>
                <span v-if="stepDuration(s)" class="step-duration">{{ stepDuration(s) }}</span>
                <span v-if="s.trace_id" class="step-trace" @click.stop="goTrace(s.trace_id)">
                  trace ↗
                </span>
              </div>
              <div v-if="s.error" class="step-error">{{ s.error.message || s.error.code }}</div>
            </a-timeline-item>
          </a-timeline>

          <!-- waiting_human -->
          <a-alert
            v-if="currentTask.status === 'waiting_human'"
            type="warning"
            show-icon
            style="margin-top: 8px;"
          >
            <template #message>需要人工介入</template>
            <template #description>
              <div style="margin-bottom: 12px;">{{ humanReason }}</div>
              <a-space>
                <a-textarea
                  v-model:value="humanFeedback"
                  :rows="2"
                  placeholder="填写人工处理结果（将注入任务上下文，供 AI 员工继续决策）"
                  style="width: 420px;"
                />
                <a-button type="primary" :loading="resuming" @click="handleResume">
                  继续执行
                </a-button>
              </a-space>
            </template>
          </a-alert>

          <!-- Result -->
          <div v-if="resultSummary" class="result-section">
            <a-divider>最终结果</a-divider>
            <div class="result-summary">{{ resultSummary }}</div>
            <div v-if="currentTask.result?.partial" style="margin-top: 8px;">
              <a-tag color="orange">部分完成（有步骤被跳过）</a-tag>
            </div>
          </div>
        </a-card>

        <a-empty v-else style="margin-top: 60px;" description="选择 AI 员工并提交任务" />
      </a-col>
    </a-row>

    <!-- Step detail modal -->
    <a-modal
      v-model:open="stepDetailVisible"
      :title="stepDetail ? `${stepDetail.agent_name} — 步骤详情` : '步骤详情'"
      :footer="null"
      width="680"
    >
      <div v-if="stepDetail">
        <h4>输入指令</h4>
        <pre class="detail-block">{{ stepDetail.input?.instruction || '（无）' }}</pre>
        <h4>输出</h4>
        <pre class="detail-block">{{ stepOutput }}</pre>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import { employeeApi } from '@/api/client'

const route = useRoute()
const router = useRouter()

// --- State ---
const employees = ref<any[]>([])
const selectedEmployeeId = ref<number | null>(null)
const tasks = ref<any[]>([])
const tasksLoading = ref(false)
const currentTask = ref<any>(null)
const taskMessage = ref('')
const executing = ref(false)
const resuming = ref(false)
const humanFeedback = ref('')
const stepDetailVisible = ref(false)
const stepDetail = ref<any>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

const selectedEmployee = computed(() =>
  employees.value.find((e) => e.id === selectedEmployeeId.value)
)

const employeeOptions = computed(() =>
  employees.value
    .filter((e) => e.status === 'published')
    .map((e) => ({ value: e.id, label: `${e.name}（${e.orchestration_mode === 'supervisor' ? 'Supervisor' : 'DAG'}）` }))
)

const isRunning = computed(() =>
  currentTask.value && ['pending', 'running'].includes(currentTask.value.status)
)

const decisions = computed(() =>
  currentTask.value?.context?.decisions || []
)

const resultSummary = computed(() => {
  const r = currentTask.value?.result
  if (!r) return ''
  if (currentTask.value.status === 'completed') return r.summary || ''
  return ''
})

const humanReason = computed(() =>
  currentTask.value?.error?.reason || currentTask.value?.error?.message || '（未提供原因）'
)

const stepOutput = computed(() => {
  const out = stepDetail.value?.output
  if (!out) return '（无输出）'
  return out.summary || JSON.stringify(out, null, 2)
})

// --- Loaders ---
async function loadEmployees() {
  try {
    const res = await employeeApi.list()
    employees.value = res.data
    // Preselect from query param
    const qid = Number(route.query.employee_id)
    if (qid && employees.value.some((e) => e.id === qid)) {
      selectedEmployeeId.value = qid
      await loadTasks()
    }
  } catch {
    // handled
  }
}

async function loadTasks() {
  if (!selectedEmployeeId.value) return
  tasksLoading.value = true
  try {
    const res = await employeeApi.tasks({
      employee_id: selectedEmployeeId.value, limit: 30
    })
    tasks.value = res.data
  } catch {
    // handled
  } finally {
    tasksLoading.value = false
  }
}

function selectTask(taskId: number) {
  humanFeedback.value = ''
  fetchTaskDetail(taskId)
}

async function fetchTaskDetail(taskId: number) {
  try {
    const res = await employeeApi.taskDetail(taskId)
    currentTask.value = res.data
    schedulePolling()
  } catch {
    // handled
  }
}

// --- Polling (2s, pause when tab hidden) ---
function schedulePolling() {
  stopPolling()
  if (!currentTask.value) return
  if (['pending', 'running'].includes(currentTask.value.status)) {
    pollTimer = setInterval(async () => {
      if (document.hidden || !currentTask.value) return
      if (!['pending', 'running'].includes(currentTask.value.status)) {
        stopPolling()
        return
      }
      try {
        const res = await employeeApi.taskDetail(currentTask.value.id)
        currentTask.value = res.data
        if (!['pending', 'running'].includes(res.data.status)) {
          stopPolling()
          await loadTasks()
        }
      } catch {
        // ignore transient polling errors
      }
    }, 2000)
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// --- Actions ---
async function handleExecute() {
  if (!selectedEmployeeId.value || !taskMessage.value.trim()) return
  executing.value = true
  try {
    const res = await employeeApi.execute(selectedEmployeeId.value, {
      input: { message: taskMessage.value.trim() },
      title: taskMessage.value.trim().slice(0, 30)
    })
    message.success(`任务 #${res.data.task_id} 已提交`)
    taskMessage.value = ''
    await loadTasks()
    await fetchTaskDetail(res.data.task_id)
  } catch {
    // handled
  } finally {
    executing.value = false
  }
}

async function handleCancel() {
  if (!currentTask.value) return
  try {
    await employeeApi.cancelTask(currentTask.value.id)
    message.success('已取消')
    await fetchTaskDetail(currentTask.value.id)
    await loadTasks()
  } catch {
    // handled
  }
}

async function handleResume() {
  if (!currentTask.value) return
  resuming.value = true
  try {
    await employeeApi.resumeTask(
      currentTask.value.id,
      humanFeedback.value.trim() ? { human_feedback: humanFeedback.value.trim() } : undefined
    )
    message.success('已恢复执行')
    humanFeedback.value = ''
    await fetchTaskDetail(currentTask.value.id)
  } catch {
    // handled
  } finally {
    resuming.value = false
  }
}

function openStepDetail(s: any) {
  stepDetail.value = s
  stepDetailVisible.value = true
}

function goTrace(traceId: string) {
  router.push({ path: '/analytics', query: { trace_id: traceId } })
}

// --- Display helpers ---
function taskBadge(s: string): string {
  return ({
    pending: 'default', running: 'processing', completed: 'success',
    failed: 'error', cancelled: 'default', waiting_human: 'warning'
  } as Record<string, string>)[s] || 'default'
}
function taskStatusColor(s: string): string {
  return ({
    pending: 'default', running: 'processing', completed: 'success',
    failed: 'error', cancelled: 'default', waiting_human: 'warning'
  } as Record<string, string>)[s] || 'default'
}
function taskStatusLabel(s: string): string {
  return ({
    pending: '排队中', running: '执行中', completed: '已完成',
    failed: '失败', cancelled: '已取消', waiting_human: '等待人工'
  } as Record<string, string>)[s] || s
}
function stepColor(s: string): string {
  return ({
    pending: 'gray', running: 'blue', completed: 'green',
    failed: 'red', cancelled: 'gray', skipped: 'gray'
  } as Record<string, string>)[s] || 'gray'
}
function stepIcon(s: string): string {
  return ({
    pending: '○', running: '●', completed: '✓',
    failed: '✗', cancelled: '⊘', skipped: '⊘'
  } as Record<string, string>)[s] || '○'
}
function stepStatusLabel(s: string): string {
  return ({
    pending: '等待中', running: '执行中…', completed: '完成',
    failed: '失败', cancelled: '已取消', skipped: '已跳过'
  } as Record<string, string>)[s] || s
}
function stepStatusColor(s: string): string {
  return ({
    pending: '#999', running: '#1677ff', completed: '#52c41a',
    failed: '#ff4d4f', cancelled: '#999', skipped: '#999'
  } as Record<string, string>)[s] || '#999'
}
function stepDuration(s: any): string {
  if (!s.started_at || !s.completed_at) return ''
  const ms = new Date(s.completed_at).getTime() - new Date(s.started_at).getTime()
  if (isNaN(ms) || ms < 0) return ''
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}
function decisionColor(a: string): string {
  return ({
    dispatch_agent: 'blue', dispatch_parallel: 'geekblue',
    finish: 'green', human_intervention: 'orange', human_resolved: 'purple'
  } as Record<string, string>)[a] || 'default'
}
function decisionLabel(a: string): string {
  return ({
    dispatch_agent: '派发 Agent', dispatch_parallel: '并行派发',
    finish: '任务完成', human_intervention: '请求人工介入',
    human_resolved: '人工已处理'
  } as Record<string, string>)[a] || a
}

// --- Lifecycle ---
onMounted(loadEmployees)
onUnmounted(stopPolling)
</script>

<style scoped>
.workbench-page {
  min-height: 100%;
}

.workbench-layout {
  min-height: calc(100vh - 140px);
}

.empty-hint {
  color: #999;
  text-align: center;
  padding: 24px 0;
}

.task-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 6px;
  border: 1px solid transparent;
}

.task-item:hover {
  background: rgba(128, 128, 128, 0.08);
}

.task-item.active {
  border-color: #7c3aed;
  background: rgba(124, 58, 237, 0.06);
}

.task-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-item-title {
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
  padding-left: 22px;
}

.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-wrap: wrap;
}

.step-name {
  font-weight: 500;
}

.step-duration {
  font-size: 12px;
  color: #999;
}

.step-trace {
  font-size: 12px;
  color: #1677ff;
  cursor: pointer;
}

.step-error {
  font-size: 12px;
  color: #ff4d4f;
  margin-top: 4px;
}

.decision-log {
  background: rgba(128, 128, 128, 0.06);
  border-radius: 8px;
  padding: 10px 12px;
}

.decision-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
}

.decision-item:last-child {
  margin-bottom: 0;
}

.decision-round {
  color: #999;
  flex-shrink: 0;
}

.decision-reason {
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-section {
  margin-top: 8px;
}

.result-summary {
  white-space: pre-wrap;
  line-height: 1.7;
  background: rgba(82, 196, 26, 0.06);
  border: 1px solid rgba(82, 196, 26, 0.25);
  border-radius: 8px;
  padding: 16px;
}

.detail-block {
  background: rgba(128, 128, 128, 0.08);
  border-radius: 8px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  max-height: 320px;
  overflow: auto;
}
</style>
