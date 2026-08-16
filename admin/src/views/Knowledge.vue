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
            :pagination="{ pageSize: 10 }" size="small"
            :custom-row="(record: any) => ({ onClick: () => openDocDetail(record), style: 'cursor: pointer;' })">
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
    <!-- Document Detail Drawer -->
    <a-drawer v-model:open="showDocDetail" width="860" :title="`文档详情 - ${docDetail?.title || ''}`"
      :destroy-on-close="true" :footer-style="{ textAlign: 'right' }">
      <a-spin :spinning="docDetailLoading">
        <template v-if="docDetail">
          <a-tabs v-model:active-key="docDetailTab">
            <!-- Tab 1: Chunks (default) -->
            <a-tab-pane key="chunks" :title="`分块内容 (${docDetail.chunks.length})`">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                <a-alert type="info" show-icon style="margin-bottom: 0; flex: 1; min-width: 260px;">
                  <template #message>点击「编辑全文」可直接修改整篇文档，保存后自动重新分块并向量化</template>
                </a-alert>
                <a-button type="primary" @click="openFullContentEdit">编辑全文</a-button>
              </div>
              <a-table :data-source="docDetail.chunks" :pagination="{ pageSize: 10 }" size="small" row-key="id">
                <a-table-column title="#" data-index="chunk_index" width="50" />
                <a-table-column title="小节" data-index="section" width="140">
                  <template #default="{ record }">
                    <span style="color: #999;">{{ record.section || '-' }}</span>
                  </template>
                </a-table-column>
                <a-table-column title="内容" ellipsis>
                  <template #default="{ record }">
                    <a-tooltip :title="record.content">
                      <span>{{ record.content.slice(0, 100) }}{{ record.content.length > 100 ? '…' : '' }}</span>
                    </a-tooltip>
                  </template>
                </a-table-column>
                <a-table-column title="Token" data-index="token_count" width="70" />
                <a-table-column title="操作" width="160">
                  <template #default="{ record }">
                    <a-button size="small" type="link" @click="openChunkEdit(record)">编辑</a-button>
                    <a-popconfirm title="确定删除该分块？" ok-text="删除" cancel-text="取消"
                      @confirm="deleteChunk(record)">
                      <a-button size="small" type="link" danger>删除</a-button>
                    </a-popconfirm>
                  </template>
                </a-table-column>
              </a-table>
            </a-tab-pane>

            <!-- Tab 2: Basic info -->
            <a-tab-pane key="info" title="基本信息">
              <a-form layout="vertical" style="max-width: 600px;">
                <a-form-item label="标题">
                  <a-input v-model:value="docEdit.title" />
                </a-form-item>
                <a-form-item label="来源路径">
                  <a-input v-model:value="docEdit.source_path" disabled />
                </a-form-item>
                <a-form-item label="来源类型">
                  <a-tag>{{ docDetail.source_type }}</a-tag>
                </a-form-item>
                <a-form-item label="状态">
                  <a-tag :color="docDetail.status === 'ready' ? 'green' : 'orange'">{{ docStatusLabel(docDetail.status) }}</a-tag>
                </a-form-item>
                <a-form-item label="分块数">{{ docDetail.chunk_count }}</a-form-item>
                <a-form-item label="创建时间">{{ formatDate(docDetail.created_at) }}</a-form-item>
                <a-form-item label="更新时间">{{ formatDate(docDetail.updated_at) }}</a-form-item>
                <a-form-item>
                  <a-button type="primary" :loading="docSaving" @click="saveDocBasic">保存修改</a-button>
                </a-form-item>
              </a-form>
            </a-tab-pane>

            <!-- Tab 3: Metadata -->
            <a-tab-pane key="meta" title="元数据 (frontmatter)">
              <p style="color: #999; margin-bottom: 8px;">JSON 格式，保存后会随文档一起展示给检索流程</p>
              <a-textarea v-model:value="docEdit.metaJson" :auto-size="{ minRows: 8, maxRows: 16 }"
                :status="docMetaError ? 'error' : ''" />
              <div v-if="docMetaError" style="color: #ff4d4f; margin-top: 4px;">{{ docMetaError }}</div>
              <div style="margin-top: 12px;">
                <a-button type="primary" :loading="docSaving" @click="saveDocMeta">保存元数据</a-button>
              </div>
            </a-tab-pane>
          </a-tabs>
        </template>
      </a-spin>
      <template #footer>
        <a-popconfirm title="确定删除整个文档及其所有分块？此操作不可恢复" ok-text="删除" cancel-text="取消"
          @confirm="deleteDoc">
          <a-button danger>删除整个文档</a-button>
        </a-popconfirm>
        <a-button style="margin-left: 8px;" @click="showDocDetail = false">关闭</a-button>
      </template>
    </a-drawer>

    <!-- Edit Chunk Modal -->
    <a-modal v-model:open="showChunkEdit" title="编辑分块" @ok="saveChunk" :confirm-loading="chunkSaving"
      ok-text="保存">
      <a-alert type="info" show-icon style="margin-bottom: 12px;">
        <template #message>保存后会自动重新生成 embedding，检索会立即生效</template>
      </a-alert>
      <a-form layout="vertical">
        <a-form-item label="小节">
          <a-input v-model:value="chunkEdit.section" placeholder="可选，如：商品基础信息" />
        </a-form-item>
        <a-form-item label="内容">
          <a-textarea v-model:value="chunkEdit.content" :auto-size="{ minRows: 8, maxRows: 20 }" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Edit Full Content Modal -->
    <a-modal v-model:open="showFullContentEdit" title="编辑全文" @ok="saveFullContent" :confirm-loading="fullContentSaving"
      ok-text="保存并重新向量化" width="900">
      <a-alert type="warning" show-icon style="margin-bottom: 12px;">
        <template #message>保存后会按 Markdown 标题重新分块、重新生成 embedding，原分块将被替换</template>
      </a-alert>
      <a-form layout="vertical">
        <a-form-item label="标题">
          <a-input v-model:value="fullContentEdit.title" />
        </a-form-item>
        <a-form-item label="正文 (Markdown)">
          <a-textarea v-model:value="fullContentEdit.content" :auto-size="{ minRows: 16, maxRows: 30 }" />
        </a-form-item>
      </a-form>
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

// Document detail drawer state
const showDocDetail = ref(false)
const docDetailLoading = ref(false)
const docDetail = ref<any>(null)
const docDetailTab = ref('chunks')
const docSaving = ref(false)
const docEdit = reactive({ title: '', source_path: '', metaJson: '' })
const docMetaError = ref('')

// Chunk edit modal state
const showChunkEdit = ref(false)
const chunkSaving = ref(false)
const chunkEdit = reactive({ id: 0, section: '', content: '' })

// Full content edit modal state
const showFullContentEdit = ref(false)
const fullContentSaving = ref(false)
const fullContentEdit = reactive({ title: '', content: '' })

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

// -------- Document detail drawer --------
async function openDocDetail(record: any) {
  if (!selectedKB.value) return
  docDetailTab.value = 'chunks'
  showDocDetail.value = true
  docDetailLoading.value = true
  try {
    const res = await knowledgeApi.documentDetail(selectedKB.value.id, record.id)
    docDetail.value = res.data
    docEdit.title = res.data.title
    docEdit.source_path = res.data.source_path || ''
    docEdit.metaJson = JSON.stringify(res.data.meta || {}, null, 2)
    docMetaError.value = ''
  } catch (e: any) {
    message.error('文档详情加载失败')
    showDocDetail.value = false
  } finally { docDetailLoading.value = false }
}

async function saveDocBasic() {
  if (!docDetail.value || !selectedKB.value) return
  docSaving.value = true
  try {
    await knowledgeApi.updateDocument(selectedKB.value.id, docDetail.value.id, { title: docEdit.title })
    docDetail.value.title = docEdit.title
    message.success('标题已更新')
    selectKB(selectedKB.value)  // refresh list
  } finally { docSaving.value = false }
}

async function saveDocMeta() {
  if (!docDetail.value || !selectedKB.value) return
  let parsed: any
  try {
    parsed = JSON.parse(docEdit.metaJson || '{}')
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
      throw new Error('必须是 JSON 对象')
    }
  } catch (e: any) {
    docMetaError.value = 'JSON 格式错误：' + (e.message || '解析失败')
    return
  }
  docMetaError.value = ''
  docSaving.value = true
  try {
    await knowledgeApi.updateDocument(selectedKB.value.id, docDetail.value.id, { meta: parsed })
    docDetail.value.meta = parsed
    message.success('元数据已更新')
    selectKB(selectedKB.value)
  } finally { docSaving.value = false }
}

async function deleteDoc() {
  if (!docDetail.value || !selectedKB.value) return
  try {
    await knowledgeApi.deleteDocument(selectedKB.value.id, docDetail.value.id)
    message.success('文档已删除')
    showDocDetail.value = false
    docDetail.value = null
    selectKB(selectedKB.value)
    fetchKBs()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

// -------- Full content edit --------
function openFullContentEdit() {
  if (!docDetail.value) return
  fullContentEdit.title = docDetail.value.title
  fullContentEdit.content = docDetail.value.chunks.map((c: any) => c.content).join('\n\n')
  showFullContentEdit.value = true
}

async function saveFullContent() {
  if (!docDetail.value || !selectedKB.value) return
  if (!fullContentEdit.content.trim()) {
    message.warning('正文内容不能为空')
    return
  }
  fullContentSaving.value = true
  try {
    let meta: any
    try {
      meta = JSON.parse(docEdit.metaJson || '{}')
    } catch {
      meta = docDetail.value.meta || {}
    }
    const res = await knowledgeApi.updateDocumentContent(
      selectedKB.value.id,
      docDetail.value.id,
      {
        title: fullContentEdit.title,
        content: fullContentEdit.content,
        meta,
      }
    )
    message.success(`全文已更新，共 ${res.data.chunks.length} 个分块（embedding 已重新生成）`)
    showFullContentEdit.value = false
    // Refresh detail and list
    docDetail.value = res.data
    docEdit.title = res.data.title
    selectKB(selectedKB.value)
    fetchKBs()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '全文保存失败')
  } finally { fullContentSaving.value = false }
}

// -------- Chunk edit --------
function openChunkEdit(record: any) {
  chunkEdit.id = record.id
  chunkEdit.section = record.section || ''
  chunkEdit.content = record.content || ''
  showChunkEdit.value = true
}

async function saveChunk() {
  if (!docDetail.value || !selectedKB.value) return
  chunkSaving.value = true
  try {
    await knowledgeApi.updateChunk(
      selectedKB.value.id, docDetail.value.id, chunkEdit.id,
      { content: chunkEdit.content, section: chunkEdit.section || null }
    )
    message.success('分块已更新（embedding 已重新生成）')
    showChunkEdit.value = false
    // refresh detail
    await openDocDetail(docDetail.value)
    fetchKBs()
  } finally { chunkSaving.value = false }
}

async function deleteChunk(record: any) {
  if (!docDetail.value || !selectedKB.value) return
  try {
    await knowledgeApi.deleteChunk(selectedKB.value.id, docDetail.value.id, record.id)
    message.success('分块已删除')
    await openDocDetail(docDetail.value)
    fetchKBs()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(() => fetchKBs())
</script>
