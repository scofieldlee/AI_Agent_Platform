<template>
  <div>
    <!-- Search Bar -->
    <a-card style="margin-bottom: 16px;">
      <a-space wrap>
        <a-input-search v-model:value="searchQuery" placeholder="语义搜索记忆..." style="width: 300px"
          enter-button @search="doSearch" />
        <a-select v-model:value="filterType" style="width: 140px" allowClear placeholder="类型" @change="fetchMemories">
          <a-select-option value="">全部类型</a-select-option>
          <a-select-option value="preference">偏好</a-select-option>
          <a-select-option value="fact">事实</a-select-option>
          <a-select-option value="behavior">行为</a-select-option>
          <a-select-option value="history">历史</a-select-option>
          <a-select-option value="skill">技能</a-select-option>
        </a-select>
      </a-space>
    </a-card>

    <!-- Search Results -->
    <a-card v-if="searchResults.length > 0" title="搜索结果" style="margin-bottom: 16px;">
      <template #extra>
        <a-button size="small" @click="clearSearch">清除</a-button>
      </template>
      <a-list :data-source="searchResults" size="small">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                <a-tag :color="typeColor(item.memory_type)">{{ typeLabel(item.memory_type) }}</a-tag>
                {{ item.content }}
              </template>
              <template #description>
                相似度: {{ (item.similarity * 100).toFixed(1) }}% · 重要度: {{ item.importance }}
              </template>
            </a-list-item-meta>
          </a-list-item>
        </template>
      </a-list>
    </a-card>

    <!-- Memory Table -->
    <a-card title="记忆列表">
      <a-table :columns="columns" :data-source="memories" :loading="loading" row-key="id"
        :pagination="pagination" @change="handleTableChange" size="middle">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'memory_type'">
            <a-tag :color="typeColor(record.memory_type)">{{ typeLabel(record.memory_type) }}</a-tag>
          </template>
          <template v-if="column.key === 'importance'">
            <a-rate :value="Math.round(record.importance * 5)" disabled :count="5" style="font-size: 12px;" />
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="record.status === 'active' ? 'green' : 'default'">
              {{ record.status === 'active' ? '活跃' : '已归档' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'action'">
            <a-popconfirm title="确定删除？" @confirm="deleteMemory(record.id)">
              <a-button size="small" type="link" danger>删除</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { memoriesApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const memories = ref<any[]>([])
const searchResults = ref<any[]>([])
const searchQuery = ref('')
const filterType = ref('')

const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

const columns = [
  { title: '类型', key: 'memory_type', width: 90 },
  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
  { title: '重要度', key: 'importance', width: 120 },
  { title: '状态', key: 'status', width: 80 },
  { title: '访问次数', dataIndex: 'access_count', key: 'access_count', width: 90 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 80 }
]

function typeColor(t: string) { return { preference: 'purple', fact: 'blue', behavior: 'cyan', history: 'orange', skill: 'green' }[t] || 'default' }
function typeLabel(t: string) { return { preference: '偏好', fact: '事实', behavior: '行为', history: '历史', skill: '技能' }[t] || t }
function formatDate(d: string) { return d ? dayjs(d).format('YYYY-MM-DD HH:mm') : '-' }

async function fetchMemories() {
  loading.value = true
  try {
    const params: any = { page: pagination.current, size: pagination.pageSize }
    if (filterType.value) params.memory_type = filterType.value
    const res = await memoriesApi.list(params)
    memories.value = res.data.items || []
    if (res.data.total !== undefined) pagination.total = res.data.total
  } catch {
    memories.value = []
  } finally { loading.value = false }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current; pagination.pageSize = pag.pageSize
  fetchMemories()
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  try {
    const res = await memoriesApi.search(searchQuery.value)
    searchResults.value = res.data || []
  } catch {}
}

function clearSearch() { searchResults.value = []; searchQuery.value = '' }

async function deleteMemory(id: number) {
  try {
    await memoriesApi.delete(id)
    message.success('已删除')
    fetchMemories()
  } catch {}
}

onMounted(() => fetchMemories())
</script>
