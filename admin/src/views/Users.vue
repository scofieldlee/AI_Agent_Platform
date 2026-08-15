<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0; font-size: 20px; font-weight: 600;">用户管理</h2>
      <a-button type="primary" @click="showCreateModal = true">
        <PlusOutlined />
        新建用户
      </a-button>
    </div>

    <!-- User Table -->
    <a-table
      :columns="columns"
      :data-source="users"
      :loading="loading"
      row-key="id"
      :pagination="{ pageSize: 10 }"
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
          <a-tag v-for="role in record.roles" :key="role" :color="roleColor(role)">
            {{ roleLabel(role) }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'is_active'">
          <a-badge :status="record.is_active ? 'success' : 'error'" :text="record.is_active ? '启用' : '禁用'" />
        </template>
        <template v-else-if="column.key === 'last_login'">
          {{ record.last_login ? formatTime(record.last_login) : '从未登录' }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" @click="handleEdit(record)">编辑</a-button>
          <a-popconfirm
            :title="record.is_active ? '确定禁用该用户？' : '确定启用该用户？'"
            @confirm="handleToggleActive(record)"
          >
            <a-button type="link" size="small" :danger="record.is_active">
              {{ record.is_active ? '禁用' : '启用' }}
            </a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <!-- Create User Modal -->
    <a-modal
      v-model:open="showCreateModal"
      title="新建用户"
      @ok="handleCreate"
      :confirm-loading="submitting"
      width="480px"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="用户名" required>
          <a-input v-model:value="createForm.username" placeholder="3-100 字符" />
        </a-form-item>
        <a-form-item label="邮箱" required>
          <a-input v-model:value="createForm.email" placeholder="user@example.com" />
        </a-form-item>
        <a-form-item label="密码" required>
          <a-input-password v-model:value="createForm.password" placeholder="至少 6 位" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="姓名">
              <a-input v-model:value="createForm.full_name" placeholder="张三" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="部门">
              <a-input v-model:value="createForm.department" placeholder="客服部" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="手机号">
          <a-input v-model:value="createForm.phone" placeholder="13800138000" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select
            v-model:value="createForm.role_codes"
            mode="multiple"
            placeholder="选择角色"
            style="width: 100%"
          >
            <a-select-option v-for="r in roles" :key="r.code" :value="r.code">
              {{ r.name }} — {{ r.description }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="超级管理员">
          <a-switch v-model:checked="createForm.is_superuser" />
          <span style="margin-left: 8px; color: var(--text-color-secondary, #999); font-size: 12px;">
            超级管理员绕过所有权限检查
          </span>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Edit User Modal -->
    <a-modal
      v-model:open="showEditModal"
      title="编辑用户"
      @ok="handleUpdate"
      :confirm-loading="submitting"
      width="480px"
    >
      <a-form layout="vertical" style="margin-top: 16px;">
        <a-form-item label="用户名">
          <a-input :value="editForm.username" disabled />
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input :value="editForm.email" disabled />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="姓名">
              <a-input v-model:value="editForm.full_name" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="部门">
              <a-input v-model:value="editForm.department" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="手机号">
          <a-input v-model:value="editForm.phone" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select
            v-model:value="editForm.role_codes"
            mode="multiple"
            placeholder="选择角色"
            style="width: 100%"
          >
            <a-select-option v-for="r in roles" :key="r.code" :value="r.code">
              {{ r.name }} — {{ r.description }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="超级管理员">
          <a-switch v-model:checked="editForm.is_superuser" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { authApi } from '@/api/client'
import dayjs from 'dayjs'

interface UserItem {
  id: number
  username: string
  email: string
  full_name: string | null
  department: string | null
  phone: string | null
  is_active: boolean
  is_superuser: boolean
  last_login: string | null
  roles: string[]
}

interface RoleItem {
  id: number
  code: string
  name: string
  description: string | null
}

const loading = ref(false)
const submitting = ref(false)
const users = ref<UserItem[]>([])
const roles = ref<RoleItem[]>([])
const showCreateModal = ref(false)
const showEditModal = ref(false)

const createForm = ref({
  username: '',
  email: '',
  password: '',
  full_name: '',
  department: '',
  phone: '',
  role_codes: ['user'],
  is_superuser: false,
})

const editForm = ref({
  id: 0,
  username: '',
  email: '',
  full_name: '',
  department: '',
  phone: '',
  role_codes: [] as string[],
  is_superuser: false,
})

const columns = [
  { title: '用户名', key: 'username', dataIndex: 'username' },
  { title: '邮箱', key: 'email', dataIndex: 'email' },
  { title: '姓名', key: 'full_name', dataIndex: 'full_name' },
  { title: '角色', key: 'roles' },
  { title: '状态', key: 'is_active' },
  { title: '最后登录', key: 'last_login' },
  { title: '操作', key: 'action', width: 160 },
]

const roleMap: Record<string, string> = {
  super_admin: '超级管理员',
  ai_admin: 'AI 管理员',
  business_admin: '业务管理员',
  developer: '开发者',
  customer_service: '客服',
  user: '普通用户',
}

function roleLabel(code: string): string {
  return roleMap[code] || code
}

function roleColor(code: string): string {
  const colors: Record<string, string> = {
    super_admin: 'gold',
    ai_admin: 'purple',
    business_admin: 'blue',
    developer: 'geekblue',
    customer_service: 'green',
    user: 'default',
  }
  return colors[code] || 'default'
}

function formatTime(t: string): string {
  return dayjs(t).format('YYYY-MM-DD HH:mm')
}

async function loadData() {
  loading.value = true
  try {
    const [usersRes, rolesRes] = await Promise.all([
      authApi.listUsers(),
      authApi.listRoles(),
    ])
    users.value = usersRes.data.items || []
    roles.value = rolesRes.data || []
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.username || !createForm.value.email || !createForm.value.password) {
    message.warning('请填写必填项')
    return
  }
  submitting.value = true
  try {
    await authApi.createUser({
      ...createForm.value,
      full_name: createForm.value.full_name || undefined,
      department: createForm.value.department || undefined,
      phone: createForm.value.phone || undefined,
    })
    message.success('用户创建成功')
    showCreateModal.value = false
    // Reset form
    createForm.value = {
      username: '', email: '', password: '',
      full_name: '', department: '', phone: '',
      role_codes: ['user'], is_superuser: false,
    }
    await loadData()
  } finally {
    submitting.value = false
  }
}

function handleEdit(record: UserItem) {
  editForm.value = {
    id: record.id,
    username: record.username,
    email: record.email,
    full_name: record.full_name || '',
    department: record.department || '',
    phone: record.phone || '',
    role_codes: [...record.roles],
    is_superuser: record.is_superuser,
  }
  showEditModal.value = true
}

async function handleUpdate() {
  submitting.value = true
  try {
    await authApi.updateUser(editForm.value.id, {
      full_name: editForm.value.full_name || undefined,
      department: editForm.value.department || undefined,
      phone: editForm.value.phone || undefined,
      role_codes: editForm.value.role_codes,
      is_superuser: editForm.value.is_superuser,
    })
    message.success('用户更新成功')
    showEditModal.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function handleToggleActive(record: UserItem) {
  try {
    await authApi.updateUser(record.id, { is_active: !record.is_active })
    message.success(record.is_active ? '已禁用用户' : '已启用用户')
    await loadData()
  } catch {
    // error handled by interceptor
  }
}

onMounted(() => {
  loadData()
})
</script>
