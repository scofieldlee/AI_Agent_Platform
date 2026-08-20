import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '仪表盘', icon: 'DashboardOutlined', permission: 'dashboard:view' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/Tasks.vue'),
        meta: { title: '工单管理', icon: 'CustomerServiceOutlined', permission: 'ticket:view' }
      },
      {
        path: 'conversations',
        name: 'Conversations',
        component: () => import('@/views/Conversations.vue'),
        meta: { title: '对话管理', icon: 'MessageOutlined', permission: 'conversation:view' }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/Knowledge.vue'),
        meta: { title: '知识库', icon: 'BookOutlined', permission: 'knowledge:view' }
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/Analytics.vue'),
        meta: { title: '执行追踪', icon: 'LineChartOutlined', permission: 'analytics:view' }
      },
      {
        path: 'memories',
        name: 'Memories',
        component: () => import('@/views/Memories.vue'),
        meta: { title: '记忆管理', icon: 'BulbOutlined', permission: 'memory:view' }
      },
      {
        path: 'agents',
        name: 'Agents',
        component: () => import('@/views/Agents.vue'),
        meta: { title: 'Agent 管理', icon: 'RobotOutlined', permission: 'agent:view' }
      },
      {
        path: 'employees',
        name: 'Employees',
        component: () => import('@/views/Employees.vue'),
        meta: { title: 'AI 员工', icon: 'UsergroupAddOutlined', permission: 'agent:view' }
      },
      {
        path: 'employee-workbench',
        name: 'EmployeeWorkbench',
        component: () => import('@/views/EmployeeWorkbench.vue'),
        meta: { title: 'AI 员工工作台', icon: 'ThunderboltOutlined', permission: 'agent:view' }
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/Models.vue'),
        meta: { title: '模型中心', icon: 'DatabaseOutlined', permission: 'model:view' }
      },
      {
        path: 'workflow',
        name: 'Workflow',
        component: () => import('@/views/WorkflowEditor.vue'),
        meta: { title: '工作流编排', icon: 'ApartmentOutlined', permission: 'agent:view' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { title: '用户管理', icon: 'TeamOutlined', permission: 'user:view' }
      },
      {
        path: 'roles',
        name: 'Roles',
        component: () => import('@/views/Roles.vue'),
        meta: { title: '角色权限', icon: 'SafetyOutlined', permission: 'user:manage' }
      },
      {
        path: 'monitoring',
        name: 'Monitoring',
        component: () => import('@/views/Monitoring.vue'),
        meta: { title: '系统监控', icon: 'MonitorOutlined', permission: 'system:config' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// --- Navigation guard ---
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')

  // Public routes (login) — allow if not authenticated
  if (to.meta.public) {
    if (token && to.name === 'Login') {
      next('/dashboard')
    } else {
      next()
    }
    return
  }

  // Protected routes — require token
  if (!token) {
    next('/login')
    return
  }

  next()
})

export default router
