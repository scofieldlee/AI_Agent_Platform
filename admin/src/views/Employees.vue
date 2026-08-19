<template>
  <div class="employees-page">
    <!-- Employee List -->
    <a-card title="AI 员工列表">
      <template #extra>
        <a-space>
          <a-input-search
            v-model:value="keyword"
            placeholder="搜索名称 / Code"
            style="width: 200px"
            allow-clear
            @search="loadEmployees"
          />
          <a-tag color="purple">{{ employees.length }} 个 AI 员工</a-tag>
          <a-button type="primary" size="small" @click="openCreateModal">
            <PlusOutlined /> 新建 AI 员工
          </a-button>
        </a-space>
      </template>
      <a-table
        :columns="columns"
        :data-source="filteredEmployees"
        :loading="loading"
        row-key="id"
        :pagination="false"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-space>
              <a-avatar :size="36" style="background-color: #7c3aed;">{{ record.name?.charAt(0) }}</a-avatar>
              <div>
                <div style="font-weight: 600;">{{ record.name }}</div>
                <div style="font-size: 12px; color: #999;">{{ record.code }}</div>
              </div>
            </a-space>
          </template>
          <template v-if="column.key === 'mode'">
            <a-tag :color="record.orchestration_mode === 'supervisor' ? 'geekblue' : 'cyan'">
              {{ record.orchestration_mode === 'supervisor' ? 'Supervisor' : 'DAG' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'supervisor'">
            <a-tag v-if="record.supervisor_agent_id" color="purple">{{ supervisorName(record) }}</a-tag>
            <span v-else style="font-size: 12px; color: #999;">—</span>
          </template>
          <template v-if="column.key === 'status'">
            <a-badge
              :status="statusBadge(record.status)"
              :text="statusLabel(record.status)"
            />
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openWorkbench(record)">
                <PlayCircleOutlined /> 工作台
              </a-button>
              <a-button type="link" size="small" @click="openConfigDrawer(record)">
                <EditOutlined /> 配置
              </a-button>
              <a-popconfirm
                v-if="record.status !== 'published'"
                title="确定要删除这个 AI 员工吗？（绑定关系将一并删除）"
                ok-text="删除"
                cancel-text="取消"
                ok-type="danger"
                @confirm="handleDelete(record)"
              >
                <a-button type="link" size="small" danger>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-popconfirm>
              <a-tooltip v-else title="已发布的 AI 员工不能删除，请先禁用">
                <a-button type="link" size="small" danger disabled>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Create Modal -->
    <a-modal
      v-model:open="createVisible"
      title="新建 AI 员工"
      :confirm-loading="creating"
      ok-text="创建"
      cancel-text="取消"
      @ok="handleCreate"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="名称" required>
          <a-input v-model:value="createForm.name" placeholder="如：Amazon 运营专员" />
        </a-form-item>
        <a-form-item label="Code（唯一标识）" required>
          <a-input v-model:value="createForm.code" placeholder="如：amazon_ops" />
        </a-form-item>
        <a-form-item label="业务角色">
          <a-input v-model:value="createForm.role" placeholder="如：电商运营" />
        </a-form-item>
        <a-form-item label="协同模式">
          <a-radio-group v-model:value="createForm.orchestration_mode">
            <a-radio value="dag">DAG（静态依赖编排）</a-radio>
            <a-radio value="supervisor">Supervisor（动态决策编排）</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Config Drawer -->
    <a-drawer
      v-model:open="drawerVisible"
      :title="editing ? `${editing.name} — 配置编辑` : 'AI 员工配置'"
      placement="right"
      width="720"
      :destroy-on-close="true"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="detail" class="config-form">
          <!-- Basic Info -->
          <div class="config-section">
            <div class="section-title"><InfoCircleOutlined /> 基本信息</div>
            <a-form layout="vertical">
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="名称">
                    <a-input v-model:value="form.name" :disabled="detail.status === 'published'" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="业务角色">
                    <a-input v-model:value="form.role" :disabled="detail.status === 'published'" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="描述">
                <a-textarea v-model:value="form.description" :rows="2" :disabled="detail.status === 'published'" />
              </a-form-item>
              <a-form-item label="工作目标">
                <a-input v-model:value="form.goal" placeholder="这个 AI 员工要达成什么目标" :disabled="detail.status === 'published'" />
              </a-form-item>
              <a-form-item label="Role Prompt（Supervisor 决策职责描述）">
                <a-textarea
                  v-model:value="form.role_prompt"
                  :rows="4"
                  placeholder="描述该 AI 员工的职责与调度策略，Supervisor 模式下会注入决策 Prompt"
                  :disabled="detail.status === 'published'"
                />
              </a-form-item>
            </a-form>
          </div>

          <!-- Orchestration -->
          <div class="config-section">
            <div class="section-title"><ApartmentOutlined /> 协同配置</div>
            <a-form layout="vertical">
              <a-form-item label="编排模式">
                <a-radio-group v-model:value="form.orchestration_mode" :disabled="detail.status === 'published'">
                  <a-radio value="dag">DAG — 按依赖关系静态执行</a-radio>
                  <a-radio value="supervisor">Supervisor — 由主管 Agent 动态决策</a-radio>
                </a-radio-group>
              </a-form-item>
              <a-form-item
                v-if="form.orchestration_mode === 'supervisor'"
                label="Supervisor Agent（调度大脑）"
                :validate-status="supervisorMissing ? 'error' : ''"
                :help="supervisorMissing ? 'Supervisor 模式必须选择一个主管 Agent' : ''"
              >
                <a-select
                  v-model:value="form.supervisor_agent_id"
                  placeholder="选择已发布的主管 Agent"
                  show-search
                  option-filter-prop="label"
                  :options="selectableOptions"
                  :disabled="detail.status === 'published'"
                  style="width: 100%;"
                />
              </a-form-item>
            </a-form>
          </div>

          <!-- Agent Team -->
          <div class="config-section">
            <div class="section-title"><TeamOutlined /> Agent 团队（{{ teamRows.length }}）</div>
            <a-alert
              v-if="cycleError"
              type="error"
              :message="cycleError"
              show-icon
              style="margin-bottom: 12px;"
            />
            <a-table
              :columns="teamColumns"
              :data-source="teamRows"
              :pagination="false"
              size="small"
              row-key="agent_id"
            >
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'agent'">
                  <div style="font-weight: 500;">{{ agentNameOf(record.agent_id) }}</div>
                  <div style="font-size: 12px; color: #999;">ID: {{ record.agent_id }}</div>
                </template>
                <template v-if="column.key === 'role'">
                  <a-input v-model:value="record.role" size="small" placeholder="角色" style="width: 120px;" :disabled="detail.status === 'published'" />
                </template>
                <template v-if="column.key === 'priority'">
                  <a-input-number v-model:value="record.priority" size="small" :min="0" :max="99" style="width: 70px;" :disabled="detail.status === 'published'" />
                </template>
                <template v-if="column.key === 'enabled'">
                  <a-switch v-model:checked="record.enabled" size="small" :disabled="detail.status === 'published'" />
                </template>
                <template v-if="column.key === 'depends_on'">
                  <a-select
                    v-if="form.orchestration_mode === 'dag'"
                    :value="record.depends_on"
                    mode="multiple"
                    size="small"
                    style="min-width: 140px;"
                    placeholder="依赖"
                    :disabled="detail.status === 'published'"
                    :options="depOptionsFor(record)"
                    @change="(val: number[]) => (record.depends_on = val)"
                  />
                  <span v-else style="font-size: 12px; color: #999;">Supervisor 动态决策</span>
                </template>
                <template v-if="column.key === 'op'">
                  <a-button
                    type="link"
                    size="small"
                    danger
                    :disabled="detail.status === 'published'"
                    @click="removeTeamRow(index)"
                  >移除</a-button>
                </template>
              </template>
            </a-table>
            <a-button
              v-if="detail.status !== 'published'"
              type="dashed"
              block
              style="margin-top: 12px;"
              @click="showAddAgent = true"
            >
              <PlusOutlined /> 添加团队 Agent
            </a-button>
            <a-modal
              v-model:open="showAddAgent"
              title="选择要加入团队的 Agent（仅已发布）"
              ok-text="添加"
              cancel-text="取消"
              @ok="addTeamAgents"
            >
              <a-select
                v-model:value="pendingAgentIds"
                mode="multiple"
                style="width: 100%;"
                placeholder="选择 Agent"
                :options="addableOptions"
                show-search
                option-filter-prop="label"
              />
            </a-modal>
          </div>

          <!-- Advanced Config -->
          <div class="config-section">
            <a-collapse ghost>
              <a-collapse-panel key="adv" header="高级配置">
                <a-form layout="vertical">
                  <a-row :gutter="16">
                    <a-col :span="12">
                      <a-form-item label="max_agent_calls（Agent 调用上限）">
                        <a-input-number v-model:value="form.config.max_agent_calls" :min="1" :max="100" style="width: 100%;" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="supervisor_max_rounds（决策轮次上限）">
                        <a-input-number v-model:value="form.config.supervisor_max_rounds" :min="1" :max="50" style="width: 100%;" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="step_timeout_seconds（步骤超时）">
                        <a-input-number v-model:value="form.config.step_timeout_seconds" :min="30" :max="1800" style="width: 100%;" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="max_retries（步骤重试次数）">
                        <a-input-number v-model:value="form.config.max_retries" :min="0" :max="5" style="width: 100%;" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="fail_fast（DAG 步骤失败即终止）">
                        <a-switch v-model:checked="form.config.fail_fast" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="summarize_with_llm（LLM 汇总结果）">
                        <a-switch v-model:checked="form.config.summarize_with_llm" />
                      </a-form-item>
                    </a-col>
                  </a-row>
                </a-form>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </div>
      </a-spin>

      <template #footer>
        <a-space>
          <a-button @click="drawerVisible = false">取消</a-button>
          <a-button
            v-if="detail && detail.status === 'published'"
            danger
            :loading="actionLoading"
            @click="handleDisable"
          >禁用</a-button>
          <a-button
            v-else
            type="primary"
            ghost
            :loading="actionLoading"
            :disabled="!!cycleError || supervisorMissing"
            @click="handlePublish"
          >
            <CloudUploadOutlined /> 发布
          </a-button>
          <a-button
            type="primary"
            :loading="saving"
            :disabled="detail?.status === 'published' || !!cycleError || supervisorMissing"
            @click="handleSave"
          >保存</a-button>
        </a-space>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  InfoCircleOutlined, ApartmentOutlined, TeamOutlined, CloudUploadOutlined
} from '@ant-design/icons-vue'
import { employeeApi } from '@/api/client'

const router = useRouter()

// --- List state ---
const loading = ref(false)
const employees = ref<any[]>([])
const keyword = ref('')

const columns = [
  { title: '名称', key: 'name' },
  { title: '业务角色', dataIndex: 'role', key: 'role', width: 120 },
  { title: 'Agent 数', dataIndex: 'agent_count', key: 'agent_count', width: 90, align: 'center' },
  { title: '模式', key: 'mode', width: 110, align: 'center' },
  { title: 'Supervisor', key: 'supervisor', width: 140 },
  { title: '状态', key: 'status', width: 110 },
  { title: '操作', key: 'action', width: 300 }
]

const teamColumns = [
  { title: 'Agent', key: 'agent', width: 150 },
  { title: '角色', key: 'role', width: 140 },
  { title: '优先级', key: 'priority', width: 90, align: 'center' },
  { title: '启用', key: 'enabled', width: 70, align: 'center' },
  { title: '依赖', key: 'depends_on' },
  { title: '', key: 'op', width: 70 }
]

const filteredEmployees = computed(() => employees.value)

async function loadEmployees() {
  loading.value = true
  try {
    const res = await employeeApi.list(keyword.value ? { keyword: keyword.value } : undefined)
    employees.value = res.data
  } catch {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

// --- Status helpers ---
function statusLabel(s: string): string {
  return ({ draft: '草稿', published: '已发布', disabled: '已禁用' } as Record<string, string>)[s] || s
}
function statusBadge(s: string): string {
  return ({ draft: 'default', published: 'success', disabled: 'error' } as Record<string, string>)[s] || 'default'
}
function supervisorName(record: any): string {
  const id = record.supervisor_agent_id
  const a = selectableAgents.value.find((x: any) => x.id === id)
  return a?.name || `Agent#${id}`
}

// --- Create modal ---
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({
  name: '', code: '', role: '', orchestration_mode: 'dag' as 'dag' | 'supervisor'
})

function openCreateModal() {
  createForm.name = ''
  createForm.code = ''
  createForm.role = ''
  createForm.orchestration_mode = 'dag'
  createVisible.value = true
}

async function handleCreate() {
  if (!createForm.name || !createForm.code) {
    message.warning('请填写名称和 Code')
    return
  }
  creating.value = true
  try {
    await employeeApi.create({ ...createForm })
    message.success('创建成功，请在配置抽屉中完善团队绑定')
    createVisible.value = false
    await loadEmployees()
  } catch {
    // handled by interceptor
  } finally {
    creating.value = false
  }
}

// --- Config drawer ---
const drawerVisible = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const actionLoading = ref(false)
const detail = ref<any>(null)
const editing = ref<any>(null)
const selectableAgents = ref<any[]>([])
const showAddAgent = ref(false)
const pendingAgentIds = ref<number[]>([])
const teamRows = ref<any[]>([])

const form = reactive({
  name: '',
  role: '',
  description: '',
  goal: '',
  role_prompt: '',
  orchestration_mode: 'dag' as 'dag' | 'supervisor',
  supervisor_agent_id: null as number | null,
  config: {} as Record<string, any>
})

const selectableOptions = computed(() =>
  selectableAgents.value.map((a: any) => ({ value: a.id, label: `${a.name} (#${a.id})` }))
)

const addableOptions = computed(() =>
  selectableAgents.value
    .filter((a: any) => !teamRows.value.some((r) => r.agent_id === a.id))
    .map((a: any) => ({ value: a.id, label: `${a.name} (#${a.id})` }))
)

const supervisorMissing = computed(() =>
  form.orchestration_mode === 'supervisor' && !form.supervisor_agent_id
)

function agentNameOf(id: number): string {
  const a = selectableAgents.value.find((x: any) => x.id === id)
  return a?.name || `Agent#${id}`
}

function depOptionsFor(row: any) {
  // Dependencies: other enabled team agents, excluding self
  return teamRows.value
    .filter((r) => r.agent_id !== row.agent_id && r.enabled)
    .map((r) => ({ value: r.agent_id, label: agentNameOf(r.agent_id) }))
}

// Front-end cycle detection (same rule as backend, DFS)
const cycleError = computed(() => {
  if (form.orchestration_mode !== 'dag') return ''
  const graph: Record<number, number[]> = {}
  for (const r of teamRows.value) {
    graph[r.agent_id] = (r.depends_on || []).filter(
      (d: number) => d in graph || teamRows.value.some((t) => t.agent_id === d)
    )
  }
  const WHITE = 0, GRAY = 1, BLACK = 2
  const color: Record<number, number> = {}
  for (const id of Object.keys(graph)) color[Number(id)] = WHITE

  const dfs = (node: number): boolean => {
    color[node] = GRAY
    for (const nb of graph[node] || []) {
      if (color[nb] === undefined) continue
      if (color[nb] === GRAY) return true
      if (color[nb] === WHITE && dfs(nb)) return true
    }
    color[node] = BLACK
    return false
  }

  for (const id of Object.keys(graph)) {
    if (color[Number(id)] === WHITE && dfs(Number(id))) {
      return '检测到 Agent 依赖关系成环，请调整依赖配置'
    }
  }
  return ''
})

async function openConfigDrawer(record: any) {
  editing.value = record
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const [detailRes, selRes] = await Promise.all([
      employeeApi.detail(record.id),
      employeeApi.selectableAgents()
    ])
    selectableAgents.value = selRes.data
    detail.value = detailRes.data

    form.name = detail.value.name || ''
    form.role = detail.value.role || ''
    form.description = detail.value.description || ''
    form.goal = detail.value.goal || ''
    form.role_prompt = detail.value.role_prompt || ''
    form.orchestration_mode = detail.value.orchestration_mode || 'dag'
    form.supervisor_agent_id = detail.value.supervisor_agent_id || null
    form.config = {
      max_agent_calls: detail.value.config?.max_agent_calls ?? 20,
      supervisor_max_rounds: detail.value.config?.supervisor_max_rounds ?? 15,
      step_timeout_seconds: detail.value.config?.step_timeout_seconds ?? 300,
      max_retries: detail.value.config?.max_retries ?? 1,
      fail_fast: detail.value.config?.fail_fast ?? false,
      summarize_with_llm: detail.value.config?.summarize_with_llm ?? false
    }

    teamRows.value = (detail.value.bindings || []).map((b: any) => ({
      agent_id: b.agent_id,
      role: b.role || '',
      priority: b.priority ?? 0,
      enabled: b.enabled,
      depends_on: [...(b.depends_on || [])]
    }))
  } catch {
    // handled
  } finally {
    detailLoading.value = false
  }
}

function addTeamAgents() {
  for (const id of pendingAgentIds.value) {
    if (!teamRows.value.some((r) => r.agent_id === id)) {
      teamRows.value.push({
        agent_id: id,
        role: '',
        priority: teamRows.value.length + 1,
        enabled: true,
        depends_on: []
      })
    }
  }
  pendingAgentIds.value = []
}

function removeTeamRow(index: number) {
  const removed = teamRows.value[index].agent_id
  teamRows.value.splice(index, 1)
  // Clean dangling depends_on references
  for (const r of teamRows.value) {
    r.depends_on = (r.depends_on || []).filter((d: number) => d !== removed)
  }
}

async function handleSave() {
  if (!detail.value) return
  saving.value = true
  try {
    await employeeApi.update(detail.value.id, {
      name: form.name,
      role: form.role,
      description: form.description,
      goal: form.goal,
      role_prompt: form.role_prompt,
      orchestration_mode: form.orchestration_mode,
      supervisor_agent_id: form.supervisor_agent_id,
      config: form.config
    })
    await employeeApi.setBindings(
      detail.value.id,
      teamRows.value.map((r) => ({
        agent_id: r.agent_id,
        role: r.role || undefined,
        priority: r.priority,
        enabled: r.enabled,
        depends_on: r.depends_on || []
      }))
    )
    message.success('配置已保存')
    await loadEmployees()
    drawerVisible.value = false
  } catch {
    // handled
  } finally {
    saving.value = false
  }
}

async function handlePublish() {
  if (!detail.value) return
  actionLoading.value = true
  try {
    // Save first, then publish (backend re-validates everything)
    await employeeApi.update(detail.value.id, {
      name: form.name,
      role: form.role,
      description: form.description,
      goal: form.goal,
      role_prompt: form.role_prompt,
      orchestration_mode: form.orchestration_mode,
      supervisor_agent_id: form.supervisor_agent_id,
      config: form.config
    })
    await employeeApi.setBindings(
      detail.value.id,
      teamRows.value.map((r) => ({
        agent_id: r.agent_id,
        role: r.role || undefined,
        priority: r.priority,
        enabled: r.enabled,
        depends_on: r.depends_on || []
      }))
    )
    await employeeApi.publish(detail.value.id)
    message.success('发布成功')
    await loadEmployees()
    drawerVisible.value = false
  } catch {
    // handled
  } finally {
    actionLoading.value = false
  }
}

async function handleDisable() {
  if (!detail.value) return
  actionLoading.value = true
  try {
    await employeeApi.disable(detail.value.id)
    message.success('已禁用')
    await loadEmployees()
    drawerVisible.value = false
  } catch {
    // handled
  } finally {
    actionLoading.value = false
  }
}

async function handleDelete(record: any) {
  try {
    await employeeApi.remove(record.id)
    message.success('已删除')
    await loadEmployees()
  } catch {
    // handled
  }
}

function openWorkbench(record: any) {
  router.push({ path: '/employee-workbench', query: { employee_id: record.id } })
}

onMounted(loadEmployees)
</script>

<style scoped>
.employees-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-section {
  margin-bottom: 24px;
}

.section-title {
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
