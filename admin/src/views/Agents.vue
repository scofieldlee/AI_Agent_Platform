<template>
  <div class="agents-page">
    <!-- Agent List -->
    <a-card title="Agent 列表">
      <template #extra>
        <a-space>
          <a-tag color="blue">{{ agents.length }} 个 Agent</a-tag>
          <a-button type="primary" size="small" @click="showCreateModal = true">
            <PlusOutlined /> 新建 Agent
          </a-button>
        </a-space>
      </template>
      <a-table
        :columns="columns"
        :data-source="agents"
        :loading="loading"
        row-key="id"
        :pagination="false"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-space>
              <a-avatar :size="36" style="background-color: #4f46e5;">{{ record.name?.charAt(0) }}</a-avatar>
              <div>
                <div style="font-weight: 600;">{{ record.name }}</div>
                <div style="font-size: 12px; color: #999;">{{ record.code }}</div>
              </div>
            </a-space>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'agent_type'">
            {{ typeLabel(record.agent_type) }}
          </template>
          <template v-if="column.key === 'version'">
            <a-tag color="blue">v{{ record.version }}</a-tag>
          </template>
          <template v-if="column.key === 'is_active'">
            <a-tag :color="record.is_active ? 'green' : 'default'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
          </template>
          <template v-if="column.key === 'chat_link'">
            <div v-if="record.chat_token && record.status === 'published'" style="display: flex; align-items: center; gap: 4px;">
              <a-tooltip :title="`/chat?token=${record.chat_token}`">
                <a-button type="link" size="small" @click="openChatUrl(record.chat_token)">
                  <LinkOutlined /> 打开对话
                </a-button>
              </a-tooltip>
              <a-button type="text" size="small" @click="copyChatUrl(record.chat_token)">
                <CopyOutlined />
              </a-button>
            </div>
            <span v-else style="font-size: 12px; color: #999;">未发布</span>
          </template>
          <template v-if="column.key === 'workflow'">
            <a-tooltip v-if="record.workflow" :title="`工作流编码: ${record.workflow.code}`">
              <a-tag color="geekblue" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ record.workflow.name }}
              </a-tag>
            </a-tooltip>
            <span v-else style="font-size: 12px; color: #999;">默认</span>
          </template>
          <template v-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openTestModal(record)">
                <MessageOutlined /> 测试
              </a-button>
              <a-button type="link" size="small" @click="openConfigDrawer(record)">
                <EditOutlined /> 配置
              </a-button>
              <a-popconfirm
                v-if="record.status !== 'published'"
                title="确定要删除这个 Agent 吗？"
                ok-text="删除"
                cancel-text="取消"
                ok-type="danger"
                @confirm="handleDelete(record)"
              >
                <a-button type="link" size="small" danger>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-popconfirm>
              <a-tooltip v-else title="已发布的 Agent 不能删除，请先取消发布">
                <a-button type="link" size="small" danger disabled>
                  <DeleteOutlined /> 删除
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Config Drawer -->
    <a-drawer
      v-model:open="drawerVisible"
      :title="editingAgent ? `${editingAgent.name} — 配置编辑` : 'Agent 配置'"
      placement="right"
      width="640"
      :destroy-on-close="true"
    >
      <a-spin :spinning="detailLoading">
        <div v-if="agentDetail" class="config-form">
          <!-- Basic Info -->
          <div class="config-section">
            <div class="section-title"><InfoCircleOutlined /> 基本信息</div>
            <a-form layout="vertical">
              <a-form-item label="Agent 名称">
                <a-input v-model:value="formData.name" placeholder="Agent 名称" />
              </a-form-item>
              <a-form-item label="描述">
                <a-textarea v-model:value="formData.description" :rows="2" placeholder="Agent 描述" />
              </a-form-item>
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="状态">
                    <a-select v-model:value="formData.status" style="width: 100%">
                      <a-select-option value="draft">草稿</a-select-option>
                      <a-select-option value="published">已发布</a-select-option>
                      <a-select-option value="running">运行中</a-select-option>
                      <a-select-option value="suspended">已暂停</a-select-option>
                      <a-select-option value="archived">已归档</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="启用状态">
                    <a-switch
                      v-model:checked="formData.is_active"
                      checked-children="启用"
                      un-checked-children="停用"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-form>
          </div>

          <!-- System Prompt -->
          <div class="config-section">
            <div class="section-title"><RobotOutlined /> System Prompt</div>
            <a-form layout="vertical">
              <a-form-item>
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                  <span style="font-size: 12px; color: #999;">定义 Agent 的角色、职责和回答规则</span>
                  <span style="font-size: 12px;" :style="{ color: formData.system_prompt.length > 3000 ? '#ff4d4f' : '#999' }">
                    {{ formData.system_prompt.length }} 字符
                  </span>
                </div>
                <a-textarea
                  v-model:value="formData.system_prompt"
                  :rows="10"
                  placeholder="输入 Agent 的 System Prompt..."
                  style="font-family: 'SF Mono', 'Monaco', 'Courier New', monospace; font-size: 13px;"
                />
              </a-form-item>
            </a-form>
          </div>

          <!-- Model Parameters -->
          <div class="config-section">
            <div class="section-title"><SettingOutlined /> 模型参数</div>
            <a-form layout="vertical">
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="模型">
                    <a-select v-model:value="formData.model_config_id" style="width: 100%" placeholder="选择模型">
                      <a-select-option v-for="opt in modelOptions" :key="opt.id" :value="opt.id">
                        {{ opt.provider_name }} / {{ opt.name }}
                        <a-tag size="small" style="margin-left: 4px;">{{ modelTypeLabel(opt.model_type) }}</a-tag>
                      </a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="Max Tokens">
                    <a-input-number
                      v-model:value="formData.max_tokens"
                      :min="256"
                      :max="8192"
                      :step="256"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="Temperature">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <a-slider
                    v-model:value="formData.temperature"
                    :min="0"
                    :max="2"
                    :step="0.1"
                    style="flex: 1;"
                  />
                  <span style="font-weight: 600; min-width: 36px; text-align: right;">{{ formData.temperature }}</span>
                </div>
                <div style="font-size: 12px; color: #999; margin-top: -4px;">
                  0 = 确定性回答, 2 = 创造性回答
                </div>
              </a-form-item>
            </a-form>
          </div>

          <!-- Input Form / Attachment Support -->
          <div class="config-section">
            <div class="section-title"><PaperClipOutlined /> 输入形式 / 附件支持</div>
            <a-form layout="vertical">
              <a-form-item label="允许的输入类型">
                <span style="font-size: 12px; color: #999; display: block; margin-bottom: 8px;">
                  控制用户在该 Agent 对话中可以上传的文件类型
                </span>
                <a-checkbox-group v-model:value="formData.allowed_input_types">
                  <a-row :gutter="[8, 8]">
                    <a-col :span="8">
                      <a-checkbox value="text">
                        <span style="font-size: 13px;">📄 文本</span>
                        <div style="font-size: 11px; color: #999;">.txt .md .csv</div>
                      </a-checkbox>
                    </a-col>
                    <a-col :span="8">
                      <a-checkbox value="pdf">
                        <span style="font-size: 13px;">📕 PDF</span>
                        <div style="font-size: 11px; color: #999;">.pdf</div>
                      </a-checkbox>
                    </a-col>
                    <a-col :span="8">
                      <a-checkbox value="word">
                        <span style="font-size: 13px;">📝 Word</span>
                        <div style="font-size: 11px; color: #999;">.docx .doc</div>
                      </a-checkbox>
                    </a-col>
                    <a-col :span="8">
                      <a-checkbox value="excel">
                        <span style="font-size: 13px;">📊 Excel</span>
                        <div style="font-size: 11px; color: #999;">.xlsx .xls</div>
                      </a-checkbox>
                    </a-col>
                    <a-col :span="8">
                      <a-checkbox value="image">
                        <span style="font-size: 13px;">🖼️ 图片</span>
                        <div style="font-size: 11px; color: #999;">需多模态模型</div>
                      </a-checkbox>
                    </a-col>
                    <a-col :span="8">
                      <a-checkbox value="video">
                        <span style="font-size: 13px;">🎬 视频</span>
                        <div style="font-size: 11px; color: #999;">存储+转人工</div>
                      </a-checkbox>
                    </a-col>
                  </a-row>
                </a-checkbox-group>
              </a-form-item>
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="单文件大小上限 (MB)">
                    <a-input-number
                      v-model:value="formData.max_file_size_mb"
                      :min="1"
                      :max="100"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="单条消息最大文件数">
                    <a-input-number
                      v-model:value="formData.max_files_per_message"
                      :min="1"
                      :max="20"
                      style="width: 100%"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-alert
                v-if="formData.allowed_input_types.includes('image') && selectedModelType !== 'vision'"
                type="warning"
                show-icon
                message="图片附件需要多模态模型支持"
                description="当前选择的模型可能不支持图片识别。建议配置 GPT-4o、Qwen-VL 等视觉模型。"
                style="margin-top: 4px;"
              />
            </a-form>
          </div>

          <!-- Tool Bindings -->
          <div class="config-section">
            <div class="section-title"><ToolOutlined /> 工具绑定</div>
            <a-checkbox-group v-model:value="formData.tool_bindings" style="width: 100%;">
              <div v-for="tool in allTools" :key="tool.name" class="binding-item">
                <a-checkbox :value="tool.name">
                  <div class="binding-info">
                    <div class="binding-name">
                      {{ tool.name }}
                      <a-tag :color="toolTypeColor(tool.tool_type)" style="margin-left: 4px; font-size: 11px;">{{ tool.tool_type }}</a-tag>
                    </div>
                    <div class="binding-desc">{{ tool.description?.substring(0, 80) }}{{ tool.description?.length > 80 ? '...' : '' }}</div>
                  </div>
                </a-checkbox>
              </div>
            </a-checkbox-group>
          </div>

          <!-- Chat UI Config -->
          <div class="config-section">
            <div class="section-title"><MessageOutlined /> 聊天界面配置</div>
            <a-form layout="vertical">
              <a-row :gutter="16">
                <a-col :span="20">
                  <a-form-item label="欢迎语">
                    <a-textarea
                      v-model:value="formData.welcome_message"
                      :rows="2"
                      placeholder="如：👋 你好，我是商品客服 Agent"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="4">
                  <a-form-item label="头像 Emoji">
                    <a-input
                      v-model:value="formData.avatar_emoji"
                      placeholder="🛍️"
                      :maxlength="2"
                      style="text-align: center; font-size: 18px;"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
              <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; font-weight: 500;">建议问题</span>
                <a-button type="dashed" size="small" @click="addSuggestedQuestion">
                  <PlusOutlined /> 添加问题
                </a-button>
              </div>
              <div v-if="formData.suggested_questions.length === 0" style="font-size: 12px; color: #999; padding: 8px 0;">
                暂无建议问题，用户进入对话页面将只看到欢迎语
              </div>
              <div v-for="(q, idx) in formData.suggested_questions" :key="idx" class="suggestion-edit-item">
                <a-row :gutter="8" align="middle">
                  <a-col :span="2">
                    <a-input v-model:value="q.icon" placeholder="📦" :maxlength="2" style="text-align: center;" />
                  </a-col>
                  <a-col :span="6">
                    <a-input v-model:value="q.title" placeholder="标题" />
                  </a-col>
                  <a-col :span="6">
                    <a-input v-model:value="q.desc" placeholder="描述" />
                  </a-col>
                  <a-col :span="8">
                    <a-input v-model:value="q.question" placeholder="点击后发送的问题" />
                  </a-col>
                  <a-col :span="2">
                    <a-button type="text" danger size="small" @click="removeSuggestedQuestion(idx)">
                      <DeleteOutlined />
                    </a-button>
                  </a-col>
                </a-row>
              </div>
            </a-form>
          </div>

          <!-- Knowledge Bindings -->
          <div class="config-section">
            <div class="section-title"><BookOutlined /> 知识库绑定</div>
            <a-checkbox-group v-model:value="formData.knowledge_bindings" style="width: 100%;">
              <div v-for="kb in allKnowledgeBases" :key="kb.id" class="binding-item">
                <a-checkbox :value="kb.id">
                  <div class="binding-info">
                    <div class="binding-name">
                      {{ kb.name }}
                      <a-tag style="margin-left: 4px; font-size: 11px;">{{ kb.kb_type || 'general' }}</a-tag>
                    </div>
                    <div class="binding-desc">{{ kb.description || `${kb.document_count} 篇文档` }}</div>
                  </div>
                </a-checkbox>
              </div>
              <div v-if="allKnowledgeBases.length === 0" style="color: #999; font-size: 13px;">
                暂无知识库
              </div>
            </a-checkbox-group>
          </div>

          <!-- Workflow Bindings -->
          <div class="config-section">
            <div class="section-title"><ApartmentOutlined /> 工作流绑定</div>
            <div style="font-size: 12px; color: #999; margin-bottom: 10px; line-height: 1.5;">
              选择该 Agent 运行时使用的工作流。勾选的第一个为<span style="color: #4f46e5; font-weight: 600;">主工作流</span>，
              未绑定任何工作流时使用全局默认工作流。
              <a-button type="link" size="small" style="padding: 0 0 0 4px;" @click="openWorkflowEditor">
                管理工作流
              </a-button>
            </div>
            <a-checkbox-group v-model:value="formData.workflow_bindings" style="width: 100%;">
              <div v-for="wf in allWorkflows" :key="wf.id" class="binding-item">
                <a-checkbox :value="wf.id">
                  <div class="binding-info">
                    <div class="binding-name">
                      {{ wf.name }}
                      <a-tag :color="wf.status === 'published' ? 'green' : 'orange'" style="margin-left: 4px; font-size: 11px;">
                        {{ wf.status === 'published' ? '已发布' : '草稿' }}
                      </a-tag>
                      <a-tag style="font-size: 11px;">{{ wf.node_count }} 节点</a-tag>
                    </div>
                    <div class="binding-desc">
                      {{ wf.code }}<template v-if="wf.description"> · {{ wf.description }}</template>
                    </div>
                  </div>
                </a-checkbox>
              </div>
              <div v-if="allWorkflows.length === 0" style="color: #999; font-size: 13px;">
                暂无工作流，请先在工作流编辑器中创建
              </div>
            </a-checkbox-group>
          </div>

          <!-- Version History -->
          <div class="config-section" v-if="agentDetail.versions?.length > 0">
            <div class="section-title"><HistoryOutlined /> 版本历史 ({{ agentDetail.versions.length }})</div>
            <a-timeline style="margin-top: 8px;">
              <a-timeline-item v-for="ver in agentDetail.versions" :key="ver.id" :color="ver.status === 'published' ? 'green' : 'gray'">
                <div style="font-size: 13px;">
                  <span style="font-weight: 600;">v{{ ver.version }}</span>
                  <span style="color: #999; margin-left: 8px;">{{ formatDate(ver.created_at) }}</span>
                </div>
                <div v-if="ver.changelog" style="font-size: 12px; color: #666;">{{ ver.changelog }}</div>
              </a-timeline-item>
            </a-timeline>
          </div>
        </div>
      </a-spin>

      <!-- Drawer Footer -->
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <a-button @click="drawerVisible = false">取消</a-button>
          <a-button type="primary" :loading="saving" @click="saveConfig">
            <SaveOutlined /> 保存配置
          </a-button>
        </div>
      </template>
    </a-drawer>

    <!-- Test Chat Modal -->
    <a-modal
      v-model:open="testModalVisible"
      :title="selectedAgentForTest ? `快速测试 — ${selectedAgentForTest.name}` : '快速测试'"
      width="720px"
      :footer="null"
      :destroy-on-close="false"
    >
      <div class="test-chat">
        <div class="chat-messages" ref="chatMessagesRef">
          <div v-if="testMessages.length === 0" class="chat-empty">
            <div style="color: #999; font-size: 13px;">
              向 <strong>{{ selectedAgentForTest?.name }}</strong> 发送消息开始测试
            </div>
          </div>
          <div v-for="msg in testMessages" :key="msg.id" :class="['chat-msg', msg.role]">
            <div class="chat-bubble" :class="{ 'chat-error': msg.meta?.error }">
              <div class="chat-role">{{ msg.role === 'user' ? '顾客' : 'Agent' }}</div>
              <div class="chat-text">{{ msg.content }}</div>
              <div v-if="msg.meta" class="chat-meta">
                <a-tag v-if="msg.meta.intent" size="small" color="blue">{{ msg.meta.intent }}</a-tag>
                <a-tag v-if="msg.meta.confidence !== undefined" size="small">
                  置信度 {{ (msg.meta.confidence * 100).toFixed(0) }}%
                </a-tag>
                <a-tag v-if="msg.meta.need_human" size="small" color="red">转人工</a-tag>
              </div>
            </div>
          </div>
          <div v-if="testLoading" class="chat-msg agent">
            <div class="chat-bubble">
              <a-spin size="small" />
              <span style="margin-left: 8px; color: #999;">Agent 思考中...</span>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <a-input-search
            v-model:value="testInput"
            placeholder="输入测试消息..."
            enter-button="发送"
            :loading="testLoading"
            @search="sendTestMessage"
          />
        </div>
      </div>
    </a-modal>

    <!-- Create Agent Modal -->
    <a-modal v-model:open="showCreateModal" title="新建 Agent" @ok="handleCreate" :confirm-loading="creating">
      <a-form layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="newAgent.name" placeholder="如：售后客服 Agent" />
        </a-form-item>
        <a-form-item label="编码" required>
          <a-input v-model:value="newAgent.code" placeholder="如：after_sale_agent" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="newAgent.description" :rows="2" placeholder="Agent 描述" />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="newAgent.agent_type">
            <a-select-option value="customer_service">客服</a-select-option>
            <a-select-option value="config">配置型</a-select-option>
            <a-select-option value="assistant">助手</a-select-option>
            <a-select-option value="analyst">分析</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, EditOutlined, SaveOutlined, DeleteOutlined, MessageOutlined,
  InfoCircleOutlined, RobotOutlined, SettingOutlined,
  ToolOutlined, BookOutlined, HistoryOutlined,
  PaperClipOutlined, ApartmentOutlined,
  ExclamationCircleOutlined,
  LinkOutlined, CopyOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { agentsApi, toolsApi, knowledgeApi, modelsApi, workflowApi } from '@/api/client'

// --- Agent list ---
const loading = ref(false)
const agents = ref<any[]>([])
const columns = [
  { title: 'Agent', key: 'name', width: 250 },
  { title: '类型', key: 'agent_type', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '工作流', key: 'workflow', width: 160 },
  { title: '版本', key: 'version', width: 80 },
  { title: '启用', key: 'is_active', width: 80 },
  { title: '对话链接', key: 'chat_link', width: 180 },
  { title: '操作', key: 'action', width: 200 },
]

// --- Drawer ---
const drawerVisible = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const editingAgent = ref<any>(null)
const agentDetail = ref<any>(null)
const allTools = ref<any[]>([])
const allKnowledgeBases = ref<any[]>([])
const allWorkflows = ref<any[]>([])
const modelOptions = ref<any[]>([])

const formData = reactive({
  name: '',
  description: '',
  status: 'draft',
  is_active: true,
  system_prompt: '',
  model_config_id: null as number | null,
  temperature: 0.3,
  max_tokens: 4096,
  tool_bindings: [] as string[],
  knowledge_bindings: [] as number[],
  workflow_bindings: [] as number[],
  // Attachment input config
  allowed_input_types: ['text'] as string[],
  max_file_size_mb: 10,
  max_files_per_message: 5,
  // Chat UI config
  welcome_message: '',
  avatar_emoji: '',
  suggested_questions: [] as Array<{ icon: string; title: string; desc: string; question: string }>,
})

// --- Test chat ---
const testModalVisible = ref(false)
const selectedAgentForTest = ref<any>(null)
const testMessages = ref<any[]>([])
const testInput = ref('')
const testLoading = ref(false)
const chatMessagesRef = ref<HTMLElement>()

// --- Create modal ---
const showCreateModal = ref(false)
const creating = ref(false)
const newAgent = reactive({ name: '', code: '', description: '', agent_type: 'customer_service' })

const selectedModelType = computed(() => {
  const opt = modelOptions.value.find(o => o.id === formData.model_config_id)
  return opt?.model_type || 'chat'
})

function statusColor(s: string) {
  return ({ active: 'green', published: 'green', running: 'green', draft: 'orange', suspended: 'default', archived: 'red' } as any)[s] || 'default'
}
function statusLabel(s: string) {
  return ({ active: '运行中', published: '已发布', running: '运行中', draft: '草稿', suspended: '已暂停', archived: '已归档' } as any)[s] || s
}
function typeLabel(t: string) {
  return ({ customer_service: '客服', config: '配置型', assistant: '助手', analyst: '分析', custom: '自定义' } as any)[t] || t
}
function toolTypeColor(t: string) {
  return ({ internal: 'blue', business: 'green', api: 'purple', database: 'orange', mcp: 'cyan' } as any)[t] || 'default'
}
function modelTypeLabel(t: string) {
  return ({ chat: '对话', reasoning: '推理', vision: '视觉', embedding: 'Embedding', rerank: 'Rerank', speech: '语音' } as any)[t] || t
}
function formatDate(d: string) {
  return d ? dayjs(d).format('YYYY-MM-DD HH:mm') : '-'
}

function getChatUrl(token: string) {
  const origin = window.location.origin
  // Admin runs on :5173, chat page is on :8000
  const chatOrigin = origin.replace(':5173', ':8000')
  return `${chatOrigin}/chat?token=${token}`
}

function openChatUrl(token: string) {
  window.open(getChatUrl(token), '_blank')
}

async function copyChatUrl(token: string) {
  const url = getChatUrl(token)
  try {
    await navigator.clipboard.writeText(url)
    message.success('对话链接已复制')
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement('textarea')
    textarea.value = url
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    message.success('对话链接已复制')
  }
}

function addSuggestedQuestion() {
  formData.suggested_questions.push({ icon: '', title: '', desc: '', question: '' })
}

function removeSuggestedQuestion(idx: number) {
  formData.suggested_questions.splice(idx, 1)
}

async function fetchAgents() {
  loading.value = true
  try {
    const res = await agentsApi.list()
    agents.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function fetchTools() {
  try {
    const res = await toolsApi.list()
    allTools.value = res.data || []
  } catch { /* silent */ }
}

async function fetchKnowledgeBases() {
  try {
    const res = await knowledgeApi.list()
    allKnowledgeBases.value = res.data || []
  } catch { /* silent */ }
}

async function fetchWorkflows() {
  try {
    const res = await workflowApi.list()
    allWorkflows.value = res.data || []
  } catch { /* silent */ }
}

function openWorkflowEditor() {
  drawerVisible.value = false
  window.location.href = '/workflow'
}

async function fetchModelOptions() {
  try {
    const res = await modelsApi.selectable()
    modelOptions.value = res.data || []
  } catch { /* silent */ }
}

function openTestModal(agent: any) {
  selectedAgentForTest.value = agent
  testMessages.value = []
  testInput.value = ''
  testModalVisible.value = true
}

async function openConfigDrawer(agent: any) {
  editingAgent.value = agent
  drawerVisible.value = true
  detailLoading.value = true

  // Ensure model options are loaded before populating form
  if (modelOptions.value.length === 0) {
    await fetchModelOptions()
  }
  // Ensure workflow options are loaded before populating form
  if (allWorkflows.value.length === 0) {
    await fetchWorkflows()
  }

  try {
    // Fetch full detail with bindings
    const res = await agentsApi.fullDetail(agent.id)
    agentDetail.value = res.data

    const d = res.data
    const config = d.config || {}

    // Populate form
    formData.name = d.name || ''
    formData.description = d.description || ''
    formData.status = d.status || 'draft'
    formData.is_active = d.is_active ?? true
    formData.system_prompt = config.system_prompt || ''
    formData.model_config_id = config.model_config_id ?? null
    // Backward compatibility: old configs stored model as string
    if (!formData.model_config_id && config.model) {
      const matched = modelOptions.value.find(o => o.model_id === config.model)
      if (matched) {
        formData.model_config_id = matched.id
      }
    }
    formData.temperature = config.temperature ?? 0.3
    formData.max_tokens = config.max_tokens ?? 4096
    formData.allowed_input_types = config.allowed_input_types || ['text']
    formData.max_file_size_mb = config.max_file_size_mb ?? 10
    formData.max_files_per_message = config.max_files_per_message ?? 5
    formData.welcome_message = config.welcome_message || ''
    formData.avatar_emoji = config.avatar_emoji || ''
    formData.suggested_questions = config.suggested_questions || []
    formData.tool_bindings = (d.tool_bindings || []).map((t: any) => t.tool_name)
    formData.knowledge_bindings = (d.knowledge_bindings || []).map((k: any) => k.knowledge_base_id)
    // Workflow bindings (primary first, per backend order)
    formData.workflow_bindings = (d.workflow_bindings || []).map((w: any) => w.workflow_id)
  } catch (err: any) {
    message.error('加载 Agent 详情失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    detailLoading.value = false
  }
}

async function saveConfig() {
  if (!editingAgent.value) return
  saving.value = true

  try {
    const agentId = editingAgent.value.id

    // 1. Update agent config + basic info
    await agentsApi.update(agentId, {
      name: formData.name,
      description: formData.description,
      status: formData.status,
      is_active: formData.is_active,
      config: {
        system_prompt: formData.system_prompt,
        model_config_id: formData.model_config_id,
        temperature: formData.temperature,
        max_tokens: formData.max_tokens,
        allowed_input_types: formData.allowed_input_types,
        max_file_size_mb: formData.max_file_size_mb,
        max_files_per_message: formData.max_files_per_message,
        welcome_message: formData.welcome_message,
        avatar_emoji: formData.avatar_emoji,
        suggested_questions: formData.suggested_questions,
      },
    })

    // 2. Update tool bindings
    await agentsApi.bindTools(agentId, formData.tool_bindings)

    // 3. Update knowledge bindings
    await agentsApi.bindKnowledge(agentId, formData.knowledge_bindings)

    // 4. Update workflow bindings (first selected = primary)
    await agentsApi.bindWorkflow(agentId, formData.workflow_bindings)

    message.success('Agent 配置已保存')
    await fetchAgents()
  } catch (err: any) {
    message.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function sendTestMessage() {
  if (!testInput.value.trim() || !selectedAgentForTest.value) return
  const userMsg = testInput.value.trim()
  testInput.value = ''

  testMessages.value.push({
    id: Date.now(),
    role: 'user',
    content: userMsg,
  })

  testLoading.value = true
  await nextTick()
  if (chatMessagesRef.value) {
    chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }

  try {
    const res = await fetch('/api/v1/conversations/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        user_id: 1,
        agent_id: selectedAgentForTest.value.id,
        message: userMsg,
      }),
    })

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}))
      const detail = errorData.detail || ''
      let friendlyMsg = detail || `请求失败 (HTTP ${res.status})`
      if (res.status === 404) friendlyMsg = 'Agent 不存在或已被删除，请重新选择'
      else if (res.status === 403) friendlyMsg = '该 Agent 未启用，请在配置中激活后再试'
      else if (res.status === 422) friendlyMsg = '请求参数有误，请刷新页面后重试'
      else if (res.status >= 500) friendlyMsg = 'AI 服务暂时不可用，请稍后重试。如果持续出现，请检查 DeepSeek API 状态。'
      testMessages.value.push({
        id: Date.now() + 1,
        role: 'agent',
        content: friendlyMsg,
        meta: { error: true },
      })
      return
    }

    const data = await res.json()
    testMessages.value.push({
      id: Date.now() + 1,
      role: 'agent',
      content: data.reply || '（Agent 未返回内容）',
      meta: {
        intent: data.intent,
        confidence: data.confidence,
        need_human: data.need_human,
      },
    })
  } catch (err: any) {
    testMessages.value.push({
      id: Date.now() + 1,
      role: 'agent',
      content: '网络请求失败，请检查服务是否正常运行: ' + err.message,
      meta: { error: true },
    })
  } finally {
    testLoading.value = false
    await nextTick()
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  }
}

async function handleDelete(agent: any) {
  if (agent.status === 'published') {
    message.warning('已发布的 Agent 不能删除，请先取消发布')
    return
  }
  try {
    await agentsApi.delete(agent.id)
    message.success('Agent 已删除')
    await fetchAgents()
  } catch (err: any) {
    message.error('删除失败: ' + (err.response?.data?.detail || err.message))
  }
}

async function handleCreate() {
  if (!newAgent.name || !newAgent.code) {
    message.warning('请填写名称和编码')
    return
  }
  creating.value = true
  try {
    await agentsApi.list() // ensure token works
    // Use raw POST to create agent
    const res = await fetch('/api/v1/agents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({
        name: newAgent.name,
        code: newAgent.code,
        description: newAgent.description,
        agent_type: newAgent.agent_type,
        config: {},
      }),
    })
    if (!res.ok) throw new Error('创建失败')
    message.success('Agent 创建成功')
    showCreateModal.value = false
    newAgent.name = ''
    newAgent.code = ''
    newAgent.description = ''
    await fetchAgents()
  } catch (err: any) {
    message.error('创建失败: ' + err.message)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  fetchAgents()
  fetchTools()
  fetchKnowledgeBases()
  fetchWorkflows()
  fetchModelOptions()
})
</script>

<style scoped>
.agents-page {
  max-width: 100%;
}

.config-form {
  padding-bottom: 24px;
}

.config-section {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--ant-color-fill-quaternary, #f5f5f5);
  border-radius: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-primary, #4f46e5);
}

.binding-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  background: var(--ant-color-bg-container, #fff);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
  transition: all 0.2s;
}

.binding-item:hover {
  border-color: var(--ant-color-primary, #4f46e5);
}

.binding-info {
  display: inline-block;
  margin-left: 8px;
  vertical-align: top;
}

.binding-name {
  font-size: 13px;
  font-weight: 600;
}

.binding-desc {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
  line-height: 1.4;
}

/* Test chat */
.test-chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-messages {
  height: 360px;
  overflow-y: auto;
  padding: 12px;
  background: var(--ant-color-fill-tertiary, #fafafa);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
}

.chat-msg {
  display: flex;
}

.chat-msg.user {
  justify-content: flex-end;
}

.chat-msg.agent {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.chat-msg.user .chat-bubble {
  background: var(--ant-color-primary, #4f46e5);
  color: #fff;
}

.chat-msg.agent .chat-bubble {
  background: var(--ant-color-bg-container, #fff);
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}

.chat-bubble.chat-error {
  background: #fff2f0 !important;
  border: 1px solid #ffccc7 !important;
  color: #cf1322 !important;
}

.chat-role {
  font-size: 11px;
  opacity: 0.7;
  margin-bottom: 4px;
}

.chat-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-meta {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.suggestion-edit-item {
  margin-bottom: 8px;
  padding: 8px;
  background: var(--ant-color-bg-container, #fff);
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}
</style>
