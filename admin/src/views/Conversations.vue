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
            <div v-for="msg in messages" :key="msg.id" style="margin-bottom: 16px;">
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
                </div>
              </div>
            </div>
          </div>
          <a-empty v-else description="选择对话查看消息" style="padding: 100px 0;" />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { conversationsApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const conversations = ref<any[]>([])
const messages = ref<any[]>([])
const selectedId = ref<string>('')

function formatDate(d: string) { return d ? dayjs(d).format('MM-DD HH:mm') : '-' }
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

onMounted(() => fetchConversations())
</script>
