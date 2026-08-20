<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0; font-size: 20px; font-weight: 600;">角色权限管理</h2>
      <a-button type="primary" @click="openCreateModal">
        <PlusOutlined />
        新建角色
      </a-button>
    </div>

    <!-- Role Table -->
    <a-table
      :columns="columns"
      :data-source="roles"
      :loading="loading"
      row-key="id"
      :pagination="{ pageSize: 10 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 500;">{{ record.name }}</span>
            <a-tag v-if="record.is_system" color="blue" style="margin: 0;">系统</a-tag>
          </div>
        </template>
        <template v-else-if="column.key === 'code'">
          <a-tag color="default">{{ record.code }}</a-tag>
        </template>
        <template v-else-if="column.key === 'user_count'">
          <a-badge :count="record.user_count" :number-style="{ backgroundColor: record.user_count ? '#4f46e5' : '#999' }" />
        </template>
        <template v-else-if="column.key === 'permission_count'">
          <a-tag color="processing">{{ record.permission_count }} 项</a-tag>
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" @click="openEditModal(record)">编辑权限</a-button>
          <a-button type="link" size="small" @click="openUsersDrawer(record)">查看用户</a-button>
          <a-popconfirm
            title="确定删除该角色？"
            description="删除后无法恢复，已绑定用户将失去该角色权限。"
            @confirm="handleDelete(record)"
            :disabled="isDeleteDisabled(record)"
          >
            <a-button type="link" size="small" danger :disabled="isDeleteDisabled(record)">
              删除
            </a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <!-- Create / Edit Modal -->
    <a-modal
      v-model:open="modalVisible"
      :title="modalTitle"
      @ok="handleSubmit"
      :confirm-loading="submitting"
      width="720px"
      :ok-button-props="{ disabled: !isFormValid }"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="角色名称" required>
              <a-input
                v-model:value="form.name"
                placeholder="如：内容运营"
                :maxlength="100"
                :disabled="isEditing && form.is_system"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="角色标识" required>
              <a-input
                v-model:value="form.code"
                placeholder="如：content_operator"
                :disabled="isEditing"
                :maxlength="50"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" placeholder="角色职责说明" :rows="2" />
        </a-form-item>

        <a-divider orientation="left">权限分配</a-divider>

        <div v-if="permissionLoading" style="text-align: center; padding: 24px;">
          <a-spin tip="加载权限中..." />
        </div>

        <div v-else>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <a-typography-text type="secondary">
              已选择 {{ selectedPermissionCount }} 项权限
            </a-typography-text>
            <a-space>
              <a-button size="small" @click="selectAllPermissions(true)">全选</a-button>
              <a-button size="small" @click="selectAllPermissions(false)">清空</a-button>
            </a-space>
          </div>

          <a-row :gutter="[16, 16]">
            <a-col v-for="group in permissionGroups" :key="group.resource_type" :span="12">
              <a-card size="small" :title="resourceTypeLabel(group.resource_type)">
                <template #extra>
                  <a-checkbox
                    :checked="groupCheckAll[group.resource_type]"
                    :indeterminate="groupIndeterminate[group.resource_type]"
                    @change="(e: any) => onGroupCheckAllChange(group.resource_type, e.target.checked)"
                  >
                    全选
                  </a-checkbox>
                </template>
                <a-checkbox-group
                  v-model:value="form.permission_codes"
                  style="display: flex; flex-direction: column; gap: 8px;"
                  @change="() => updateGroupState(group.resource_type)"
                >
                  <a-checkbox
                    v-for="perm in group.permissions"
                    :key="perm.code"
                    :value="perm.code"
                    style="margin-left: 0;"
                  >
                    <a-tooltip :title="perm.description || perm.name">
                      <span>{{ perm.name }}</span>
                    </a-tooltip>
                    <a-tag size="small" style="margin-left: 4px;">{{ actionLabel(perm.action) }}</a-tag>
                  </a-checkbox>
                </a-checkbox-group>
              </a-card>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-modal>

    <!-- Users Drawer -->
    <a-drawer
      v-model:open="usersDrawerVisible"
      :title="`「${currentRole?.name}」绑定用户`"
      width="560px"
      placement="right"
    >
      <a-table
        :columns="userColumns"
        :data-source="roleUsers"
        :loading="roleUsersLoading"
        row-key="id"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'username'">
            <div style="display: flex; align-items: center; gap: 8px;">
              <a-avatar size="small" style="background-color: #4f46e5;">
                {{ record.username.charAt(0).toUpperCase() }}
              </a-avatar>
              <span>{{ record.username }}</span>
              <a-tag v-if="record.is_superuser" color="gold" style="margin: 0;">超级</a-tag>
            </div>
          </template>
          <template v-else-if="column.key === 'roles'">
            <a-tag v-for="role in record.roles" :key="role" color="default">
              {{ roleMap[role] || role }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'is_active'">
            <a-badge :status="record.is_active ? 'success' : 'error'" :text="record.is_active ? '启用' : '禁用'" />
          </template>
        </template>
      </a-table>
      <a-empty v-if="!roleUsersLoading && roleUsers.length === 0" description="暂无绑定用户" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { authApi } from '@/api/client'

interface PermissionItem {
  id: number
  code: string
  name: string
  resource_type: string
  action: string
  description: string | null
}

interface PermissionGroup {
  resource_type: string
  permissions: PermissionItem[]
}

interface RoleItem {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  user_count: number
  permission_count: number
}

interface UserItem {
  id: number
  username: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  roles: string[]
}

const loading = ref(false)
const submitting = ref(false)
const permissionLoading = ref(false)
const roles = ref<RoleItem[]>([])
const permissionGroups = ref<PermissionGroup[]>([])

const modalVisible = ref(false)
const isEditing = ref(false)
const modalTitle = computed(() => isEditing.value ? '编辑角色权限' : '新建角色')

const form = ref({
  id: 0,
  code: '',
  name: '',
  description: '',
  permission_codes: [] as string[],
  is_system: false,
})

const groupCheckAll = reactive<Record<string, boolean>>({})
const groupIndeterminate = reactive<Record<string, boolean>>({})

const usersDrawerVisible = ref(false)
const roleUsersLoading = ref(false)
const roleUsers = ref<UserItem[]>([])
const currentRole = ref<RoleItem | null>(null)

const columns = [
  { title: '角色名称', key: 'name', dataIndex: 'name' },
  { title: '标识', key: 'code' },
  { title: '描述', key: 'description', dataIndex: 'description', ellipsis: true },
  { title: '用户数', key: 'user_count', width: 90 },
  { title: '权限数', key: 'permission_count', width: 90 },
  { title: '操作', key: 'action', width: 220 },
]

const userColumns = [
  { title: '用户名', key: 'username', dataIndex: 'username' },
  { title: '姓名', key: 'full_name', dataIndex: 'full_name' },
  { title: '角色', key: 'roles' },
  { title: '状态', key: 'is_active', width: 90 },
]

const roleMap: Record<string, string> = {
  super_admin: '超级管理员',
  ai_admin: 'AI 管理员',
  business_admin: '业务管理员',
  developer: '开发者',
  customer_service: '客服',
  user: '普通用户',
}

const resourceTypeLabels: Record<string, string> = {
  dashboard: '仪表盘',
  agent: 'Agent',
  conversation: '对话',
  knowledge: '知识库',
  tool: '工具',
  model: '模型',
  memory: '记忆',
  ticket: '工单',
  analytics: '执行追踪',
  user: '用户权限',
  system: '系统',
}

const actionLabels: Record<string, string> = {
  view: '查看',
  use: '使用',
  manage: '管理',
  delete: '删除',
}

function resourceTypeLabel(type: string): string {
  return resourceTypeLabels[type] || type
}

function actionLabel(action: string): string {
  return actionLabels[action] || action
}

function isDeleteDisabled(record: RoleItem): boolean {
  return !!record.is_system || Number(record.user_count || 0) > 0
}

const selectedPermissionCount = computed(() => form.value.permission_codes.length)

const isFormValid = computed(() => {
  const codePattern = /^[a-z_][a-z0-9_]*$/
  return (
    form.value.name.trim().length > 0 &&
    form.value.code.trim().length > 0 &&
    codePattern.test(form.value.code)
  )
})

function selectAllPermissions(selected: boolean) {
  if (selected) {
    const all: string[] = []
    permissionGroups.value.forEach((g) => {
      g.permissions.forEach((p) => all.push(p.code))
    })
    form.value.permission_codes = all
  } else {
    form.value.permission_codes = []
  }
  permissionGroups.value.forEach((g) => updateGroupState(g.resource_type))
}

function onGroupCheckAllChange(resourceType: string, checked: boolean) {
  const group = permissionGroups.value.find((g) => g.resource_type === resourceType)
  if (!group) return

  const codes = group.permissions.map((p) => p.code)
  const set = new Set(form.value.permission_codes)

  if (checked) {
    codes.forEach((c) => set.add(c))
  } else {
    codes.forEach((c) => set.delete(c))
  }

  form.value.permission_codes = Array.from(set)
  updateGroupState(resourceType)
}

function updateGroupState(resourceType: string) {
  const group = permissionGroups.value.find((g) => g.resource_type === resourceType)
  if (!group) return

  const codes = group.permissions.map((p) => p.code)
  const selectedCount = codes.filter((c) => form.value.permission_codes.includes(c)).length

  groupCheckAll[resourceType] = selectedCount === codes.length && codes.length > 0
  groupIndeterminate[resourceType] = selectedCount > 0 && selectedCount < codes.length
}

async function loadRoles() {
  loading.value = true
  try {
    const res = await authApi.listRoles()
    roles.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function loadPermissions() {
  permissionLoading.value = true
  try {
    const res = await authApi.listPermissions()
    permissionGroups.value = res.data || []
    // Initialize group state
    permissionGroups.value.forEach((g) => {
      groupCheckAll[g.resource_type] = false
      groupIndeterminate[g.resource_type] = false
    })
  } finally {
    permissionLoading.value = false
  }
}

function resetForm() {
  form.value = {
    id: 0,
    code: '',
    name: '',
    description: '',
    permission_codes: [],
    is_system: false,
  }
  permissionGroups.value.forEach((g) => {
    groupCheckAll[g.resource_type] = false
    groupIndeterminate[g.resource_type] = false
  })
}

function openCreateModal() {
  isEditing.value = false
  resetForm()
  modalVisible.value = true
}

async function openEditModal(record: RoleItem) {
  isEditing.value = true
  resetForm()
  modalVisible.value = true

  try {
    const res = await authApi.getRole(record.id)
    const detail = res.data
    form.value = {
      id: detail.id,
      code: detail.code,
      name: detail.name,
      description: detail.description || '',
      permission_codes: detail.permissions || [],
      is_system: detail.is_system,
    }
    await nextTick()
    permissionGroups.value.forEach((g) => updateGroupState(g.resource_type))
  } catch {
    modalVisible.value = false
  }
}

async function handleSubmit() {
  if (!isFormValid.value) {
    message.warning('请填写有效的角色名称和标识')
    return
  }

  submitting.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      description: form.value.description.trim() || undefined,
      permission_codes: form.value.permission_codes,
    }

    if (isEditing.value) {
      await authApi.updateRole(form.value.id, payload)
      message.success('角色权限更新成功')
    } else {
      await authApi.createRole({
        code: form.value.code.trim(),
        name: form.value.name.trim(),
        description: form.value.description.trim() || undefined,
        permission_codes: form.value.permission_codes,
      })
      message.success('角色创建成功')
    }

    modalVisible.value = false
    await loadRoles()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(record: RoleItem) {
  if (record.is_system) {
    message.warning('系统角色不可删除')
    return
  }
  if (record.user_count > 0) {
    message.warning('该角色下还有用户，请先移除用户绑定')
    return
  }
  try {
    await authApi.deleteRole(record.id)
    message.success('角色已删除')
    await loadRoles()
  } catch {
    // error handled by interceptor
  }
}

async function openUsersDrawer(record: RoleItem) {
  currentRole.value = record
  usersDrawerVisible.value = true
  roleUsersLoading.value = true
  try {
    const res = await authApi.listRoleUsers(record.id)
    roleUsers.value = res.data.items || []
  } finally {
    roleUsersLoading.value = false
  }
}

onMounted(() => {
  loadRoles()
  loadPermissions()
})
</script>
