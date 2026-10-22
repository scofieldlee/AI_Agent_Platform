<template>
  <div class="agents-page">
    <!-- Agent List -->
    <a-card title="Agent 列表">
      <template #extra>
        <a-space>
          <a-tag color="blue">{{ agents.length }} 个 Agent</a-tag>
          <a-button type="primary" size="small" @click="showCreateModal = true">
            <PlusOutlined /> 新建 Agent
          </a-button>
        </a-space>
      </template>
      <a-table
        :columns="columns"
        :data-source="agents"
        :loading="loading"
        row-key="id"
        :pagination="false"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-space>
              <a-avatar :size="36" style="background-color: #4f46e5;">{{ record.name?.charAt(0) }}</a-avatar>
              <div>
                <div style="font-weight: 600;">{{ record.name }}</div>
                <div style="font-size: 12px; color: #999;">{{ record.code }}</div>
              </div>
            </a-space>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'agent_type'">
            {{ typeLabel(record.agent_type) }}
          </template>
          <template v-if="column.key === 'created_by_name'">
            <span v-if="record.created_by_name">{{ record.created_by_name }}</span>
            <a-tag v-else color="default" style="font-size: 11px;">公共</a-tag>
          </template>
          <template v-if="column.key === 'version'">
            <a-tag color="blue">v{{ record.version }}</a-tag>
          </template>
          <template v-if="column.key === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
          </template>
          <template v-if="column.key === 'chat_link'">
            <div v-if="record.chat_token && record.status === 'published'" style="display: flex; align-items: center; gap: 4px;">
              <a-tooltip :title="`/chat?token=${record.chat_token}`">
                <a-button type="link" size="small" @click="openChatUrl(record.chat_token)">
                  <LinkOutlined /> 打开对话
                </a-button>
              </a-tooltip>
              <a-button type="text" size="small" @click="copyChatUrl(record.chat_token)">
                <CopyOutlined />
              </a-button>
            </div>
            <span v-else style="font-size: 12px; color: #999;">未发布</span>
          </template>
          <template v-if="column.key === 'workflow'">
            <a-tooltip v-if="record.workflow" :title="`工作流编码: ${record.workflow.code}`">
              <a-tag color="geekblue" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ record.workflow.name }}
              </a-tag>
            </a-tooltip>
            <span v-else style="font-size: 12px; color: #999;">默认</span>
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openTestModal(record)">
                <MessageOutlined /> 测试
              </a-button>
              <a-button type="link" size="small" @click="openConfigPage(record)">
                <EditOutlined /> 配置
              </a-button>
              <a-button type="link" size="small" @click="openShareModal(record)">
                <ShareAltOutlined /> 授权
              </a-button>
              <a-popconfirm
                v-if="record.status !== 'published'"
                title="确定要删除这个 Agent 吗？"
                ok-text="删除"
                cancel-text="取消"
                ok-type="danger"
                @confirm="handleDelete(record)"
              >
                <a-button type="link" size="small" danger>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-popconfirm>
              <a-tooltip v-else title="已发布的 Agent 不能删除，请先取消发布">
                <a-button type="link" size="small" danger disabled>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Share Modal -->
    <a-modal
      v-model:open="shareModalOpen"
      :title="shareModalAgent ? `成员授权 — ${shareModalAgent.name}` : '成员授权'"
      width="680px"
      :footer="null"
      :destroy-on-close="true"
    >
      <ResourceShareSection
        v-if="shareModalOpen && shareModalAgent"
        resource-type="agent"
        :resource-id="shareModalAgent.id"
        resource-label="Agent"
      />
    </a-modal>

    <!-- Test Chat Modal -->
    <a-modal
      v-model:open="testModalVisible"
      :title="selectedAgentForTest ? `快速测试 — ${selectedAgentForTest.name}` : '快速测试'"
      width="720px"
      :footer="null"
      :destroy-on-close="false"
    >
      <div class="test-chat">
        <div class="chat-messages" ref="chatMessagesRef">
          <div v-if="testMessages.length === 0" class="chat-empty">
            <div style="color: #999; font-size: 13px;">
              向 <strong>{{ selectedAgentForTest?.name }}</strong> 发送消息开始测试
            </div>
          </div>
          <div v-for="msg in testMessages" :key="msg.id" :class="['chat-msg', msg.role]">
            <div class="chat-bubble" :class="{ 'chat-error': msg.meta?.error }">
              <div class="chat-role">{{ msg.role === 'user' ? '顾客' : 'Agent' }}</div>
              <div class="chat-text">{{ msg.content }}</div>
              <div v-if="msg.meta" class="chat-meta">
                <a-tag v-if="msg.meta.intent" size="small" color="blue">{{ msg.meta.intent }}</a-tag>
                <a-tag v-if="msg.meta.confidence !== undefined" size="small">
                  置信度 {{ (msg.meta.confidence * 100).toFixed(0) }}%
                </a-tag>
                <a-tag v-if="msg.meta.need_human" size="small" color="red">转人工</a-tag>
              </div>
            </div>
          </div>
          <div v-if="testLoading" class="chat-msg agent">
            <div class="chat-bubble">
              <a-spin size="small" />
              <span style="margin-left: 8px; color: #999;">Agent 思考中...</span>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <a-input-search
            v-model:value="testInput"
            placeholder="输入测试消息..."
            enter-button="发送"
            :loading="testLoading"
            @search="sendTestMessage"
          />
        </div>
      </div>
    </a-modal>

    <!-- Create Agent Modal -->
    <a-modal v-model:open="showCreateModal" title="新建 Agent" @ok="handleCreate" :confirm-loading="creating">
      <a-form layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="newAgent.name" placeholder="如：售后客服 Agent" />
        </a-form-item>
        <a-form-item label="编码" required>
          <a-input v-model:value="newAgent.code" placeholder="如：after_sale_agent" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="newAgent.description" :rows="2" placeholder="Agent 描述" />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="newAgent.agent_type">
            <a-select-option value="customer_service">客服</a-select-option>
            <a-select-option value="config">配置型</a-select-option>
            <a-select-option value="assistant">助手</a-select-option>
            <a-select-option value="analyst">分析</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, MessageOutlined,
  ExclamationCircleOutlined,
  LinkOutlined, CopyOutlined,
  ShareAltOutlined,
} from '@ant-design/icons-vue'
import { agentsApi } from '@/api/client'
import { formatTime } from '@/utils/time'
import ResourceShareSection from '@/components/ResourceShareSection.vue'

// --- Agent list ---
const loading = ref(false)
const agents = ref<any[]>([])
const columns = [
  { title: 'Agent', key: 'name', width: 250 },
  { title: '类型', key: 'agent_type', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '创建者', key: 'created_by_name', width: 110 },
  { title: '工作流', key: 'workflow', width: 160 },
  { title: '版本', key: 'version', width: 80 },
  { title: '启用', key: 'is_active', width: 80 },
  { title: '对话链接', key: 'chat_link', width: 180 },
  { title: '操作', key: 'action', width: 250 },
]

// --- Test chat ---
const testModalVisible = ref(false)
const selectedAgentForTest = ref<any>(null)
const testMessages = ref<any[]>([])
const testInput = ref('')
const testLoading = ref(false)
const chatMessagesRef = ref<HTMLElement>()

// --- Create modal ---
const showCreateModal = ref(false)
const creating = ref(false)
const newAgent = reactive({ name: '', code: '', description: '', agent_type: 'customer_service' })

function statusColor(s: string) {
  return ({ active: 'green', published: 'green', running: 'green', draft: 'orange', suspended: 'default', archived: 'red' } as any)[s] || 'default'
}
function statusLabel(s: string) {
  return ({ active: '运行中', published: '已发布', running: '运行中', draft: '草稿', suspended: '已暂停', archived: '已归档' } as any)[s] || s
}
function typeLabel(t: string) {
  return ({ customer_service: '客服', config: '配置型', assistant: '助手', analyst: '分析', custom: '自定义' } as any)[t] || t
}

function openConfigPage(agent: any) {
  // 配置项较多，新窗口整页打开（Tab 分区），不占用列表页
  window.open(`/agents/${agent.id}/config`, '_blank')
}

function getChatUrl(token: string) {
  const origin = window.location.origin
  // Admin runs on :5173, chat page is on :8000
  const chatOrigin = origin.replace(':5173', ':8000')
  return `${chatOrigin}/chat?token=${token}`
}

function openChatUrl(token: string) {
  window.open(getChatUrl(token), '_blank')
}

async function copyChatUrl(token: string) {
  const url = getChatUrl(token)
  try {
    await navigator.clipboard.writeText(url)
    message.success('对话链接已复制')
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement('textarea')
    textarea.value = url
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    message.success('对话链接已复制')
  }
}

async function fetchAgents() {
  loading.value = true
  try {
    const res = await agentsApi.list()
    agents.value = res.data || []
  } finally {
    loading.value = false
  }
}


function openTestModal(agent: any) {
  selectedAgentForTest.value = agent
  testMessages.value = []
  testInput.value = ''
  testModalVisible.value = true
}

// --- 成员授权弹窗 ---
const shareModalOpen = ref(false)
const shareModalAgent = ref<any>(null)
function openShareModal(agent: any) {
  shareModalAgent.value = agent
  shareModalOpen.value = true
}


async function sendTestMessage() {
  if (!testInput.value.trim() || !selectedAgentForTest.value) return
  const userMsg = testInput.value.trim()
  testInput.value = ''

  testMessages.value.push({
    id: Date.now(),
    role: 'user',
    content: userMsg,
  })

  testLoading.value = true
  await nextTick()
  if (chatMessagesRef.value) {
    chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }

  try {
    const res = await fetch('/api/v1/conversations/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        user_id: 1,
        agent_id: selectedAgentForTest.value.id,
        message: userMsg,
      }),
    })

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}))
      const detail = errorData.detail || ''
      let friendlyMsg = detail || `请求失败 (HTTP ${res.status})`
      if (res.status === 404) friendlyMsg = 'Agent 不存在或已被删除，请重新选择'
      else if (res.status === 403) friendlyMsg = '该 Agent 未启用，请在配置中激活后再试'
      else if (res.status === 422) friendlyMsg = '请求参数有误，请刷新页面后重试'
      else if (res.status >= 500) friendlyMsg = 'AI 服务暂时不可用，请稍后重试。如果持续出现，请检查 DeepSeek API 状态。'
      testMessages.value.push({
        id: Date.now() + 1,
        role: 'agent',
        content: friendlyMsg,
        meta: { error: true },
      })
      return
    }

    const data = await res.json()
    testMessages.value.push({
      id: Date.now() + 1,
      role: 'agent',
      content: data.reply || '（Agent 未返回内容）',
      meta: {
        intent: data.intent,
        confidence: data.confidence,
        need_human: data.need_human,
      },
    })
  } catch (err: any) {
    testMessages.value.push({
      id: Date.now() + 1,
      role: 'agent',
      content: '网络请求失败，请检查服务是否正常运行: ' + err.message,
      meta: { error: true },
    })
  } finally {
    testLoading.value = false
    await nextTick()
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  }
}

async function handleDelete(agent: any) {
  if (agent.status === 'published') {
    message.warning('已发布的 Agent 不能删除，请先取消发布')
    return
  }
  // 删除前检查专属知识库（将随 Agent 级联删除）
  let privateKBHint = ''
  try {
    const res = await agentsApi.listPrivateKBs(agent.id)
    const kbs = res.data || []
    if (kbs.length > 0) {
      const docs = kbs.reduce((s: number, k: any) => s + (k.document_count || 0), 0)
      privateKBHint =
        `\n该 Agent 拥有 ${kbs.length} 个专属知识库（共 ${docs} 篇文档），删除 Agent 将一并删除。` +
        `\n如需保留，请先在 Agent 配置页使用「转公共」。`
    }
  } catch { /* ignore: KB 列表拉不到不阻塞删除 */ }
  Modal.confirm({
    title: `确认删除 Agent「${agent.name}」？`,
    content: privateKBHint ? `此操作不可恢复。${privateKBHint}` : '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    onOk: async () => {
      try {
        await agentsApi.delete(agent.id)
        message.success('Agent 已删除')
        await fetchAgents()
      } catch (err: any) {
        message.error('删除失败: ' + (err.response?.data?.detail || err.message))
      }
    },
  })
}

async function handleCreate() {
  if (!newAgent.name || !newAgent.code) {
    message.warning('请填写名称和编码')
    return
  }
  creating.value = true
  try {
    await agentsApi.list() // ensure token works
    // Use raw POST to create agent
    const res = await fetch('/api/v1/agents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        name: newAgent.name,
        code: newAgent.code,
        description: newAgent.description,
        agent_type: newAgent.agent_type,
        config: {},
      }),
    })
    if (!res.ok) throw new Error('创建失败')
    message.success('Agent 创建成功')
    showCreateModal.value = false
    newAgent.name = ''
    newAgent.code = ''
    newAgent.description = ''
    await fetchAgents()
  } catch (err: any) {
    message.error('创建失败: ' + err.message)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  fetchAgents()
})
</script>

<style scoped>
.agents-page {
  max-width: 100%;
}

.config-form {
  padding-bottom: 24px;
}

.config-section {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--ant-color-fill-quaternary, #f5f5f5);
  border-radius: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-primary, #4f46e5);
}

.binding-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  background: var(--ant-color-bg-container, #fff);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
  transition: all 0.2s;
}

.binding-item:hover {
  border-color: var(--ant-color-primary, #4f46e5);
}

.binding-info {
  display: inline-block;
  margin-left: 8px;
  vertical-align: top;
}

.binding-name {
  font-size: 13px;
  font-weight: 600;
}

.binding-desc {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
  line-height: 1.4;
}

/* Test chat */
.test-chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-messages {
  height: 360px;
  overflow-y: auto;
  padding: 12px;
  background: var(--ant-color-fill-tertiary, #fafafa);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
}

.chat-msg {
  display: flex;
}

.chat-msg.user {
  justify-content: flex-end;
}

.chat-msg.agent {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.chat-msg.user .chat-bubble {
  background: var(--ant-color-primary, #4f46e5);
  color: #fff;
}

.chat-msg.agent .chat-bubble {
  background: var(--ant-color-bg-container, #fff);
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}

.chat-bubble.chat-error {
  background: #fff2f0 !important;
  border: 1px solid #ffccc7 !important;
  color: #cf1322 !important;
}

.chat-role {
  font-size: 11px;
  opacity: 0.7;
  margin-bottom: 4px;
}

.chat-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-meta {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.suggestion-edit-item {
  margin-bottom: 8px;
  padding: 8px;
  background: var(--ant-color-bg-container, #fff);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}
</style>
