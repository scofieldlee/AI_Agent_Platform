import axios from 'axios'
import { message } from 'ant-design-vue'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

// --- Request interceptor: attach JWT ---
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// --- Response interceptor: handle 401 ---
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message || '请求失败'

    if (status === 401) {
      // Token expired or not authenticated — redirect to login
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      if (window.location.pathname !== '/login') {
        message.warning('登录已过期，请重新登录')
        window.location.href = '/login'
      }
    } else if (status === 403) {
      message.error(`权限不足: ${msg}`)
    } else {
      message.error(msg)
    }
    return Promise.reject(error)
  }
)

// ===== Auth =====
export const authApi = {
  login: (username: string, password: string) =>
    client.post('/auth/login', { username, password }),
  me: () => client.get('/auth/me'),
  refresh: (refreshToken: string) =>
    client.post('/auth/refresh', { refresh_token: refreshToken }),
  logout: () => client.post('/auth/logout'),
  listUsers: () => client.get('/auth/users'),
  listRoles: () => client.get('/auth/roles'),
  createUser: (data: {
    username: string; email: string; password: string;
    full_name?: string; department?: string; phone?: string;
    role_codes: string[]; is_active?: boolean; is_superuser?: boolean;
  }) => client.post('/auth/users', data),
  updateUser: (id: number, data: {
    full_name?: string; department?: string; phone?: string;
    is_active?: boolean; is_superuser?: boolean; role_codes?: string[];
  }) => client.patch(`/auth/users/${id}`, data)
}

// ===== Analytics =====
export const analyticsApi = {
  getStats: () => client.get('/analytics/stats'),
  getTraces: (params?: { limit?: number; offset?: number }) => client.get('/analytics/traces', { params }),
  getTrace: (traceId: string) => client.get(`/analytics/traces/${traceId}`),
  getSpans: (traceId: string) => client.get(`/analytics/traces/${traceId}/spans`)
}

// ===== Human Tasks =====
export const tasksApi = {
  list: (params?: { status?: string; priority?: string; page?: number; page_size?: number }) =>
    client.get('/human-tasks', { params }),
  stats: () => client.get('/human-tasks/stats'),
  detail: (id: number) => client.get(`/human-tasks/${id}`),
  assign: (id: number, assigneeId: string) => client.post(`/human-tasks/${id}/assign`, { assignee_id: assigneeId }),
  resolve: (id: number, data: { resolution_note: string; resolution_type?: string }) =>
    client.post(`/human-tasks/${id}/resolve`, data)
}

// ===== Conversations =====
export const conversationsApi = {
  list: (params?: { limit?: number; offset?: number }) => client.get('/conversations', { params }),
  messages: (conversationId: string) => client.get(`/conversations/${conversationId}/messages`)
}

// ===== Knowledge =====
export const knowledgeApi = {
  list: () => client.get('/knowledge'),
  create: (data: { name: string; kb_type?: string; source_type?: string; source_path: string }) =>
    client.post('/knowledge', data),
  documents: (kbId: number) => client.get(`/knowledge/${kbId}/documents`),
  sync: (kbId: number) => client.post(`/knowledge/${kbId}/sync`),
  importFile: (kbId: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return client.post(`/knowledge/${kbId}/import`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000  // embedding large files can take a while
    })
  },
  downloadTemplate: (kbId: number) =>
    client.get(`/knowledge/${kbId}/import-template`, {
      responseType: 'blob',
      timeout: 30000
    })
}

// ===== Memories =====
export const memoriesApi = {
  list: (params?: { page?: number; size?: number; memory_type?: string }) =>
    client.get('/memories', { params }),
  delete: (id: number) => client.delete(`/memories/${id}`),
  search: (query: string) => client.get('/memories/search/results', { params: { query } })
}

// ===== Agents =====
export const agentsApi = {
  list: () => client.get('/agents'),
  detail: (id: number) => client.get(`/agents/${id}`),
  fullDetail: (id: number) => client.get(`/agents/${id}/detail`),
  update: (id: number, data: {
    name?: string; description?: string; status?: string;
    config?: Record<string, any>; is_active?: boolean;
  }) => client.patch(`/agents/${id}`, data),
  delete: (id: number) => client.delete(`/agents/${id}`),
  archive: (id: number) => client.delete(`/agents/${id}`),
  bindTools: (id: number, toolNames: string[]) =>
    client.put(`/agents/${id}/tools`, { tool_names: toolNames }),
  bindKnowledge: (id: number, kbIds: number[]) =>
    client.put(`/agents/${id}/knowledge`, { knowledge_base_ids: kbIds }),
  bindWorkflow: (id: number, workflowIds: number[]) =>
    client.put(`/agents/${id}/workflow`, { workflow_ids: workflowIds })
}

// ===== Tools =====
export const toolsApi = {
  list: () => client.get('/tools')
}

// ===== Workflow =====
export const workflowApi = {
  list: () => client.get('/workflow'),
  create: (data: {
    name: string; code: string; description?: string;
    workflow_type?: string; graph_config?: Record<string, any>;
  }) => client.post('/workflow', data),
  detail: (id: number) => client.get(`/workflow/${id}`),
  update: (id: number, data: {
    name?: string; description?: string; workflow_type?: string;
    graph_config?: Record<string, any>; is_active?: boolean;
  }) => client.put(`/workflow/${id}`, data),
  delete: (id: number) => client.delete(`/workflow/${id}`),
  publish: (id: number) => client.post(`/workflow/${id}/publish`),
  getDefinition: () => client.get('/workflow/definition'),
  getTraces: (params?: { limit?: number; offset?: number }) =>
    client.get('/workflow/traces', { params }),
  getExecutionPath: (traceId: string) =>
    client.get(`/workflow/execution-path/${traceId}`)
}

// ===== Models =====
export const modelsApi = {
  selectable: () => client.get('/models/configs/selectable'),
  listProviders: () => client.get('/models/providers'),
  listConfigs: () => client.get('/models/configs'),
}

// ===== Monitoring =====
export const monitoringApi = {
  overview: () => client.get('/monitoring/overview'),
  health: () => client.get('/monitoring/health'),
  system: () => client.get('/monitoring/system'),
  database: () => client.get('/monitoring/database'),
  redis: () => client.get('/monitoring/redis'),
  llm: () => client.get('/monitoring/llm'),
  agents: () => client.get('/monitoring/agents')
}

export default client
