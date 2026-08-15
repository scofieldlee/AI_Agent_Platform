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
                  <a-button size="small" type="link" @click.stop="openImport(item)">导入</a-button>
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

    <!-- Import Excel Modal -->
    <a-modal v-model:open="showImport" :title="`导入 Excel - ${importTarget?.name || ''}`"
      @ok="doImport" :confirm-loading="importing" ok-text="开始导入">
      <a-alert type="info" show-icon style="margin-bottom: 16px;">
        <template #message>
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <span>支持 .xlsx / .xlsm / .csv（≤20MB）。首行为表头，<b>每一行数据</b>会作为一个检索单元（保留"列名: 值"结构）向量化入库。</span>
            <a type="link" @click="downloadTemplate" :disabled="!importTarget" style="white-space: nowrap;">下载示例模板</a>
          </div>
        </template>
      </a-alert>
      <a-upload-dragger :file-list="importFiles" :max-count="1" accept=".xlsx,.xlsm,.csv"
        :before-upload="pickImportFile" @remove="() => (importFiles = [])">
        <p class="ant-upload-drag-icon"><inbox-outlined /></p>
        <p class="ant-upload-text">点击或拖拽文件到此处</p>
        <p class="ant-upload-hint">重复导入相同文件会自动跳过；文件内容变化时更新原文档</p>
      </a-upload-dragger>
      <div v-if="importResult" style="margin-top: 16px;">
        <a-alert :type="importResult.action === 'skipped' ? 'warning' : 'success'" show-icon>
          <template #message>
            <template v-if="importResult.action === 'skipped'">文件内容未变化，已跳过（{{ importResult.chunks }} 个分块已是最新）</template>
            <template v-else>
              导入成功：{{ importResult.sheets.join('、') }} · 共 {{ importResult.rows }} 行 →
              {{ importResult.chunks }} 个分块已向量化
            </template>
          </template>
        </a-alert>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { InboxOutlined } from '@ant-design/icons-vue'
import { knowledgeApi } from '@/api/client'
import dayjs from 'dayjs'

const loading = ref(false)
const docLoading = ref(false)
const creating = ref(false)
const knowledgeBases = ref<any[]>([])
const documents = ref<any[]>([])
const selectedKB = ref<any>(null)
const showCreate = ref(false)

// Excel import state
const showImport = ref(false)
const importing = ref(false)
const importTarget = ref<any>(null)
const importFiles = ref<any[]>([])
const importResult = ref<any>(null)

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

function openImport(kb: any) {
  importTarget.value = kb
  importFiles.value = []
  importResult.value = null
  showImport.value = true
}

function pickImportFile(file: File) {
  if (file.size > 20 * 1024 * 1024) {
    message.error('文件超过 20MB 限制')
    return false
  }
  importFiles.value = [{ uid: '-1', name: file.name, status: 'done', originFileObj: file }]
  importResult.value = null
  return false  // prevent auto upload
}

async function doImport() {
  const file = importFiles.value[0]?.originFileObj
  if (!file) { message.warning('请先选择要导入的文件'); return }
  importing.value = true
  importResult.value = null
  try {
    const res = await knowledgeApi.importFile(importTarget.value.id, file)
    importResult.value = res.data
    if (res.data?.action !== 'skipped') {
      message.success(`导入成功：${res.data?.rows ?? 0} 行 → ${res.data?.chunks ?? 0} 个分块`)
    }
    fetchKBs()
    if (selectedKB.value?.id === importTarget.value.id) selectKB(importTarget.value)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '导入失败，请检查文件格式')
  } finally { importing.value = false }
}

async function downloadTemplate() {
  if (!importTarget.value) return
  try {
    const res = await knowledgeApi.downloadTemplate(importTarget.value.id)
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    })
    const url = URL.createObjectURL(blob)
    const filename = importTarget.value.code
      ? `${importTarget.value.code}_import_template.xlsx`
      : 'knowledge_import_template.xlsx'
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    message.error('模板下载失败')
  }
}

onMounted(() => fetchKBs())
</script>
