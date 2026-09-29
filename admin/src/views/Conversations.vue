<template>
  <div>
    <a-row :gutter="16">
      <!-- Conversation List -->
      <a-col :xs="24" :lg="10">
        <a-card title="对话列表" :loading="loading">
          <a-list :data-source="conversations" size="small">
            <template #renderItem="{ item }">
              <a-list-item @click="selectConversation(item)" style="cursor: pointer;"
                :style="{ background: selectedId === item.id ? '#f0f5ff' : '' }">
                <a-list-item-meta>
                  <template #title>
                    <span>{{ item.title || `对话 #${item.id}` }}</span>
                  </template>
                  <template #description>
                    <span>{{ item.message_count || 0 }} 条消息</span>
                    <a-tag v-if="item.is_transferred" color="orange" style="margin-left: 8px;">已转人工</a-tag>
                  </template>
                </a-list-item-meta>
                <template #actions>
                  <span style="color: #999; font-size: 12px;">{{ formatDate(item.created_at) }}</span>
                </template>
              </a-list-item>
            </template>
            <template #footer>
              <div v-if="conversations.length === 0" style="text-align: center; padding: 20px;">
                <a-empty description="暂无对话" />
              </div>
            </template>
          </a-list>
        </a-card>
      </a-col>

      <!-- Messages -->
      <a-col :xs="24" :lg="14">
        <a-card :title="selectedId ? `消息详情 #${selectedId}` : '消息详情'">
          <div v-if="messages.length > 0" style="max-height: 600px; overflow-y: auto;">
            <div v-for="(msg, idx) in messages" :key="msg.id" style="margin-bottom: 16px;">
              <div :style="{
                display: 'flex',
                justifyContent: msg.sender_type === 'user' ? 'flex-start' : 'flex-end'
              }">
                <div :style="{
                  maxWidth: '75%',
                  padding: '10px 14px',
                  borderRadius: '12px',
                  background: msg.sender_type === 'user' ? '#f0f0f0' : '#4f46e5',
                  color: msg.sender_type === 'user' ? '#333' : '#fff'
                }">
                  <div style="font-size: 11px; opacity: 0.7; margin-bottom: 4px;">
                    {{ senderLabel(msg.sender_type) }} · {{ formatDate(msg.created_at) }}
                  </div>
                  <div style="white-space: pre-wrap;">{{ msg.content }}</div>
                  <div v-if="msg.meta" style="margin-top: 6px;">
                    <a-tag v-if="msg.meta.intent" size="small">{{ msg.meta.intent }}</a-tag>
                    <a-tag v-if="msg.meta.confidence" size="small">
                      {{ (msg.meta.confidence * 100).toFixed(0) }}%
                    </a-tag>
                    <a-tag v-if="msg.meta.ticket_number" color="orange" size="small">
                      {{ msg.meta.ticket_number }}
                    </a-tag>
                  </div>
                  <!-- 沉淀知识按钮：仅 AI 回复 -->
                  <div v-if="msg.sender_type === 'agent' && msg.content" style="margin-top: 8px; text-align: right;">
                    <a-button size="small" ghost style="color: #fff; border-color: rgba(255,255,255,0.5);"
                      @click="openSediment(idx)">
                      <BookOutlined /> 沉淀知识
                    </a-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <a-empty v-else description="选择对话查看消息" style="padding: 100px 0;" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 沉淀知识弹窗 -->
    <a-modal v-model:open="sedimentOpen" title="沉淀知识 — 人工编辑后提交草稿" width="640px"
      :confirm-loading="submitting" ok-text="提交草稿" @ok="submitSediment">
      <a-alert type="info" show-icon style="margin-bottom: 12px;"
        message="AI 起草，人来定稿：请将问答改写为独立可懂的知识条目，提交后需在「知识库 → 对话沉淀」中发布才会生效。" />
      <a-form layout="vertical">
        <a-form-item label="目标知识库" required>
          <a-select v-model:value="sedimentForm.kbId" :options="kbOptions" placeholder="选择知识库" />
        </a-form-item>
        <a-form-item label="问题（编辑后）" required>
          <a-textarea v-model:value="sedimentForm.question" :rows="2" placeholder="独立、明确的问题表述" />
        </a-form-item>
        <a-form-item label="答案（编辑后）" required>
          <a-textarea v-model:value="sedimentForm.answer" :rows="6" placeholder="去上下文化的完整答案" />
        </a-form-item>
        <a-collapse ghost>
          <a-collapse-panel key="src" header="原始内容（AI 起草，只读参考）">
            <div style="font-size: 12px; color: #666;">
              <div style="margin-bottom: 6px;"><b>用户原问：</b>{{ sedimentForm.originalQuestion || '—' }}</div>
              <div style="white-space: pre-wrap;"><b>AI 原答：</b>{{ sedimentForm.originalAnswer || '—' }}</div>
            </div>
          </a-collapse-panel>
        </a-collapse>
        <a-form-item label="编辑说明（选填）">
          <a-input v-model:value="sedimentForm.editNote" placeholder="例如：合并了两轮对话、修正了型号口误" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { BookOutlined } from '@ant-design/icons-vue'
import { conversationsApi, knowledgeApi } from '@/api/client'
import { formatTime } from '@/utils/time'

const loading = ref(false)
const conversations = ref<any[]>([])
const messages = ref<any[]>([])
const selectedId = ref<string>('')

const sedimentOpen = ref(false)
const submitting = ref(false)
const kbOptions = ref<any[]>([])
const sedimentForm = ref({
  kbId: undefined as number | undefined,
  question: '',
  answer: '',
  originalQuestion: '',
  originalAnswer: '',
  conversationId: undefined as number | undefined,
  messageId: undefined as number | undefined,
  agentId: undefined as number | undefined,
  editNote: ''
})

function formatDate(d: string) { return formatTime(d, 'short') }
function senderLabel(t: string) {
  return { user: '用户', agent: 'AI Agent', human: '人工客服', system: '系统' }[t] || t
}

async function fetchConversations() {
  loading.value = true
  try {
    const res = await conversationsApi.list({ limit: 50 })
    conversations.value = res.data || []
    if (conversations.value.length > 0) selectConversation(conversations.value[0])
  } finally { loading.value = false }
}

async function selectConversation(conv: any) {
  selectedId.value = conv.id
  messages.value = []
  try {
    const res = await conversationsApi.messages(conv.id)
    messages.value = res.data || []
  } catch {}
}

async function fetchKbOptions() {
  try {
    const res = await knowledgeApi.list()
    kbOptions.value = (res.data || []).map((kb: any) => ({ value: kb.id, label: kb.name }))
    // 默认选中「训练知识库」
    const training = (res.data || []).find((kb: any) => kb.code === 'training_kb')
    sedimentForm.value.kbId = training ? training.id : kbOptions.value[0]?.value
  } catch { kbOptions.value = [] }
}

function openSediment(idx: number) {
  const aiMsg = messages.value[idx]
  // 向前找最近的用户消息作为「原问题」
  let userQuestion = ''
  for (let i = idx - 1; i >= 0; i--) {
    if (messages.value[i].sender_type === 'user') {
      userQuestion = messages.value[i].content
      break
    }
  }
  sedimentForm.value.originalQuestion = userQuestion
  sedimentForm.value.originalAnswer = aiMsg.content
  // 预填：问题=用户原问，答案=AI 原答（人工改写）
  sedimentForm.value.question = userQuestion
  sedimentForm.value.answer = aiMsg.content
  sedimentForm.value.conversationId = aiMsg.conversation_id ?? (selectedId.value ? Number(selectedId.value) : undefined)
  sedimentForm.value.messageId = aiMsg.id
  sedimentForm.value.agentId = aiMsg.agent_id ?? undefined
  sedimentForm.value.editNote = ''
  sedimentOpen.value = true
}

async function submitSediment() {
  const f = sedimentForm.value
  if (!f.kbId) { message.error('请选择目标知识库'); return }
  if (!f.question.trim() || !f.answer.trim()) { message.error('问题与答案不能为空'); return }
  submitting.value = true
  try {
    await knowledgeApi.qaSediment.submit({
      knowledge_base_id: f.kbId,
      question: f.question,
      answer: f.answer,
      original_question: f.originalQuestion,
      original_answer: f.originalAnswer,
      conversation_id: f.conversationId,
      message_id: f.messageId,
      agent_id: f.agentId,
      edit_note: f.editNote || undefined
    })
    message.success('已提交草稿，请到「知识库 → 对话沉淀」中发布')
    sedimentOpen.value = false
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '提交失败')
  } finally { submitting.value = false }
}

onMounted(() => { fetchConversations(); fetchKbOptions() })
</script>
