<template>
  <div>
    <!-- 顶部操作栏 -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <div>
        <h2 style="margin: 0;">多模态知识库</h2>
        <span style="opacity: 0.65; font-size: 13px;">
          图片 / 视频 / 音频 / PPT 素材的统一管理与 AI 检索
        </span>
      </div>
      <a-space>
        <a-button @click="loadKbs" :loading="loading">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button type="primary" @click="showCreate = true">
          <PlusOutlined /> 新建知识库
        </a-button>
      </a-space>
    </div>

    <!-- 知识库卡片网格 -->
    <a-row :gutter="[16, 16]">
      <a-col v-for="kb in kbs" :key="kb.id" :xs="24" :sm="12" :lg="8" :xl="6">
        <a-card hoverable class="kb-card" @click="openLibrary(kb)">
          <template #title>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 20px;">📁</span>
              <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ kb.name }}
              </span>
            </div>
          </template>
          <template #extra>
            <a-tag :color="kb.status === 'active' ? 'green' : 'default'">
              {{ kb.status === 'active' ? '启用' : kb.status === 'archived' ? '归档' : kb.status }}
            </a-tag>
          </template>
          <a-tooltip :title="kb.description || '暂无描述'">
            <p class="kb-desc">{{ kb.description || '暂无描述' }}</p>
          </a-tooltip>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <a-statistic title="素材数" :value="kb.asset_count" style="margin: 0;" />
            <span class="kb-code">{{ kb.code }}</span>
          </div>
          <template #actions>
            <span @click.stop="openLibrary(kb)"><AppstoreOutlined /> 素材库</span>
            <span @click.stop="openSearch(kb)"><SearchOutlined /> 检索</span>
            <a-dropdown @click.stop>
              <span><MoreOutlined /></span>
              <template #overlay>
                <a-menu @click="({ key }: any) => onKbMenu(key, kb)">
                  <a-menu-item key="edit"><EditOutlined /> 编辑</a-menu-item>
                  <a-menu-item key="archive" v-if="kb.status === 'active'">
                    <InboxOutlined /> 归档
                  </a-menu-item>
                  <a-menu-item key="activate" v-else>
                    <CheckCircleOutlined /> 启用
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="delete" danger><DeleteOutlined /> 删除</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </a-card>
      </a-col>

      <!-- 空态 -->
      <a-col :span="24" v-if="!loading && kbs.length === 0">
        <a-empty description="暂无多模态知识库，点击右上角新建">
          <a-button type="primary" @click="showCreate = true">
            <PlusOutlined /> 新建知识库
          </a-button>
        </a-empty>
      </a-col>
    </a-row>

    <!-- 新建 Modal -->
    <a-modal v-model:open="showCreate" title="新建多模态知识库" @ok="handleCreate" :confirmLoading="creating">
      <a-form layout="vertical" style="margin-top: 12px;">
        <a-form-item label="名称" required>
          <a-input v-model:value="createForm.name" placeholder="如：产品图库 / 营销视频库" :maxlength="60" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="createForm.description" placeholder="知识库用途说明（可选）" :rows="3" />
        </a-form-item>
        <a-alert type="info" show-icon message="编码将自动生成；默认使用通义千问 VL 分析 + 1024 维多模态 Embedding（可在知识库详情中调整）。" />
      </a-form>
    </a-modal>

    <!-- 编辑 Modal -->
    <a-modal v-model:open="showEdit" title="编辑知识库" @ok="handleUpdate" :confirmLoading="updating">
      <a-form layout="vertical" style="margin-top: 12px;">
        <a-form-item label="名称" required>
          <a-input v-model:value="editForm.name" :maxlength="60" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="editForm.description" :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined, ReloadOutlined, AppstoreOutlined, SearchOutlined,
  MoreOutlined, EditOutlined, DeleteOutlined, InboxOutlined,
  CheckCircleOutlined
} from '@ant-design/icons-vue'
import { multimodalApi } from '@/api/client'
import type { MmKnowledgeBase } from './types'

const router = useRouter()
const loading = ref(false)
const kbs = ref<MmKnowledgeBase[]>([])

const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

const showEdit = ref(false)
const updating = ref(false)
const editForm = ref({ id: 0, name: '', description: '' })

async function loadKbs() {
  loading.value = true
  try {
    const res = await multimodalApi.listKbs()
    kbs.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    message.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    await multimodalApi.createKb({
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim() || undefined
    })
    message.success('知识库创建成功')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await loadKbs()
  } finally {
    creating.value = false
  }
}

function onKbMenu(key: string, kb: MmKnowledgeBase) {
  if (key === 'edit') {
    editForm.value = { id: kb.id, name: kb.name, description: kb.description || '' }
    showEdit.value = true
  } else if (key === 'archive') {
    doUpdate(kb, 'archived')
  } else if (key === 'activate') {
    doUpdate(kb, 'active')
  } else if (key === 'delete') {
    Modal.confirm({
      title: '删除知识库',
      content: `确定删除「${kb.name}」？仅允许删除空知识库（素材数为 0，含回收站）。`,
      okType: 'danger',
      onOk: async () => {
        try {
          await multimodalApi.deleteKb(kb.id)
          message.success('已删除')
          await loadKbs()
        } catch { /* interceptor 已提示 */ }
      }
    })
  }
}

async function doUpdate(kb: MmKnowledgeBase, status?: string) {
  try {
    await multimodalApi.updateKb(kb.id, status ? { status } : {
      name: editForm.value.name.trim(),
      description: editForm.value.description.trim() || undefined
    })
    message.success('已更新')
    showEdit.value = false
    await loadKbs()
  } catch { /* interceptor 已提示 */ }
}

async function handleUpdate() {
  if (!editForm.value.name.trim()) {
    message.warning('名称不能为空')
    return
  }
  updating.value = true
  try {
    await multimodalApi.updateKb(editForm.value.id, {
      name: editForm.value.name.trim(),
      description: editForm.value.description.trim() || undefined
    })
    message.success('已更新')
    showEdit.value = false
    await loadKbs()
  } finally {
    updating.value = false
  }
}

function openLibrary(kb: MmKnowledgeBase) {
  router.push(`/multimodal/assets?kb=${kb.id}`)
}

function openSearch(kb: MmKnowledgeBase) {
  router.push(`/multimodal/search?kb=${kb.id}`)
}

onMounted(loadKbs)
</script>

<style scoped>
.kb-card :deep(.ant-card-body) {
  padding: 16px;
}
.kb-desc {
  height: 40px;
  margin: 0 0 8px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  opacity: 0.75;
  font-size: 13px;
}
.kb-code {
  font-size: 12px;
  opacity: 0.5;
  font-family: monospace;
}
</style>
