<template>
  <div
    class="wf-node"
    :class="[
      `cat-${data.category}`,
      data.isExecuted ? 'executed' : '',
      hasTrace && !data.isExecuted ? 'dimmed' : '',
      data.editable ? 'editable' : '',
    ]"
    :style="{ '--cat-color': data.color }"
  >
    <!-- Connect handles (edit mode only) -->
    <Handle v-if="data.editable" type="target" :position="Position.Left" class="wf-handle" />
    <Handle v-if="data.editable" type="source" :position="Position.Right" class="wf-handle" />

    <!-- Node Header -->
    <div class="wf-node-header">
      <component :is="iconComp" class="wf-node-icon" />
      <span class="wf-node-title">{{ data.label }}</span>
    </div>

    <!-- Execution Badge -->
    <div v-if="data.isExecuted" class="wf-node-badge">
      <CheckCircleFilled v-if="data.stepStatus === 'success'" class="badge-icon success" />
      <CloseCircleFilled v-else-if="data.stepStatus === 'error' || data.stepStatus === 'failed'" class="badge-icon error" />
      <LoadingOutlined v-else class="badge-icon running" />
      <span class="badge-duration">{{ data.durationMs ? data.durationMs + 'ms' : '-' }}</span>
    </div>

    <!-- Category Tag -->
    <div class="wf-node-category">{{ categoryLabel }}</div>

    <!-- Edit-mode type badge -->
    <div v-if="data.editable" class="wf-node-type">
      <span class="type-key">{{ data.nodeType }}</span>
    </div>

    <!-- Hover indicator -->
    <div class="wf-node-hover-hint">
      <template v-if="!data.editable">
        <InfoCircleOutlined /> 点击查看详情
      </template>
      <template v-else>
        <EditOutlined /> 点击配置 · 拖动连线
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined,
  InfoCircleOutlined,
  EditOutlined,
  AimOutlined,
  SearchOutlined,
  DatabaseOutlined,
  ToolOutlined,
  RobotOutlined,
  CustomerServiceOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons-vue'

const props = defineProps<{
  id: string
  data: {
    label: string
    category: string
    color: string
    description: string
    inputs: string[]
    outputs: string[]
    type: string
    nodeType: string
    config: Record<string, any>
    editable: boolean
    isExecuted: boolean
    hasTrace: boolean
    durationMs?: number
    stepStatus?: string
  }
}>()

const categoryIcons: Record<string, any> = {
  intent: AimOutlined,
  retrieval: SearchOutlined,
  tool: ToolOutlined,
  model: RobotOutlined,
  human: CustomerServiceOutlined,
}

const iconComp = computed(() => categoryIcons[props.data.category] || NodeIndexOutlined)

const categoryLabels: Record<string, string> = {
  intent: '意图分类',
  retrieval: '检索',
  tool: '工具执行',
  model: 'LLM 生成',
  human: '转人工',
}

const categoryLabel = computed(() => categoryLabels[props.data.category] || props.data.category)

// Whether a trace is loaded (for dimming non-executed nodes)
const hasTrace = computed(() => props.data.hasTrace)
</script>

<style scoped>
.wf-node {
  width: 160px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 2px solid var(--cat-color, #6b7280);
  background: color-mix(in srgb, var(--cat-color, #6b7280) 8%, transparent);
  text-align: center;
  position: relative;
  transition: all 0.2s ease;
  cursor: pointer;
}

.wf-node:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.wf-node.editable {
  cursor: grab;
}

.wf-node.editable:active {
  cursor: grabbing;
}

.wf-node-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-bottom: 4px;
}

.wf-node-icon {
  font-size: 16px;
  color: var(--cat-color, #6b7280);
}

.wf-node-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cat-color, #6b7280);
}

.wf-node-category {
  font-size: 10px;
  opacity: 0.5;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Edit-mode type badge */
.wf-node-type {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(128, 128, 128, 0.25);
}

.type-key {
  font-size: 10px;
  font-family: monospace;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.12);
  color: var(--cat-color, #6b7280);
}

/* Connection handles */
.wf-handle {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--cat-color, #6b7280);
  border: 2px solid #fff;
  transition: transform 0.15s ease;
}

:global(.dark) .wf-handle {
  border-color: #1f1f1f;
}

.wf-handle:hover {
  transform: scale(1.4);
}

/* Execution badge */
.wf-node-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  display: flex;
  align-items: center;
  gap: 2px;
  background: #fff;
  border-radius: 10px;
  padding: 2px 6px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  font-size: 11px;
  font-weight: 600;
}

:global(.dark) .wf-node-badge {
  background: #1f1f1f;
}

.badge-icon {
  font-size: 12px;
}

.badge-icon.success {
  color: #10b981;
}

.badge-icon.error {
  color: #ef4444;
}

.badge-icon.running {
  color: #3b82f6;
}

.badge-duration {
  color: #4f46e5;
}

/* Executed state */
.wf-node.executed {
  border-width: 3px;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--cat-color) 15%, transparent);
}

/* Dimmed state (not in execution path) */
.wf-node.dimmed {
  opacity: 0.3;
}

/* Hover hint (hidden by default, shown on hover) */
.wf-node-hover-hint {
  position: absolute;
  bottom: -22px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  opacity: 0;
  transition: opacity 0.2s;
  white-space: nowrap;
  color: #6b7280;
}

.wf-node:hover .wf-node-hover-hint {
  opacity: 0.6;
}
</style>
