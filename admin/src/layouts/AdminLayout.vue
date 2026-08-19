<template>
  <a-layout style="min-height: 100vh">
    <!-- Sider -->
    <a-layout-sider v-model:collapsed="collapsed" collapsible :trigger="null" width="220"
      :theme="isDark ? 'dark' : 'dark'"
      :style="siderStyle">
      <!-- Logo -->
      <div style="height: 64px; display: flex; align-items: center; justify-content: center; overflow: hidden;">
        <span v-if="!collapsed" style="color: #fff; font-size: 18px; font-weight: 700; white-space: nowrap;
          background: linear-gradient(135deg, #4f46e5, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
          AI Agent Platform
        </span>
        <span v-else style="font-size: 24px;">⚡</span>
      </div>

      <a-menu v-model:selectedKeys="selectedKeys" theme="dark" mode="inline" @click="onMenuClick"
        style="background: transparent; border: none;">
        <a-menu-item v-if="canSee('dashboard')" key="dashboard">
          <DashboardOutlined />
          <span>仪表盘</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('tasks')" key="tasks">
          <CustomerServiceOutlined />
          <span>工单管理</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('conversations')" key="conversations">
          <MessageOutlined />
          <span>对话管理</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('knowledge')" key="knowledge">
          <BookOutlined />
          <span>知识库</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('analytics')" key="analytics">
          <LineChartOutlined />
          <span>执行追踪</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('memories')" key="memories">
          <BulbOutlined />
          <span>记忆管理</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('agents')" key="agents">
          <RobotOutlined />
          <span>Agent 管理</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('employees')" key="employees">
          <UsergroupAddOutlined />
          <span>AI 员工</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('employee-workbench')" key="employee-workbench">
          <ThunderboltOutlined />
          <span>员工工作台</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('models')" key="models">
          <DatabaseOutlined />
          <span>模型中心</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('workflow')" key="workflow">
          <ApartmentOutlined />
          <span>工作流编排</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('users')" key="users">
          <TeamOutlined />
          <span>用户管理</span>
        </a-menu-item>
        <a-menu-item v-if="canSee('monitoring')" key="monitoring">
          <MonitorOutlined />
          <span>系统监控</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <!-- Main Content -->
    <a-layout>
      <!-- Header -->
      <a-layout-header :style="headerStyle">
        <div style="display: flex; align-items: center; gap: 16px;">
          <a-button type="text" @click="collapsed = !collapsed" style="font-size: 18px;">
            <MenuFoldOutlined v-if="!collapsed" />
            <MenuUnfoldOutlined v-else />
          </a-button>
          <a-breadcrumb>
            <a-breadcrumb-item>Admin</a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentTitle }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div style="display: flex; align-items: center; gap: 16px;">
          <!-- Theme Toggle -->
          <a-tooltip :title="isDark ? '切换到亮色模式' : '切换到暗色模式'">
            <a-button type="text" @click="themeStore.toggle()" style="font-size: 16px;">
              <BulbFilled v-if="isDark" />
              <BulbOutlined v-else />
            </a-button>
          </a-tooltip>
          <a-tag color="green">系统运行中</a-tag>
          <a-dropdown>
            <div style="cursor: pointer; display: flex; align-items: center; gap: 8px;">
              <a-avatar style="background-color: #4f46e5;">
                {{ avatarLetter }}
              </a-avatar>
              <div style="line-height: 1.3;">
                <div style="font-size: 14px; font-weight: 500;">{{ displayName }}</div>
                <div style="font-size: 12px; opacity: 0.6;">{{ roleLabel }}</div>
              </div>
            </div>
            <template #overlay>
              <a-menu>
                <a-menu-item key="info" disabled>
                  <span style="opacity: 0.6;">{{ authStore.user?.email }}</span>
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" @click="handleLogout">
                  <LogoutOutlined />
                  <span style="margin-left: 8px;">退出登录</span>
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <!-- Content -->
      <a-layout-content :style="contentStyle">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DashboardOutlined,
  CustomerServiceOutlined,
  MessageOutlined,
  BookOutlined,
  LineChartOutlined,
  BulbOutlined,
  BulbFilled,
  RobotOutlined,
  TeamOutlined,
  UsergroupAddOutlined,
  ThunderboltOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  ApartmentOutlined,
  MonitorOutlined,
  DatabaseOutlined
} from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const collapsed = ref(false)

const isDark = computed(() => themeStore.isDark)

const selectedKeys = ref<string[]>([route.name as string || 'dashboard'])

// --- Dynamic styles based on theme ---
const siderStyle = computed(() => isDark.value
  ? 'background: linear-gradient(180deg, #141414 0%, #1d1d1d 100%);'
  : 'background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);'
)

const headerStyle = computed(() => ({
  background: isDark.value ? '#1f1f1f' : '#fff',
  padding: '0 24px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  boxShadow: isDark.value ? '0 1px 4px rgba(0,0,0,0.3)' : '0 1px 4px rgba(0,0,0,0.06)',
  zIndex: 10,
}))

const contentStyle = computed(() => ({
  margin: '16px',
  padding: '24px',
  background: isDark.value ? '#141414' : '#f5f5f5',
  overflow: 'auto',
}))

// --- Permission map for menu items ---
const menuPermissions: Record<string, string> = {
  dashboard: 'dashboard:view',
  tasks: 'ticket:view',
  conversations: 'conversation:view',
  knowledge: 'knowledge:view',
  analytics: 'analytics:view',
  memories: 'memory:view',
  agents: 'agent:view',
  employees: 'agent:view',
  'employee-workbench': 'agent:view',
  models: 'model:view',
  workflow: 'agent:view',
  users: 'user:view',
  monitoring: 'system:config'
}

function canSee(key: string): boolean {
  const perm = menuPermissions[key]
  if (!perm) return true
  return authStore.hasPermission(perm)
}

// --- User display ---
const displayName = computed(() => authStore.user?.full_name || authStore.user?.username || 'User')
const avatarLetter = computed(() => {
  const name = authStore.user?.full_name || authStore.user?.username || 'U'
  return name.charAt(0).toUpperCase()
})
const roleLabel = computed(() => {
  const roles = authStore.user?.roles || []
  const map: Record<string, string> = {
    super_admin: '超级管理员',
    ai_admin: 'AI 管理员',
    business_admin: '业务管理员',
    developer: '开发者',
    customer_service: '客服',
    user: '普通用户'
  }
  return roles.map(r => map[r] || r).join(', ') || '用户'
})

// --- Current title ---
const currentTitle = computed(() => {
  const name = route.name as string
  const map: Record<string, string> = {
    Dashboard: '仪表盘',
    Tasks: '工单管理',
    Conversations: '对话管理',
    Knowledge: '知识库',
    Analytics: '执行追踪',
    Memories: '记忆管理',
    Agents: 'Agent 管理',
    Employees: 'AI 员工',
    EmployeeWorkbench: '员工工作台',
    Models: '模型中心',
    Workflow: '工作流编排',
    Users: '用户管理',
    Monitoring: '系统监控'
  }
  return map[name] || '仪表盘'
})

watch(() => route.name, (newName) => {
  if (newName) selectedKeys.value = [newName as string]
})

function onMenuClick({ key }: { key: string }) {
  router.push(`/${key}`)
}

async function handleLogout() {
  await authStore.logout()
  message.success('已退出登录')
  router.push('/login')
}

// --- Restore auth state on mount ---
onMounted(async () => {
  authStore.restoreFromStorage()
  if (authStore.isLoggedIn && !authStore.user) {
    try {
      await authStore.fetchUser()
    } catch {
      router.push('/login')
    }
  }
  if (!authStore.isLoggedIn) {
    router.push('/login')
  }
})
</script>
