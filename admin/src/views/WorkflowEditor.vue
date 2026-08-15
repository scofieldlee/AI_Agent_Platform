<template>
  <div class="workflow-editor">
    <!-- Toolbar -->
    <div class="workflow-toolbar">
      <div class="toolbar-left">
        <ApartmentOutlined class="toolbar-icon" />
        <a-select
          v-model:value="currentWorkflowId"
          style="width: 260px"
          placeholder="选择工作流"
          :loading="workflowsLoading"
          @change="onWorkflowChange"
        >
          <a-select-option v-for="wf in workflows" :key="wf.id" :value="wf.id">
            {{ wf.name }}
            <a-tag v-if="wf.status === 'published'" color="green" size="small" style="margin-left: 6px;">已发布</a-tag>
            <a-tag v-else color="orange" size="small" style="margin-left: 6px;">草稿</a-tag>
          </a-select-option>
        </a-select>
        <a-button size="small" @click="openCreateModal">
          <PlusOutlined /> 新建
        </a-button>
        <a-tag v-if="definition" color="blue">{{ definition.nodes.length }} 节点</a-tag>
        <a-tag v-if="definition" color="purple">{{ definition.edges.length }} 连线</a-tag>
      </div>
      <div class="toolbar-right">
        <a-radio-group v-model:value="editMode" size="small" button-style="solid">
          <a-radio-button :value="false">
            <EyeOutlined /> 查看
          </a-radio-button>
          <a-radio-button :value="true">
            <EditOutlined /> 编辑
          </a-radio-button>
        </a-radio-group>

        <a-button
          v-if="editMode"
          type="primary"
          size="small"
          :loading="saving"
          :disabled="!dirty"
          @click="saveWorkflow"
        >
          <SaveOutlined /> {{ dirty ? '保存修改' : '已保存' }}
        </a-button>
        <a-button
          v-if="editMode"
          size="small"
          :loading="publishing"
          :disabled="!currentWorkflowId"
          @click="publishWorkflow"
        >
          <RocketOutlined /> 发布
        </a-button>

        <a-divider type="vertical" />

        <a-select
          v-model:value="selectedTraceId"
          placeholder="选择 Trace 查看执行路径"
          style="width: 320px"
          allow-clear
          @change="onTraceChange"
        >
          <a-select-option
            v-for="t in traces"
            :key="t.trace_id"
            :value="t.trace_id"
          >
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>
                <span style="font-family: monospace; font-size: 12px;">{{ t.trace_id.substring(0, 12) }}...</span>
                <a-divider type="vertical" />
                <a-tag :color="intentColor(t.intent)" size="small">{{ t.intent || 'unknown' }}</a-tag>
              </span>
              <span style="font-size: 12px; opacity: 0.6;">
                {{ t.duration_ms ? (t.duration_ms / 1000).toFixed(1) + 's' : '-' }}
              </span>
            </div>
          </a-select-option>
        </a-select>
        <a-button @click="loadTraces" :loading="tracesLoading" size="small">
          <ReloadOutlined />
        </a-button>
      </div>
    </div>

    <!-- Main Content: Palette + Canvas + Detail Panel -->
    <div class="workflow-body">
      <!-- Node Palette (edit mode) -->
      <div v-if="editMode" class="palette" :class="{ dark: isDark }">
        <div class="palette-title">节点库</div>
        <div class="palette-hint">拖拽到画布添加节点</div>
        <div
          v-for="t in paletteNodes"
          :key="t.nodeType"
          class="palette-node"
          draggable="true"
          @dragstart="onPaletteDragStart($event, t.nodeType)"
        >
          <component :is="categoryIcon(t.category)" class="palette-node-icon" :style="{ color: t.color }" />
          <span>{{ t.name }}</span>
        </div>
        <div class="palette-footer">
          <a-alert type="info" :show-icon="false" style="font-size: 11px;" message="Delete 键删除选中元素" />
        </div>
      </div>

      <!-- Vue Flow Canvas -->
      <div
        class="workflow-canvas"
        :class="[{ dark: isDark }, editMode ? 'editing' : '']"
        @drop="onDrop"
        @dragover.prevent
      >
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :node-types="nodeTypes"
          :default-viewport="{ zoom: 0.75, x: 20, y: 40 }"
          :min-zoom="0.3"
          :max-zoom="2"
          :nodes-draggable="editMode"
          :nodes-connectable="editMode"
          :elements-selectable="true"
          :delete-key-code="['Delete', 'Backspace']"
          fit-view-on-init
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
          @pane-click="onPaneClick"
          @connect="onConnect"
          @node-drag-stop="onNodeDragStop"
          @nodes-delete="onNodesDelete"
          @edges-delete="onEdgesDelete"
        >
          <Background :gap="20" :size="1" pattern-color="#888" />
          <Controls position="bottom-left" />
          <MiniMap
            pannable
            zoomable
            :node-color="miniMapNodeColor"
            :mask-color="isDark ? 'rgba(20,20,20,0.6)' : 'rgba(240,240,240,0.6)'"
          />
        </VueFlow>

        <!-- Edit-mode banner -->
        <div v-if="editMode" class="edit-banner" :class="{ dark: isDark }">
          <EditOutlined /> 编辑模式：拖拽节点库节点到画布 · 拖动节点调整位置 · 拖动手柄连线 · Delete 删除
        </div>

        <!-- Legend -->
        <div class="workflow-legend" :class="{ dark: isDark }">
          <div class="legend-item" v-for="cat in categories" :key="cat.key">
            <div class="legend-dot" :style="{ background: cat.color }"></div>
            <span>{{ cat.label }}</span>
          </div>
        </div>

        <!-- Execution Summary (when trace selected) -->
        <div v-if="executionPath" class="execution-summary" :class="{ dark: isDark }">
          <div class="exec-header">
            <span class="exec-label">执行路径</span>
            <a-tag :color="statusColor(executionPath.status)">{{ statusLabel(executionPath.status) }}</a-tag>
            <a-tag color="blue">{{ executionPath.intent }}</a-tag>
            <a-tag color="cyan">置信度 {{ executionPath.confidence }}</a-tag>
            <span class="exec-duration">
              总耗时 {{ executionPath.duration_ms ? (executionPath.duration_ms / 1000).toFixed(2) + 's' : '-' }}
            </span>
          </div>
          <div class="exec-steps">
            <span
              v-for="(step, i) in executionPath.steps"
              :key="i"
              class="exec-step-tag"
              :style="{ borderColor: categoryColor(step.node_category) }"
            >
              <span class="step-name">{{ nodeName(step.node_name) }}</span>
              <span class="step-duration">{{ step.duration_ms ? step.duration_ms + 'ms' : '-' }}</span>
              <ArrowRightOutlined v-if="i < executionPath.steps.length - 1" class="step-arrow" />
            </span>
          </div>
        </div>
      </div>

      <!-- Detail Panel -->
      <div class="detail-panel" :class="{ dark: isDark }">
        <!-- ===== EDIT MODE: node / edge configuration ===== -->
        <template v-if="editMode">
          <template v-if="selectedEdge">
            <div class="detail-header">
              <div class="detail-icon" style="background: #8b5cf6;">
                <SwapOutlined />
              </div>
              <div>
                <h4>连线配置</h4>
                <a-tag color="purple">边</a-tag>
                <a-tag>{{ selectedEdge.source }} → {{ selectedEdge.target === 'END' ? 'END' : selectedEdge.target }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">连线类型</div>
              <a-radio-group v-model:value="selectedEdge.edge_type" size="small" style="width: 100%;">
                <a-radio value="default" style="display: block; margin-bottom: 6px;">默认连线（无条件执行）</a-radio>
                <a-radio value="conditional" style="display: block;">条件连线（按条件路由）</a-radio>
              </a-radio-group>
            </div>

            <div class="detail-section" v-if="selectedEdge.edge_type === 'conditional'">
              <div class="detail-label">条件表达式</div>
              <a-input
                v-model:value="selectedEdge.condition"
                placeholder="例如: confidence >= 0.5"
                size="small"
              />
              <div style="font-size: 11px; opacity: 0.6; margin-top: 6px; line-height: 1.5;">
                可用字段: intent, confidence, need_human, answer, knowledge_context, tool_results 等<br />
                支持运算符: &gt;=, &lt;, ==, && (且), || (或), ! (非)
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">连线标签</div>
              <a-input
                v-model:value="selectedEdge.label"
                placeholder="显示在连线上"
                size="small"
              />
            </div>

            <div class="detail-section">
              <a-button danger block size="small" @click="removeEdge(selectedEdge)">
                <DeleteOutlined /> 删除此连线
              </a-button>
            </div>
          </template>

          <template v-else-if="selectedNode">
            <div class="detail-header">
              <div class="detail-icon" :style="{ background: categoryColor(selectedNode.category) }">
                <component :is="categoryIcon(selectedNode.category)" />
              </div>
              <div>
                <h4>{{ selectedNode.name }}</h4>
                <a-tag :color="categoryColor(selectedNode.category)">{{ categoryLabel(selectedNode.category) }}</a-tag>
                <a-tag>{{ selectedNode.nodeType }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">节点名称</div>
              <a-input v-model:value="selectedNode.name" size="small" @change="markDirty" />
            </div>

            <div class="detail-section">
              <div class="detail-label">描述</div>
              <a-textarea
                v-model:value="selectedNode.description"
                :rows="3"
                size="small"
                @change="markDirty"
              />
            </div>

            <div class="detail-section">
              <div class="detail-label">输入</div>
              <div class="io-tags">
                <a-tag v-for="inp in selectedNode.inputs" :key="inp" color="green">{{ inp }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">输出</div>
              <div class="io-tags">
                <a-tag v-for="out in selectedNode.outputs" :key="out" color="orange">{{ out }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">节点参数 (JSON)</div>
              <a-textarea
                v-model:value="nodeConfigText"
                :rows="4"
                size="small"
                placeholder='{"top_k": 5}'
                @change="onNodeConfigChange"
              />
              <div style="font-size: 11px; opacity: 0.6; margin-top: 6px;">参数为预留字段，后续将支持按节点类型配置（如检索数量、工具列表、模型等）</div>
            </div>

            <div class="detail-section">
              <a-popconfirm
                title="删除该节点？相连的连线也会一并删除"
                ok-text="删除"
                cancel-text="取消"
                @confirm="removeNode(selectedNode)"
              >
                <a-button danger block size="small">
                  <DeleteOutlined /> 删除此节点
                </a-button>
              </a-popconfirm>
            </div>
          </template>

          <template v-else>
            <div class="detail-empty">
              <NodeIndexOutlined style="font-size: 48px; opacity: 0.2;" />
              <p>点击画布中的节点或连线进行配置</p>
              <p style="font-size: 12px; opacity: 0.5;">从左侧节点库拖拽添加新节点</p>
            </div>
          </template>
        </template>

        <!-- ===== VIEW MODE: node execution details ===== -->
        <template v-else>
          <template v-if="selectedNode">
            <div class="detail-header">
              <div class="detail-icon" :style="{ background: categoryColor(selectedNode.category) }">
                <component :is="categoryIcon(selectedNode.category)" />
              </div>
              <div>
                <h4>{{ selectedNode.name }}</h4>
                <a-tag :color="categoryColor(selectedNode.category)">{{ categoryLabel(selectedNode.category) }}</a-tag>
                <a-tag>{{ selectedNode.type }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">描述</div>
              <p class="detail-text">{{ selectedNode.description }}</p>
            </div>

            <div class="detail-section">
              <div class="detail-label">输入</div>
              <div class="io-tags">
                <a-tag v-for="inp in selectedNode.inputs" :key="inp" color="green">{{ inp }}</a-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-label">输出</div>
              <div class="io-tags">
                <a-tag v-for="out in selectedNode.outputs" :key="out" color="orange">{{ out }}</a-tag>
              </div>
            </div>

            <template v-if="selectedNodeExecution">
              <a-divider style="margin: 16px 0;" />
              <div class="detail-section">
                <div class="detail-label">执行详情</div>
                <a-descriptions :column="1" size="small" bordered>
                  <a-descriptions-item label="状态">
                    <a-tag :color="statusColor(selectedNodeExecution.status)">
                      {{ statusLabel(selectedNodeExecution.status) }}
                    </a-tag>
                  </a-descriptions-item>
                  <a-descriptions-item label="耗时">
                    <span style="font-weight: 600; color: #4f46e5;">
                      {{ selectedNodeExecution.duration_ms ? selectedNodeExecution.duration_ms + 'ms' : '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="开始时间">
                    {{ formatTime(selectedNodeExecution.started_at) }}
                  </a-descriptions-item>
                  <a-descriptions-item label="完成时间">
                    {{ formatTime(selectedNodeExecution.completed_at) }}
                  </a-descriptions-item>
                </a-descriptions>
              </div>

              <div class="detail-section" v-if="selectedNodeExecution.attributes">
                <div class="detail-label">输入数据</div>
                <pre class="detail-code" :class="{ dark: isDark }">{{ formatJSON(selectedNodeExecution.attributes?.input) }}</pre>
              </div>

              <div class="detail-section" v-if="selectedNodeExecution.attributes?.output">
                <div class="detail-label">输出数据</div>
                <pre class="detail-code" :class="{ dark: isDark }">{{ formatJSON(selectedNodeExecution.attributes?.output) }}</pre>
              </div>

              <div class="detail-section" v-if="selectedNodeExecution.attributes?.error">
                <div class="detail-label">错误信息</div>
                <pre class="detail-code error" :class="{ dark: isDark }">{{ selectedNodeExecution.attributes.error }}</pre>
              </div>
            </template>
          </template>

          <template v-else>
            <div class="detail-empty">
              <NodeIndexOutlined style="font-size: 48px; opacity: 0.2;" />
              <p>点击画布中的节点查看详情</p>
              <p v-if="executionPath" style="font-size: 12px; opacity: 0.5;">
                已加载执行路径，点击节点可查看该步骤的输入/输出数据
              </p>
            </div>
          </template>
        </template>
      </div>
    </div>

    <!-- Create workflow modal -->
    <a-modal
      v-model:open="createModalOpen"
      title="新建工作流"
      :confirm-loading="creating"
      ok-text="创建"
      cancel-text="取消"
      @ok="createWorkflow"
    >
      <a-form layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="createForm.name" placeholder="例如: 售后流程工作流" />
        </a-form-item>
        <a-form-item label="编码" required>
          <a-input v-model:value="createForm.code" placeholder="例如: after_sale_workflow" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="createForm.description" :rows="2" placeholder="可选" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, markRaw, reactive } from 'vue'
import {
  VueFlow,
  useVueFlow,
  type Node,
  type Edge,
  type Connection,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { message, Modal } from 'ant-design-vue'
import {
  ApartmentOutlined,
  ReloadOutlined,
  ArrowRightOutlined,
  NodeIndexOutlined,
  AimOutlined,
  SearchOutlined,
  DatabaseOutlined,
  ToolOutlined,
  RobotOutlined,
  CustomerServiceOutlined,
  PlusOutlined,
  EyeOutlined,
  EditOutlined,
  SaveOutlined,
  RocketOutlined,
  DeleteOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import { useThemeStore } from '@/stores/theme'
import { workflowApi } from '@/api/client'
import WorkflowNode from '@/components/WorkflowNode.vue'

// Import Vue Flow styles
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)

// Custom node types — markRaw prevents Vue from making the component reactive
const nodeTypes = {
  workflow: markRaw(WorkflowNode) as any,
}

// --- Category config ---
const categories = [
  { key: 'intent', label: '意图分类', color: '#7c3aed' },
  { key: 'retrieval', label: '检索', color: '#3b82f6' },
  { key: 'tool', label: '工具', color: '#f59e0b' },
  { key: 'model', label: 'LLM', color: '#10b981' },
  { key: 'human', label: '转人工', color: '#ef4444' },
]

function categoryColor(cat: string): string {
  return categories.find(c => c.key === cat)?.color || '#6b7280'
}

function categoryLabel(cat: string): string {
  return categories.find(c => c.key === cat)?.label || cat
}

function categoryIcon(cat: string) {
  const map: Record<string, any> = {
    intent: markRaw(AimOutlined),
    retrieval: markRaw(SearchOutlined),
    tool: markRaw(ToolOutlined),
    model: markRaw(RobotOutlined),
    human: markRaw(CustomerServiceOutlined),
  }
  return map[cat] || markRaw(NodeIndexOutlined)
}

function miniMapNodeColor(node: any): string {
  const cat = node.data?.category
  return categoryColor(cat)
}

// --- Node palette templates ---
interface PaletteItem {
  name: string
  nodeType: string
  category: string
  color: string
}

const paletteNodes: PaletteItem[] = [
  { name: '意图分类', nodeType: 'intent', category: 'intent', color: '#7c3aed' },
  { name: '知识检索', nodeType: 'knowledge', category: 'retrieval', color: '#3b82f6' },
  { name: '记忆检索', nodeType: 'memory', category: 'retrieval', color: '#3b82f6' },
  { name: '工具执行', nodeType: 'tool', category: 'tool', color: '#f59e0b' },
  { name: 'LLM 生成', nodeType: 'llm', category: 'model', color: '#10b981' },
  { name: '转人工', nodeType: 'human', category: 'human', color: '#ef4444' },
]

const NODE_TEMPLATES: Record<string, any> = {
  intent: {
    name: '意图分类',
    node_type: 'intent',
    type: 'processing',
    category: 'intent',
    description: '使用 LLM 对用户输入进行意图分类。',
    inputs: ['user_input', 'conversation_history'],
    outputs: ['intent', 'confidence'],
  },
  knowledge: {
    name: '知识检索',
    node_type: 'knowledge',
    type: 'processing',
    category: 'retrieval',
    description: 'RAG 知识检索：在知识库中检索与用户问题相关的文档片段。',
    inputs: ['user_input', 'intent'],
    outputs: ['knowledge_context', 'knowledge_sources'],
  },
  memory: {
    name: '记忆检索',
    node_type: 'memory',
    type: 'processing',
    category: 'retrieval',
    description: '长期记忆检索：检索该用户的历史记忆（偏好、事实、行为）。',
    inputs: ['user_input', 'user_id', 'agent_id'],
    outputs: ['memory_context', 'memories_used'],
  },
  tool: {
    name: '工具执行',
    node_type: 'tool',
    type: 'processing',
    category: 'tool',
    description: '多工具并行调度器：按意图映射表执行查询工具。',
    inputs: ['user_input', 'intent', 'agent_id', 'conversation_id', 'trace_id'],
    outputs: ['tool_results'],
  },
  llm: {
    name: 'LLM 生成',
    node_type: 'llm',
    type: 'processing',
    category: 'model',
    description: '使用大模型生成最终回答，注入知识上下文与工具结果。',
    inputs: ['user_input', 'knowledge_context', 'memory_context', 'tool_results', 'conversation_history', 'intent'],
    outputs: ['answer', 'confidence', 'need_human', 'transfer_reason'],
  },
  human: {
    name: '转人工',
    node_type: 'human',
    type: 'terminal',
    category: 'human',
    description: '创建人工客服工单并返回工单号。',
    inputs: ['user_input', 'intent', 'confidence', 'transfer_reason', 'answer', 'conversation_id', 'agent_id', 'trace_id'],
    outputs: ['answer', 'need_human', 'ticket_number'],
  },
}

// --- Node/Edge name mapping ---
const nodeNameMap: Record<string, string> = {
  intent: '意图分类',
  knowledge: '知识检索',
  memory: '记忆检索',
  tool: '工具执行',
  llm: 'LLM 生成',
  human: '转人工',
}

function nodeName(id: string): string {
  return nodeNameMap[id] || id
}

// --- Status helpers ---
function statusColor(status: string): string {
  const map: Record<string, string> = {
    success: 'green',
    failed: 'red',
    human_transfer: 'orange',
    running: 'blue',
    error: 'red',
  }
  return map[status] || 'default'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    success: '成功',
    failed: '失败',
    human_transfer: '转人工',
    running: '执行中',
    error: '错误',
  }
  return map[status] || status
}

function intentColor(intent: string | null): string {
  if (!intent) return 'default'
  const map: Record<string, string> = {
    product_info: 'blue',
    product_compare: 'cyan',
    purchase_advice: 'geekblue',
    order_query: 'green',
    after_sale: 'orange',
    complaint: 'red',
    greeting: 'purple',
    unknown: 'default',
  }
  return map[intent] || 'default'
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function formatJSON(data: any): string {
  if (!data) return '-'
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

// --- Data ---
const workflows = ref<any[]>([])
const workflowsLoading = ref(false)
const currentWorkflowId = ref<number | undefined>(undefined)
const currentWorkflow = computed(() => workflows.value.find(w => w.id === currentWorkflowId.value))
const definition = ref<any>(null)
const editMode = ref(false)
const dirty = ref(false)
const saving = ref(false)
const publishing = ref(false)
const creating = ref(false)

const traces = ref<any[]>([])
const tracesLoading = ref(false)
const selectedTraceId = ref<string | undefined>(undefined)
const executionPath = ref<any>(null)
const selectedNode = ref<any>(null)
const selectedNodeExecution = ref<any>(null)
const selectedEdge = ref<any>(null)
const nodeConfigText = ref('')

const createModalOpen = ref(false)
const createForm = reactive({ name: '', code: '', description: '' })

const { screenToFlowCoordinate } = useVueFlow()

// --- Build Vue Flow nodes ---
const flowNodes = computed<Node[]>(() => {
  if (!definition.value) return []

  const executedNodes = new Set<string>()
  if (executionPath.value) {
    for (const step of executionPath.value.steps) {
      executedNodes.add(step.node_name)
    }
  }

  const hasTrace = !!executionPath.value

  return definition.value.nodes.map((n: any) => {
    const color = categoryColor(n.category)
    const isExecuted = executedNodes.has(n.id)
    const execStep = executionPath.value?.steps.find((s: any) => s.node_name === n.id)

    return {
      id: n.id,
      position: { x: n.position.x, y: n.position.y },
      type: 'workflow',
      data: {
        label: n.name,
        category: n.category,
        description: n.description,
        inputs: n.inputs,
        outputs: n.outputs,
        type: n.type,
        nodeType: n.node_type,
        config: n.config || {},
        editable: editMode.value,
        color,
        isExecuted,
        hasTrace,
        durationMs: execStep?.duration_ms,
        stepStatus: execStep?.status,
      },
      class: [
        selectedNode.value?.id === n.id ? 'node-selected' : '',
      ].filter(Boolean).join(' '),
    }
  })
})

// --- Build Vue Flow edges ---
const flowEdges = computed<Edge[]>(() => {
  if (!definition.value) return []

  const executedEdges = new Set<string>()
  if (executionPath.value) {
    const steps = executionPath.value.steps
    for (let i = 0; i < steps.length - 1; i++) {
      const source = steps[i].node_name
      const target = steps[i + 1].node_name
      const edge = definition.value.edges.find((e: any) => e.source === source && e.target === target)
      if (edge) executedEdges.add(edge.id)
    }
    const lastStep = steps[steps.length - 1]
    if (lastStep) {
      const matchingEdges = definition.value.edges.filter((e: any) => e.source === lastStep.node_name)
      for (const e of matchingEdges) {
        if (e.target === 'human' && executionPath.value.status === 'human_transfer') {
          executedEdges.add(e.id)
        }
      }
    }
  }

  return definition.value.edges.map((e: any) => {
    const isExecuted = executedEdges.has(e.id)
    const hasTrace = !!executionPath.value

    return {
      id: e.id,
      source: e.source,
      target: e.target === 'END' ? undefined : e.target,
      label: e.label || undefined,
      type: 'smoothstep',
      animated: isExecuted,
      style: {
        stroke: isExecuted ? '#4f46e5' : (hasTrace ? '#d1d5db' : '#94a3b8'),
        strokeWidth: isExecuted ? 3 : 1.5,
        opacity: hasTrace && !isExecuted ? 0.3 : 1,
        strokeDasharray: editMode.value && e.edge_type === 'conditional' ? '6 4' : undefined,
      },
      labelStyle: {
        fontSize: '11px',
        fill: isDark.value ? '#a0aec0' : '#64748b',
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: isDark.value ? '#1f1f1f' : '#fff',
      },
    } as Edge
  }).filter((e: Edge) => e.target !== undefined) as Edge[]
})

// --- Event handlers ---
function onNodeClick(event: any) {
  const node = event.node
  selectedEdge.value = null
  selectedNode.value = {
    id: node.id,
    name: node.data.label,
    category: node.data.category,
    description: node.data.description,
    inputs: node.data.inputs,
    outputs: node.data.outputs,
    type: node.data.type,
    nodeType: node.data.nodeType,
    config: node.data.config || {},
    position: node.position,
  }
  nodeConfigText.value = JSON.stringify(node.data.config || {}, null, 2)

  if (!editMode.value && executionPath.value) {
    selectedNodeExecution.value = executionPath.value.steps.find(
      (s: any) => s.node_name === node.id
    ) || null
  } else {
    selectedNodeExecution.value = null
  }
}

function onEdgeClick(event: any) {
  const edge = event.edge
  selectedNode.value = null
  selectedNodeExecution.value = null
  // Find the full edge definition (with END target preserved)
  const full = definition.value?.edges.find((e: any) => e.id === edge.id)
  if (full) {
    selectedEdge.value = reactive({
      ...full,
    })
  }
}

function onPaneClick() {
  selectedNode.value = null
  selectedNodeExecution.value = null
  selectedEdge.value = null
}

function onConnect(connection: Connection) {
  if (!connection.source || !connection.target) return
  // Ignore connections targeting END (not a real node)
  const nodeIds = new Set(definition.value.nodes.map((n: any) => n.id))
  if (!nodeIds.has(connection.source) || !nodeIds.has(connection.target)) return

  // Avoid duplicate edges
  const exists = definition.value.edges.some(
    (e: any) => e.source === connection.source && e.target === connection.target
  )
  if (exists) {
    message.warning('这两个节点之间已存在连线')
    return
  }

  const edgeId = `e-${connection.source}-${connection.target}-${Date.now()}`
  definition.value.edges.push({
    id: edgeId,
    source: connection.source,
    target: connection.target,
    label: '',
    condition: '',
    edge_type: 'default',
  })
  markDirty()
  message.success('已添加连线，可在右侧配置条件')
}

function onNodeDragStop(event: any) {
  const node = event.node
  const target = definition.value.nodes.find((n: any) => n.id === node.id)
  if (target && node.position) {
    target.position = { x: node.position.x, y: node.position.y }
    markDirty()
  }
}

function onNodesDelete(event: any) {
  const deleted = event.nodes || []
  if (!deleted.length) return
  const deletedIds = new Set(deleted.map((n: any) => n.id))
  definition.value.nodes = definition.value.nodes.filter((n: any) => !deletedIds.has(n.id))
  definition.value.edges = definition.value.edges.filter(
    (e: any) => !deletedIds.has(e.source) && !deletedIds.has(e.target)
  )
  if (selectedNode.value && deletedIds.has(selectedNode.value.id)) {
    selectedNode.value = null
  }
  markDirty()
}

function onEdgesDelete(event: any) {
  const deleted = event.edges || []
  if (!deleted.length) return
  const deletedIds = new Set(deleted.map((e: any) => e.id))
  definition.value.edges = definition.value.edges.filter((e: any) => !deletedIds.has(e.id))
  if (selectedEdge.value && deletedIds.has(selectedEdge.value.id)) {
    selectedEdge.value = null
  }
  markDirty()
}

function removeNode(node: any) {
  definition.value.nodes = definition.value.nodes.filter((n: any) => n.id !== node.id)
  definition.value.edges = definition.value.edges.filter(
    (e: any) => e.source !== node.id && e.target !== node.id
  )
  if (selectedNode.value?.id === node.id) selectedNode.value = null
  markDirty()
}

function removeEdge(edge: any) {
  definition.value.edges = definition.value.edges.filter((e: any) => e.id !== edge.id)
  if (selectedEdge.value?.id === edge.id) selectedEdge.value = null
  markDirty()
}

function markDirty() {
  dirty.value = true
}

function onNodeConfigChange() {
  try {
    const parsed = JSON.parse(nodeConfigText.value || '{}')
    if (selectedNode.value) {
      selectedNode.value.config = parsed
    }
    markDirty()
  } catch {
    // Invalid JSON — keep as-is, block saving? We'll show subtle hint
  }
}

// --- Palette drag & drop ---
function onPaletteDragStart(event: DragEvent, nodeType: string) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/workflow-node', nodeType)
  event.dataTransfer.effectAllowed = 'move'
}

function onDrop(event: DragEvent) {
  if (!editMode.value) return
  const nodeType = event.dataTransfer?.getData('application/workflow-node')
  if (!nodeType || !NODE_TEMPLATES[nodeType]) return

  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  addNode(nodeType, position)
}

function genNodeId(nodeType: string): string {
  const existing = new Set(definition.value.nodes.map((n: any) => n.id))
  let i = 1
  let id = nodeType
  while (existing.has(id)) {
    i += 1
    id = `${nodeType}_${i}`
  }
  return id
}

function addNode(nodeType: string, position: { x: number; y: number }) {
  const template = NODE_TEMPLATES[nodeType]
  const id = genNodeId(nodeType)
  definition.value.nodes.push({
    id,
    name: template.name,
    node_type: template.node_type,
    type: template.type,
    category: template.category,
    description: template.description,
    inputs: [...template.inputs],
    outputs: [...template.outputs],
    position: { x: Math.round(position.x), y: Math.round(position.y) },
    config: {},
  })
  markDirty()
  message.success(`已添加「${template.name}」节点`)
}

// --- Workflow CRUD ---
function onWorkflowChange(id: number | undefined) {
  if (!id) return
  if (dirty.value && currentWorkflowId.value !== id) {
    Modal.confirm({
      title: '有未保存的修改',
      content: '切换到其他工作流将丢失未保存的修改，确定继续吗？',
      okText: '继续',
      cancelText: '取消',
      onOk: () => loadWorkflow(id),
    })
  } else {
    loadWorkflow(id)
  }
}

async function loadWorkflow(id: number) {
  try {
    const res = await workflowApi.detail(id)
    applyWorkflow(res.data)
  } catch (err: any) {
    message.error('加载工作流失败: ' + (err.response?.data?.detail || err.message))
  }
}

function applyWorkflow(wf: any) {
  definition.value = {
    id: wf.id,
    code: wf.code,
    name: wf.name,
    description: wf.description || '',
    entry_point: wf.graph_config?.entry_point || 'intent',
    nodes: wf.graph_config?.nodes || [],
    edges: wf.graph_config?.edges || [],
  }
  currentWorkflowId.value = wf.id
  dirty.value = false
  selectedNode.value = null
  selectedEdge.value = null
  selectedNodeExecution.value = null
  executionPath.value = null
  selectedTraceId.value = undefined
}

async function loadDefinition() {
  try {
    const res = await workflowApi.getDefinition()
    // Fetch full detail to get the id (definition endpoint may be the default)
    const wf = res.data
    if (wf.id) {
      const detailRes = await workflowApi.detail(wf.id)
      applyWorkflow(detailRes.data)
    } else {
      definition.value = {
        id: undefined,
        name: wf.name,
        description: wf.description,
        entry_point: wf.entry_point,
        nodes: wf.nodes,
        edges: wf.edges,
      }
    }
  } catch (err: any) {
    message.error('加载工作流定义失败: ' + (err.response?.data?.detail || err.message))
  }
}

async function loadWorkflows() {
  workflowsLoading.value = true
  try {
    const res = await workflowApi.list()
    workflows.value = res.data
  } catch (err: any) {
    message.error('加载工作流列表失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    workflowsLoading.value = false
  }
}

async function loadTraces() {
  tracesLoading.value = true
  try {
    const res = await workflowApi.getTraces({ limit: 50 })
    traces.value = res.data
  } catch (err: any) {
    message.error('加载 Trace 列表失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    tracesLoading.value = false
  }
}

async function onTraceChange(traceId: string | undefined) {
  selectedNode.value = null
  selectedNodeExecution.value = null

  if (!traceId) {
    executionPath.value = null
    return
  }

  try {
    const res = await workflowApi.getExecutionPath(traceId)
    executionPath.value = res.data
  } catch (err: any) {
    message.error('获取执行路径失败: ' + (err.response?.data?.detail || err.message))
    executionPath.value = null
  }
}

async function saveWorkflow() {
  if (!currentWorkflowId.value || !definition.value) return
  saving.value = true
  try {
    // Validate: entry point must exist among nodes
    const nodeIds = new Set(definition.value.nodes.map((n: any) => n.id))
    if (!definition.value.nodes.length) {
      message.error('工作流至少需要一个节点')
      return
    }
    if (!nodeIds.has(definition.value.entry_point)) {
      message.error('入口节点不存在，请保留入口节点（默认 intent）')
      return
    }
    // Validate edges: targets must exist (except END)
    for (const e of definition.value.edges) {
      if (e.target !== 'END' && !nodeIds.has(e.target)) {
        message.error(`连线 ${e.id} 的目标节点不存在`)
        return
      }
      if (!nodeIds.has(e.source)) {
        message.error(`连线 ${e.id} 的源节点不存在`)
        return
      }
    }

    const graphConfig = {
      entry_point: definition.value.entry_point,
      nodes: definition.value.nodes,
      edges: definition.value.edges,
    }

    await workflowApi.update(currentWorkflowId.value, {
      name: definition.value.name,
      description: definition.value.description,
      graph_config: graphConfig,
    })
    dirty.value = false
    message.success('工作流已保存，下次对话将使用新的流程定义')
    await loadWorkflows()
    await loadWorkflow(currentWorkflowId.value)
  } catch (err: any) {
    message.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function publishWorkflow() {
  if (!currentWorkflowId.value) return
  publishing.value = true
  try {
    await workflowApi.publish(currentWorkflowId.value)
    message.success('工作流已发布，运行时将使用该流程')
    dirty.value = false
    await loadWorkflows()
    await loadWorkflow(currentWorkflowId.value)
  } catch (err: any) {
    message.error('发布失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    publishing.value = false
  }
}

function openCreateModal() {
  createForm.name = ''
  createForm.code = ''
  createForm.description = ''
  createModalOpen.value = true
}

async function createWorkflow() {
  if (!createForm.name.trim() || !createForm.code.trim()) {
    message.warning('名称和编码不能为空')
    return
  }
  creating.value = true
  try {
    // Start from a single intent node (user builds from there)
    const seedNode = {
      id: 'intent',
      name: NODE_TEMPLATES.intent.name,
      node_type: 'intent',
      type: 'processing',
      category: 'intent',
      description: NODE_TEMPLATES.intent.description,
      inputs: NODE_TEMPLATES.intent.inputs,
      outputs: NODE_TEMPLATES.intent.outputs,
      position: { x: 100, y: 200 },
      config: {},
    }
    const res = await workflowApi.create({
      name: createForm.name.trim(),
      code: createForm.code.trim(),
      description: createForm.description.trim() || undefined,
      graph_config: {
        entry_point: 'intent',
        nodes: [seedNode],
        edges: [],
      },
    })
    createModalOpen.value = false
    message.success('工作流已创建，可在画布中编辑')
    await loadWorkflows()
    await loadWorkflow(res.data.id)
  } catch (err: any) {
    message.error('创建失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadWorkflows(), loadTraces()])
  // Load the default workflow definition (or first workflow)
  await loadDefinition()
})
</script>

<style scoped>
.workflow-editor {
  height: calc(100vh - 112px);
  display: flex;
  flex-direction: column;
}

/* Toolbar */
.workflow-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 16px 0;
  flex-shrink: 0;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-icon {
  font-size: 20px;
  color: #4f46e5;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* Body */
.workflow-body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}

/* Palette */
.palette {
  width: 180px;
  flex-shrink: 0;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  border: 1px solid #f0f0f0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.palette.dark {
  background: #1f1f1f;
  border-color: #303030;
}

.palette-title {
  font-size: 14px;
  font-weight: 600;
}

.palette-hint {
  font-size: 11px;
  opacity: 0.5;
  margin-bottom: 4px;
}

.palette-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1.5px solid rgba(128, 128, 128, 0.25);
  cursor: grab;
  font-size: 13px;
  transition: all 0.15s ease;
  user-select: none;
}

.palette-node:hover {
  border-color: #4f46e5;
  background: rgba(79, 70, 229, 0.05);
  transform: translateX(2px);
}

.palette-node:active {
  cursor: grabbing;
}

.palette-node-icon {
  font-size: 15px;
}

.palette-footer {
  margin-top: auto;
  padding-top: 8px;
}

/* Canvas */
.workflow-canvas {
  flex: 1;
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(128, 128, 128, 0.2);
  background: #fafafa;
}

.workflow-canvas :deep(.vue-flow) {
  background: #fafafa;
}

.workflow-canvas.dark {
  background: #141414;
}

.workflow-canvas.dark :deep(.vue-flow) {
  background: #141414;
}

.workflow-canvas.editing {
  border-color: #4f46e5;
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.12) inset;
}

/* Edit banner */
.edit-banner {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(79, 70, 229, 0.12);
  border: 1px solid rgba(79, 70, 229, 0.3);
  color: #4f46e5;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  z-index: 5;
  backdrop-filter: blur(6px);
  white-space: nowrap;
}

.edit-banner.dark {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
}

/* Detail Panel */
.detail-panel {
  width: 360px;
  flex-shrink: 0;
  border-radius: 12px;
  padding: 20px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #f0f0f0;
}

.detail-panel.dark {
  background: #1f1f1f;
  border-color: #303030;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.detail-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 22px;
  flex-shrink: 0;
}

.detail-header h4 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
}

.detail-section {
  margin-bottom: 16px;
}

.detail-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.5;
  margin-bottom: 8px;
}

.detail-text {
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.io-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-code {
  font-size: 12px;
  line-height: 1.5;
  padding: 12px;
  border-radius: 8px;
  background: #f5f5f5;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.detail-code.dark {
  background: #141414;
  color: #d4d4d4;
}

.detail-code.error {
  color: #ef4444;
}

.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  opacity: 0.4;
}

.detail-empty p {
  margin: 12px 0 0 0;
  font-size: 14px;
}

/* Legend */
.workflow-legend {
  position: absolute;
  bottom: 16px;
  right: 16px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.workflow-legend.dark {
  background: rgba(31, 31, 31, 0.9);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Execution Summary */
.execution-summary {
  position: absolute;
  top: 16px;
  left: 16px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 10px;
  padding: 12px 16px;
  z-index: 5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  max-width: 70%;
}

.execution-summary.dark {
  background: rgba(31, 31, 31, 0.95);
}

.exec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.exec-label {
  font-weight: 600;
  font-size: 13px;
}

.exec-duration {
  margin-left: auto;
  font-size: 13px;
  font-weight: 600;
  color: #4f46e5;
}

.exec-steps {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.exec-step-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1.5px solid;
  border-radius: 6px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.6);
}

.execution-summary.dark .exec-step-tag {
  background: rgba(255, 255, 255, 0.05);
}

.step-name {
  font-weight: 500;
}

.step-duration {
  font-size: 11px;
  opacity: 0.6;
}

.step-arrow {
  font-size: 10px;
  opacity: 0.4;
  margin-left: 2px;
}

/* Vue Flow node cursor */
:deep(.vue-flow__node) {
  cursor: pointer;
}
</style>

<!-- Global styling (not scoped) -->
<style>
/* Selected node outline */
.vue-flow__node.node-selected .wf-node {
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.2), 0 4px 16px rgba(0, 0, 0, 0.15) !important;
  transform: scale(1.05);
}

/* Edge labels */
.vue-flow__edge-text {
  font-size: 11px;
}

/* Dark mode for vue flow background */
.vue-flow {
  background: #fafafa;
}

/* Selected edge highlight */
.vue-flow__edge.selected .vue-flow__edge-path {
  stroke: #8b5cf6 !important;
  stroke-width: 2.5px !important;
}
</style>
