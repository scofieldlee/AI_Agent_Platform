<template>
  <div>
    <a-page-header title="模型中心" sub-title="管理 LLM 提供商与模型配置">
      <template #extra>
        <a-button type="primary" @click="openProviderDrawer()">
          <PlusOutlined /> 添加提供商
        </a-button>
        <a-button type="primary" @click="openConfigDrawer()" style="margin-left: 8px;">
          <PlusOutlined /> 添加模型配置
        </a-button>
      </template>
    </a-page-header>

    <!-- Providers -->
    <a-card title="模型提供商" style="margin-bottom: 16px;">
      <a-table :columns="providerColumns" :data-source="providers" :loading="loadingProviders" row-key="id"
        size="middle" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '启用' : '停用' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'api_key'">
            <span style="font-family: monospace;">{{ maskKey(record.api_key) }}</span>
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openProviderDrawer(record)">
                <EditOutlined /> 编辑
              </a-button>
              <a-popconfirm title="确定删除此提供商？删除前请确认没有模型配置引用它。" @confirm="deleteProvider(record.id)">
                <a-button type="link" danger size="small">
                  <DeleteOutlined /> 删除
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Model Configs -->
    <a-card title="模型配置">
      <a-table :columns="configColumns" :data-source="configs" :loading="loadingConfigs" row-key="id"
        size="middle" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'model_type'">
            <a-tag :color="modelTypeColor(record.model_type)">{{ modelTypeLabel(record.model_type) }}</a-tag>
          </template>
          <template v-if="column.key === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">
              {{ record.is_active ? '启用' : '停用' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'is_default'">
            <a-tag v-if="record.is_default" color="blue">默认</a-tag>
            <span v-else>-</span>
          </template>
          <template v-if="column.key === 'cost'">
            <span v-if="record.input_cost_per_1k || record.output_cost_per_1k">
              ${{ record.input_cost_per_1k || 0 }} / ${{ record.output_cost_per_1k || 0 }}
            </span>
            <span v-else>-</span>
          </template>
          <template v-if="column.key === 'provider'">
            {{ record.provider?.name }}
            <a-tag size="small" style="margin-left: 4px;">{{ record.provider?.code }}</a-tag>
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openConfigDrawer(record)">
                <EditOutlined /> 编辑
              </a-button>
              <a-button v-if="!record.is_default" type="link" size="small" @click="setDefault(record.id)">
                <CheckCircleOutlined /> 设为默认
              </a-button>
              <a-popconfirm title="确定删除此模型配置？" @confirm="deleteConfig(record.id)">
                <a-button type="link" danger size="small">
                  <DeleteOutlined /> 删除
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Provider Drawer -->
    <a-drawer
      v-model:open="providerDrawerOpen"
      :title="providerForm.id ? '编辑提供商' : '添加提供商'"
      width="520"
      :footer-style="{ textAlign: 'right' }"
    >
      <a-form :model="providerForm" layout="vertical">
        <a-form-item label="名称" name="name" :rules="[{ required: true, message: '请输入名称' }]">
          <a-input v-model:value="providerForm.name" placeholder="例如：DeepSeek" />
        </a-form-item>
        <a-form-item label="代码" name="code" :rules="[{ required: true, message: '请输入代码' }]">
          <a-input
            v-model:value="providerForm.code"
            placeholder="deepseek / openai / anthropic"
            :disabled="!!providerForm.id"
          />
          <div class="form-hint">只能包含小写字母、数字和下划线。</div>
        </a-form-item>
        <a-form-item label="Base URL" name="base_url" :rules="[{ required: true, message: '请输入 Base URL' }]">
          <a-input v-model:value="providerForm.base_url" placeholder="https://api.deepseek.com" />
        </a-form-item>
        <a-form-item label="API Key" name="api_key" :rules="[{ required: true, message: '请输入 API Key' }]">
          <a-input-password v-model:value="providerForm.api_key" placeholder="sk-..." />
        </a-form-item>
        <a-form-item label="启用状态">
          <a-switch v-model:checked="providerForm.is_active" checked-children="启用" un-checked-children="停用" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="providerDrawerOpen = false">取消</a-button>
        <a-button type="primary" :loading="savingProvider" @click="saveProvider" style="margin-left: 8px;">
          保存
        </a-button>
      </template>
    </a-drawer>

    <!-- Config Drawer -->
    <a-drawer
      v-model:open="configDrawerOpen"
      :title="configForm.id ? '编辑模型配置' : '添加模型配置'"
      width="520"
      :footer-style="{ textAlign: 'right' }"
    >
      <a-form :model="configForm" layout="vertical">
        <a-form-item label="所属提供商" name="provider_id" :rules="[{ required: true, message: '请选择提供商' }]">
          <a-select v-model:value="configForm.provider_id" placeholder="选择提供商">
            <a-select-option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.code }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="显示名称" name="name" :rules="[{ required: true, message: '请输入显示名称' }]">
          <a-input v-model:value="configForm.name" placeholder="例如：DeepSeek Chat" />
        </a-form-item>
        <a-form-item label="模型 ID" name="model_id" :rules="[{ required: true, message: '请输入模型 ID' }]">
          <a-input v-model:value="configForm.model_id" placeholder="例如：deepseek-chat" />
        </a-form-item>
        <a-form-item label="模型类型" name="model_type" :rules="[{ required: true }]">
          <a-radio-group v-model:value="configForm.model_type">
            <a-radio-button value="chat">对话</a-radio-button>
            <a-radio-button value="reasoning">推理</a-radio-button>
            <a-radio-button value="vision">视觉</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="Max Tokens" name="max_tokens">
              <a-input-number v-model:value="configForm.max_tokens" :min="1" :max="128000" style="width: 100%;" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="Temperature" name="temperature">
              <a-input-number v-model:value="configForm.temperature" :min="0" :max="2" :step="0.1" style="width: 100%;" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="输入成本 ($/1K tokens)">
              <a-input-number v-model:value="configForm.input_cost_per_1k" :min="0" :step="0.0001" style="width: 100%;" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="输出成本 ($/1K tokens)">
              <a-input-number v-model:value="configForm.output_cost_per_1k" :min="0" :step="0.0001" style="width: 100%;" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="启用状态">
          <a-switch v-model:checked="configForm.is_active" checked-children="启用" un-checked-children="停用" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="configDrawerOpen = false">取消</a-button>
        <a-button type="primary" :loading="savingConfig" @click="saveConfig" style="margin-left: 8px;">
          保存
        </a-button>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons-vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

interface Provider {
  id: number
  name: string
  code: string
  base_url: string
  api_key: string
  is_active: boolean
  config: Record<string, any>
  created_at?: string
  updated_at?: string
}

interface ProviderForm {
  id?: number
  name: string
  code: string
  base_url: string
  api_key: string
  is_active: boolean
  config: Record<string, any>
}

interface ModelConfig {
  id: number
  provider_id: number
  name: string
  model_id: string
  model_type: string
  max_tokens: number
  temperature: number
  input_cost_per_1k?: number
  output_cost_per_1k?: number
  is_active: boolean
  is_default: boolean
  provider?: Provider
}

interface ConfigForm {
  id?: number
  provider_id: number | null
  name: string
  model_id: string
  model_type: string
  max_tokens: number
  temperature: number
  input_cost_per_1k: number | null
  output_cost_per_1k: number | null
  is_active: boolean
}

const providers = ref<Provider[]>([])
const configs = ref<ModelConfig[]>([])
const loadingProviders = ref(false)
const loadingConfigs = ref(false)

const providerDrawerOpen = ref(false)
const configDrawerOpen = ref(false)
const savingProvider = ref(false)
const savingConfig = ref(false)

const providerForm = reactive<ProviderForm>({
  name: '',
  code: '',
  base_url: '',
  api_key: '',
  is_active: true,
  config: {},
})

const configForm = reactive<ConfigForm>({
  provider_id: null,
  name: '',
  model_id: '',
  model_type: 'chat',
  max_tokens: 4096,
  temperature: 0.3,
  input_cost_per_1k: null,
  output_cost_per_1k: null,
  is_active: true,
})

const providerColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '代码', dataIndex: 'code', key: 'code' },
  { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', ellipsis: true },
  { title: 'API Key', key: 'api_key' },
  { title: '状态', key: 'is_active', width: 90 },
  { title: '操作', key: 'action', width: 160 },
]

const configColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '模型 ID', dataIndex: 'model_id', key: 'model_id' },
  { title: '类型', key: 'model_type', width: 100 },
  { title: '提供商', key: 'provider' },
  { title: 'Max Tokens', dataIndex: 'max_tokens', key: 'max_tokens', width: 120 },
  { title: 'Temperature', dataIndex: 'temperature', key: 'temperature', width: 120 },
  { title: '成本', key: 'cost', width: 140 },
  { title: '默认', key: 'is_default', width: 80 },
  { title: '状态', key: 'is_active', width: 90 },
  { title: '操作', key: 'action', width: 200 },
]

function modelTypeColor(type: string) {
  const map: Record<string, string> = {
    chat: 'blue',
    reasoning: 'purple',
    vision: 'cyan',
    embedding: 'green',
    rerank: 'orange',
    speech: 'magenta',
  }
  return map[type] || 'default'
}

function modelTypeLabel(type: string) {
  const map: Record<string, string> = {
    chat: '对话',
    reasoning: '推理',
    vision: '视觉',
    embedding: 'Embedding',
    rerank: 'Rerank',
    speech: '语音',
  }
  return map[type] || type
}

function maskKey(key: string) {
  if (!key || key.length <= 8) return '***'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

async function fetchProviders() {
  loadingProviders.value = true
  try {
    const res = await fetch(`${API_BASE}/models/providers?include_inactive=true`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
    })
    if (!res.ok) throw new Error(await res.text())
    providers.value = await res.json()
  } catch (e: any) {
    message.error(`加载提供商失败: ${e.message}`)
  } finally {
    loadingProviders.value = false
  }
}

async function fetchConfigs() {
  loadingConfigs.value = true
  try {
    const res = await fetch(`${API_BASE}/models/configs?include_inactive=true`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
    })
    if (!res.ok) throw new Error(await res.text())
    configs.value = await res.json()
  } catch (e: any) {
    message.error(`加载模型配置失败: ${e.message}`)
  } finally {
    loadingConfigs.value = false
  }
}

function resetProviderForm() {
  Object.assign(providerForm, {
    id: undefined,
    name: '',
    code: '',
    base_url: '',
    api_key: '',
    is_active: true,
    config: {},
  })
}

function resetConfigForm() {
  Object.assign(configForm, {
    id: undefined,
    provider_id: null,
    name: '',
    model_id: '',
    model_type: 'chat',
    max_tokens: 4096,
    temperature: 0.3,
    input_cost_per_1k: null,
    output_cost_per_1k: null,
    is_active: true,
  })
}

function openProviderDrawer(record?: Provider) {
  resetProviderForm()
  if (record) {
    Object.assign(providerForm, record)
  }
  providerDrawerOpen.value = true
}

function openConfigDrawer(record?: ModelConfig) {
  resetConfigForm()
  if (record) {
    Object.assign(configForm, {
      id: record.id,
      provider_id: record.provider_id,
      name: record.name,
      model_id: record.model_id,
      model_type: record.model_type,
      max_tokens: record.max_tokens,
      temperature: record.temperature,
      input_cost_per_1k: record.input_cost_per_1k ?? null,
      output_cost_per_1k: record.output_cost_per_1k ?? null,
      is_active: record.is_active,
    })
  }
  configDrawerOpen.value = true
}

async function saveProvider() {
  if (!providerForm.name || !providerForm.code || !providerForm.base_url || !providerForm.api_key) {
    message.warning('请填写完整的提供商信息')
    return
  }
  savingProvider.value = true
  try {
    const url = `${API_BASE}/models/providers${providerForm.id ? `/${providerForm.id}` : ''}`
    const method = providerForm.id ? 'PATCH' : 'POST'
    const body = { ...providerForm }
    if (providerForm.id) {
      delete (body as any).id
    }
    const res = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    message.success(providerForm.id ? '更新成功' : '添加成功')
    providerDrawerOpen.value = false
    await fetchProviders()
  } catch (e: any) {
    message.error(`保存失败: ${e.message}`)
  } finally {
    savingProvider.value = false
  }
}

async function deleteProvider(id: number) {
  try {
    const res = await fetch(`${API_BASE}/models/providers/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
    })
    if (!res.ok) throw new Error(await res.text())
    message.success('删除成功')
    await fetchProviders()
    await fetchConfigs()
  } catch (e: any) {
    message.error(`删除失败: ${e.message}`)
  }
}

async function saveConfig() {
  if (!configForm.provider_id || !configForm.name || !configForm.model_id) {
    message.warning('请填写完整的模型配置信息')
    return
  }
  savingConfig.value = true
  try {
    const url = `${API_BASE}/models/configs${configForm.id ? `/${configForm.id}` : ''}`
    const method = configForm.id ? 'PATCH' : 'POST'
    const body: any = { ...configForm }
    if (configForm.id) {
      delete body.id
    }
    if (body.input_cost_per_1k === null || body.input_cost_per_1k === undefined) {
      delete body.input_cost_per_1k
    }
    if (body.output_cost_per_1k === null || body.output_cost_per_1k === undefined) {
      delete body.output_cost_per_1k
    }
    const res = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    message.success(configForm.id ? '更新成功' : '添加成功')
    configDrawerOpen.value = false
    await fetchConfigs()
  } catch (e: any) {
    message.error(`保存失败: ${e.message}`)
  } finally {
    savingConfig.value = false
  }
}

async function deleteConfig(id: number) {
  try {
    const res = await fetch(`${API_BASE}/models/configs/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
    })
    if (!res.ok) throw new Error(await res.text())
    message.success('删除成功')
    await fetchConfigs()
  } catch (e: any) {
    message.error(`删除失败: ${e.message}`)
  }
}

async function setDefault(id: number) {
  try {
    const res = await fetch(`${API_BASE}/models/configs/${id}/set-default`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
    })
    if (!res.ok) throw new Error(await res.text())
    message.success('已设为默认')
    await fetchConfigs()
  } catch (e: any) {
    message.error(`设置失败: ${e.message}`)
  }
}

onMounted(() => {
  fetchProviders()
  fetchConfigs()
})
</script>

<style scoped>
.form-hint {
  color: #888;
  font-size: 12px;
  margin-top: 4px;
}
</style>
