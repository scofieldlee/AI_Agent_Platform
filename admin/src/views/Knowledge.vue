<template>
  <div>
    <a-row :gutter="[16, 16]">
      <!-- KB List -->
      <a-col :xs="24" :lg="8">
        <a-card title="知识库列表">
          <template #extra>
            <a-button type="primary" size="small" @click="showCreate = true">新建</a-button>
          </template>
          <a-list :data-source="knowledgeBases" :loading="loading" size="small">
            <template #renderItem="{ item }">
              <a-list-item @click="selectKB(item)" style="cursor: pointer;"
                :style="{ background: selectedKB?.id === item.id ? '#f0f5ff' : '' }">
                <a-list-item-meta>
                  <template #title>{{ item.name }}</template>
                  <template #description>
                    {{ item.document_count || 0 }} 文档 · {{ item.chunk_count || 0 }} 分块
                    <br><span style="font-size: 12px; color: #999;">{{ item.source_path }}</span>
                  </template>
                </a-list-item-meta>
                <template #actions>
                  <a-button size="small" type="link" @click.stop="syncKB(item)">同步</a-button>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>

      <!-- Documents -->
      <a-col :xs="24" :lg="16">
        <a-card :title="selectedKB ? `${selectedKB.name} - 文档列表` : '文档列表'">
          <a-table :columns="docColumns" :data-source="documents" :loading="docLoading" row-key="id"
            :pagination="{ pageSize: 10 }" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="record.status === 'ready' ? 'green' : 'orange'">{{ docStatusLabel(record.status) }}</a-tag>
              </template>
              <template v-if="column.key === 'created_at'">
                {{ formatDate(record.created_at) }}
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>

    <!-- Create KB Modal -->
    <a-modal v-model:open="showCreate" title="新建知识库" @ok="createKB" :confirm-loading="creating">
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="createForm.name" placeholder="知识库名称" />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="createForm.kb_type">
            <a-select-option value="faq">FAQ</a-select-option>
            <a-select-option value="product">产品文档</a-select-option>
            <a-select-option value="general">通用</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="来源路径">
          <a-input v-model:value="createForm.source_path" placeholder="/path/to/obsidian/vault" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { knowledgeApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const docLoading = ref(false)
const creating = ref(false)
const knowledgeBases = ref<any[]>([])
const documents = ref<any[]>([])
const selectedKB = ref<any>(null)
const showCreate = ref(false)

const createForm = reactive({ name: '', kb_type: 'faq', source_type: 'obsidian', source_path: '' })

const docColumns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '分块数', dataIndex: 'chunk_count', key: 'chunk_count', width: 80 },
  { title: '创建时间', key: 'created_at', width: 160 }
]

function formatDate(d: string) { return d ? dayjs(d).format('YYYY-MM-DD HH:mm') : '-' }
function docStatusLabel(s: string) { return { ready: '就绪', indexing: '索引中', pending: '待处理', failed: '失败' }[s] || s }

async function fetchKBs() {
  loading.value = true
  try {
    const res = await knowledgeApi.list()
    knowledgeBases.value = res.data || []
    if (knowledgeBases.value.length > 0) selectKB(knowledgeBases.value[0])
  } finally { loading.value = false }
}

async function selectKB(kb: any) {
  selectedKB.value = kb
  docLoading.value = true
  documents.value = []
  try {
    const res = await knowledgeApi.documents(kb.id)
    documents.value = res.data || []
  } finally { docLoading.value = false }
}

async function syncKB(kb: any) {
  try {
    await knowledgeApi.sync(kb.id)
    message.success(`知识库 "${kb.name}" 同步已触发`)
    setTimeout(() => fetchKBs(), 2000)
  } catch {}
}

async function createKB() {
  if (!createForm.name || !createForm.source_path) { message.warning('请填写名称和来源路径'); return }
  creating.value = true
  try {
    await knowledgeApi.create({ ...createForm })
    message.success('知识库创建成功')
    showCreate.value = false
    createForm.name = ''; createForm.source_path = ''
    fetchKBs()
  } finally { creating.value = false }
}

onMounted(() => fetchKBs())
</script>
