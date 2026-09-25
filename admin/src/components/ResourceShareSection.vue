<template>
  <div v-if="loaded && !visible">
    <a-alert type="warning" show-icon
      message="仅资源所有者或管理员可管理授权"
      description="你不是该资源的创建者，也无管理员权限。如需授权，请联系资源创建者或管理员操作。"
    />
  </div>
  <div v-else-if="visible" class="config-section">
    <div class="section-title"><ShareAltOutlined /> 成员授权</div>
    <div style="font-size: 12px; opacity: 0.6; margin-bottom: 10px; line-height: 1.6;">
      将{{ resourceLabel }}授权给指定用户或角色。权限层级：管理 ⊃ 查看 ⊃ 对话。
      {{ isSuperuser ? '你是超级管理员，可按角色批量授权。' : '角色级授权仅超级管理员可操作。' }}
    </div>

    <a-tabs v-model:activeKey="tab" size="small">
      <!-- 按用户 -->
      <a-tab-pane key="user" tab="按用户">
        <div style="display: flex; gap: 8px; margin-bottom: 10px;">
          <a-input v-model:value="userForm.identifier" placeholder="用户名" style="width: 160px;" size="small" />
          <a-select v-model:value="userForm.permission" style="width: 110px;" size="small">
            <a-select-option value="chat">对话</a-select-option>
            <a-select-option value="view">查看</a-select-option>
            <a-select-option value="manage">管理</a-select-option>
          </a-select>
          <a-button size="small" type="primary" :loading="granting" @click="grant('user')">授权</a-button>
        </div>
        <a-table :columns="userColumns" :data-source="userShares" row-key="id" size="small" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'principal_name'">
              {{ record.principal_name }}
            </template>
            <template v-if="column.key === 'permission'">
              <a-tag :color="permColor(record.permission)" style="font-size: 11px;">{{ permLabel(record.permission) }}</a-tag>
            </template>
            <template v-if="column.key === 'action'">
              <a-popconfirm title="撤销该用户的授权？" @confirm="revoke(record)">
                <a-button size="small" type="link" danger>撤销</a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 按角色（仅超级管理员） -->
      <a-tab-pane key="role" tab="按角色" v-if="isSuperuser">
        <div style="display: flex; gap: 8px; margin-bottom: 10px;">
          <a-select v-model:value="roleForm.identifier" placeholder="选择角色" style="width: 160px;" size="small"
            :options="roleOptions" show-search option-filter-prop="label" />
          <a-select v-model:value="roleForm.permission" style="width: 110px;" size="small">
            <a-select-option value="chat">对话</a-select-option>
            <a-select-option value="view">查看</a-select-option>
            <a-select-option value="manage">管理</a-select-option>
          </a-select>
          <a-button size="small" type="primary" :loading="granting" @click="grant('role')">授权</a-button>
        </div>
        <a-table :columns="roleColumns" :data-source="roleShares" row-key="id" size="small" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'principal_name'">
              {{ record.principal_name }}
            </template>
            <template v-if="column.key === 'permission'">
              <a-tag :color="permColor(record.permission)" style="font-size: 11px;">{{ permLabel(record.permission) }}</a-tag>
            </template>
            <template v-if="column.key === 'action'">
              <a-popconfirm title="撤销该角色的授权？" @confirm="revoke(record)">
                <a-button size="small" type="link" danger>撤销</a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { ShareAltOutlined } from '@ant-design/icons-vue'
import { resourceSharesApi, authApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  resourceType: 'agent' | 'employee'
  resourceId: number
  resourceLabel: string
}>()

const auth = useAuthStore()
const isSuperuser = computed(() => auth.isSuperuser)
const visible = ref(false)
const loaded = ref(false)

const tab = ref('user')
const granting = ref(false)
const userShares = ref<any[]>([])
const roleShares = ref<any[]>([])
const roleOptions = ref<any[]>([])
const userForm = ref({ identifier: '', permission: 'view' })
const roleForm = ref({ identifier: undefined as string | undefined, permission: 'view' })

const userColumns = [
  { title: '用户', key: 'principal_name', width: 160 },
  { title: '权限', key: 'permission', width: 90 },
  { title: '操作', key: 'action', width: 70 },
]
const roleColumns = [
  { title: '角色', key: 'principal_name', width: 160 },
  { title: '权限', key: 'permission', width: 90 },
  { title: '操作', key: 'action', width: 70 },
]

function permColor(p: string) {
  return { chat: 'default', view: 'blue', manage: 'purple' }[p] || 'default'
}
function permLabel(p: string) {
  return { chat: '对话', view: '查看', manage: '管理' }[p] || p
}

async function fetchShares() {
  try {
    const res = await resourceSharesApi.list(props.resourceType, props.resourceId)
    userShares.value = (res.data.items || []).filter((s: any) => s.principal_type === 'user')
    roleShares.value = (res.data.items || []).filter((s: any) => s.principal_type === 'role')
    visible.value = true
  } catch (err: any) {
    // 403/404：非 owner 且非管理员 → 显示无权提示
    visible.value = false
  } finally {
    loaded.value = true
  }
}

async function fetchRoles() {
  if (!isSuperuser.value) return
  try {
    const res = await authApi.listRoles()
    roleOptions.value = (res.data || []).map((r: any) => ({ value: r.code, label: r.name }))
  } catch { roleOptions.value = [] }
}

async function grant(principalType: 'user' | 'role') {
  const form = principalType === 'user' ? userForm.value : roleForm.value
  if (!form.identifier?.trim()) {
    message.error(principalType === 'user' ? '请输入用户名' : '请选择角色')
    return
  }
  granting.value = true
  try {
    await resourceSharesApi.grant(props.resourceType, props.resourceId, {
      principal_type: principalType,
      identifier: form.identifier.trim(),
      permission: form.permission as 'chat' | 'view' | 'manage'
    })
    message.success('授权成功')
    form.identifier = principalType === 'user' ? '' : undefined
    await fetchShares()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '授权失败')
  } finally { granting.value = false }
}

async function revoke(record: any) {
  try {
    await resourceSharesApi.revoke(props.resourceType, props.resourceId, record.id)
    message.success('已撤销授权')
    await fetchShares()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '撤销失败')
  }
}

onMounted(async () => {
  await fetchShares()
  await fetchRoles()
})
</script>
