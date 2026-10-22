<template>
  <div class="agent-config-page">
    <!-- Page header -->
    <a-card class="header-card" :bordered="false">
      <div class="header-row">
        <div class="header-left">
          <a-button size="small" @click="goBack" style="margin-right: 12px;">
            <ArrowLeftOutlined /> 返回
          </a-button>
          <a-avatar :size="40" style="background-color: #4f46e5; font-size: 18px;">
            {{ formData.avatar_emoji || (agentDetail?.name || 'A').charAt(0) }}
          </a-avatar>
          <div style="margin-left: 12px;">
            <div class="header-title">
              {{ agentDetail?.name || 'Agent 配置' }}
              <a-tag v-if="agentDetail" :color="statusColor(agentDetail.status)" style="margin-left: 8px;">
                {{ statusLabel(agentDetail.status) }}
              </a-tag>
              <a-tag v-if="agentDetail" color="blue">v{{ agentDetail.version }}</a-tag>
            </div>
            <div class="header-sub">{{ agentDetail?.code }}</div>
          </div>
        </div>
        <a-space>
          <div v-if="agentDetail?.chat_token && agentDetail?.status === 'published'"
            style="display: flex; align-items: center; gap: 4px;">
            <a-button size="small" @click="openChatUrl(agentDetail.chat_token)">
              <LinkOutlined /> 打开对话
            </a-button>
            <a-button size="small" @click="copyChatUrl(agentDetail.chat_token)">
              <CopyOutlined /> 复制链接
            </a-button>
          </div>
          <a-button type="primary" :loading="saving" @click="saveConfig">
            <SaveOutlined /> 保存配置
          </a-button>
        </a-space>
      </div>
    </a-card>

    <a-spin :spinning="detailLoading">
      <div v-if="loadError" class="load-error">
        <a-result status="403" :title="loadError" sub-title="请确认你对该 Agent 拥有查看权限，或从列表页重新进入。">
          <template #extra>
            <a-button type="primary" @click="goBack">返回列表</a-button>
          </template>
        </a-result>
      </div>

      <a-card v-else-if="agentDetail" :bordered="false" class="tabs-card">
        <a-tabs v-model:activeKey="activeTab" tab-position="left" class="config-tabs">
          <!-- Tab: 基本信息 -->
          <a-tab-pane key="basic" tab="基础信息">
            <div class="tab-title"><InfoCircleOutlined /> 基础信息</div>
            <a-form layout="vertical" style="max-width: 640px;">
              <a-form-item label="Agent 名称">
                <a-input v-model:value="formData.name" placeholder="Agent 名称" />
              </a-form-item>
              <a-form-item label="描述">
                <a-textarea v-model:value="formData.description" :rows="3" placeholder="Agent 描述" />
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
                    <a-switch v-model:checked="formData.is_active" checked-children="启用" un-checked-children="停用" />
                  </a-form-item>
                </a-col>
              </a-row>
            </a-form>
          </a-tab-pane>

          <!-- Tab: 模型与提示词 -->
          <a-tab-pane key="model" tab="模型与提示词">
            <div class="tab-title"><RobotOutlined /> System Prompt</div>
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
                  :rows="12"
                  placeholder="输入 Agent 的 System Prompt..."
                  style="font-family: 'SF Mono', 'Monaco', 'Courier New', monospace; font-size: 13px;"
                />
              </a-form-item>
            </a-form>

            <div class="tab-title" style="margin-top: 24px;"><SettingOutlined /> 模型参数</div>
            <a-form layout="vertical" style="max-width: 640px;">
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
                    <a-input-number v-model:value="formData.max_tokens" :min="256" :max="8192" :step="256" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="Temperature">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <a-slider v-model:value="formData.temperature" :min="0" :max="2" :step="0.1" style="flex: 1;" />
                  <span style="font-weight: 600; min-width: 36px; text-align: right;">{{ formData.temperature }}</span>
                </div>
                <div style="font-size: 12px; color: #999; margin-top: -4px;">
                  0 = 确定性回答, 2 = 创造性回答
                </div>
              </a-form-item>
            </a-form>
          </a-tab-pane>

          <!-- Tab: 输入与附件 -->
          <a-tab-pane key="input" tab="输入与附件">
            <div class="tab-title"><PaperClipOutlined /> 输入形式 / 附件支持</div>
            <a-form layout="vertical" style="max-width: 680px;">
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
                    <a-input-number v-model:value="formData.max_file_size_mb" :min="1" :max="100" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="单条消息最大文件数">
                    <a-input-number v-model:value="formData.max_files_per_message" :min="1" :max="20" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-alert
                v-if="formData.allowed_input_types.includes('image') && selectedModelType !== 'vision'"
                type="warning" show-icon
                message="图片附件需要多模态模型支持"
                description="当前选择的模型可能不支持图片识别。建议配置 GPT-4o、Qwen-VL 等视觉模型。"
                style="margin-top: 4px;"
              />
            </a-form>
          </a-tab-pane>

          <!-- Tab: 工具 -->
          <a-tab-pane key="tools" tab="工具">
            <div class="tab-title"><ToolOutlined /> 工具绑定</div>
            <a-select
              v-model:value="formData.tool_bindings"
              mode="multiple"
              style="width: 100%; max-width: 680px;"
              placeholder="搜索并选择要绑定的工具..."
              option-filter-prop="label"
              :max-tag-count="8"
              allow-clear
              :options="toolOptions"
              :filter-option="filterToolOption"
            >
              <template #option="{ label, toolType, desc }">
                <div style="display: flex; align-items: baseline; gap: 8px;">
                  <span style="font-family: monospace; font-weight: 500;">{{ label }}</span>
                  <a-tag :color="toolTypeColor(toolType)" style="font-size: 11px; line-height: 16px; margin-inline-end: 0;">{{ toolType }}</a-tag>
                </div>
                <div style="font-size: 12px; opacity: 0.6; white-space: normal;">{{ desc }}</div>
              </template>
            </a-select>
            <div style="margin-top: 6px; font-size: 12px; opacity: 0.6;">
              已绑定 {{ formData.tool_bindings.length }} / {{ allTools.length }} 个工具，输入关键词可按名称搜索
            </div>
          </a-tab-pane>

          <!-- Tab: 知识库（全局绑定 + 专属） -->
          <a-tab-pane key="knowledge" tab="知识库">
            <div class="tab-title"><FolderOpenOutlined /> 专属知识库</div>
            <div style="font-size: 12px; color: #999; margin-bottom: 10px; line-height: 1.5; max-width: 680px;">
              仅本 Agent 可检索的私有知识库：不出现在全局知识库管理列表，权限跟随本 Agent，
              保存配置后立即生效。可在此一站式上传与管理文档。
            </div>

            <div v-for="kb in agentPrivateKBs" :key="kb.id" class="private-kb-item">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="cursor: pointer;" @click="togglePrivateKBDocs(kb)">
                  <span style="font-size: 13px; font-weight: 500;">{{ kb.name }}</span>
                  <a-tag color="purple" style="margin-left: 6px; font-size: 11px;">专属</a-tag>
                  <span style="font-size: 11px; color: #999; margin-left: 6px;">
                    {{ expandedPrivateKB === kb.id ? '收起' : '展开' }} · {{ kb.document_count || 0 }} 文档
                  </span>
                </div>
                <a-space :size="4">
                  <a-button size="small" type="link" @click="triggerPrivateKBUpload(kb)">上传文档</a-button>
                  <a-popconfirm title="转为公共知识库？转后所有授权用户可见。" @confirm="promotePrivateKB(kb)">
                    <a-button size="small" type="link">转公共</a-button>
                  </a-popconfirm>
                  <a-popconfirm title="删除该专属知识库及其全部文档？" @confirm="removePrivateKB(kb)">
                    <a-button size="small" type="link" danger>删除</a-button>
                  </a-popconfirm>
                </a-space>
              </div>

              <div v-if="expandedPrivateKB === kb.id"
                style="margin-top: 8px; border-top: 1px dashed rgba(128,128,128,0.25); padding-top: 8px;">
                <div v-if="privateKBDocsLoading" style="color: #999; font-size: 12px;">加载中...</div>
                <template v-else>
                  <div v-for="doc in privateKBDocs" :key="doc.id"
                    style="display: flex; align-items: center; justify-content: space-between; padding: 4px 0; font-size: 12px;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                      {{ doc.title }}
                      <span style="color: #999;">· {{ doc.chunk_count }} 分块 · {{ doc.status }}</span>
                    </span>
                    <a-popconfirm title="删除该文档？" @confirm="removePrivateKBDoc(kb, doc)">
                      <a-button size="small" type="link" danger style="font-size: 12px;">删除</a-button>
                    </a-popconfirm>
                  </div>
                  <div v-if="privateKBDocs.length === 0" style="color: #999; font-size: 12px;">
                    暂无文档，点击右上角「上传文档」导入 Excel/CSV
                  </div>
                </template>
              </div>
            </div>

            <div v-if="showPrivateKBForm" class="private-kb-item"
              style="border-color: rgba(79,70,229,0.4);">
              <a-input v-model:value="privateKBForm.name" placeholder="知识库名称，如：售后话术库" size="small" style="margin-bottom: 6px;" />
              <a-input v-model:value="privateKBForm.description" placeholder="描述（可选）" size="small" style="margin-bottom: 8px;" />
              <a-space :size="8">
                <a-button type="primary" size="small" :loading="privateKBCreating" @click="createPrivateKB">创建</a-button>
                <a-button size="small" @click="showPrivateKBForm = false">取消</a-button>
              </a-space>
            </div>

            <a-button v-if="!showPrivateKBForm" size="small" dashed block style="max-width: 680px;"
              @click="openPrivateKBForm">
              + 新建专属知识库
            </a-button>
            <input ref="privateKBFileInput" type="file" accept=".xlsx,.xls,.csv,.xlsm"
              style="display: none;" @change="handlePrivateKBUpload" />

            <a-divider />

            <div class="tab-title"><BookOutlined /> 全局知识库绑定</div>
            <div style="font-size: 12px; color: #999; margin-bottom: 10px;">
              勾选全局知识库后，本 Agent 检索范围为「专属知识库 + 勾选的全局知识库」。
            </div>
            <a-checkbox-group v-model:value="formData.knowledge_bindings" style="width: 100%; max-width: 680px;">
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
                暂无可用知识库
              </div>
            </a-checkbox-group>
          </a-tab-pane>

          <!-- Tab: 聊天界面 -->
          <a-tab-pane key="chatui" tab="聊天界面">
            <div class="tab-title"><MessageOutlined /> 聊天界面配置</div>
            <a-form layout="vertical" style="max-width: 680px;">
              <a-row :gutter="16">
                <a-col :span="20">
                  <a-form-item label="欢迎语">
                    <a-textarea v-model:value="formData.welcome_message" :rows="2" placeholder="如：👋 你好，我是商品客服 Agent" />
                  </a-form-item>
                </a-col>
                <a-col :span="4">
                  <a-form-item label="头像 Emoji">
                    <a-input v-model:value="formData.avatar_emoji" placeholder="🛍️" :maxlength="2"
                      style="text-align: center; font-size: 18px;" />
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
          </a-tab-pane>

          <!-- Tab: 工作流 -->
          <a-tab-pane key="workflow" tab="工作流">
            <div class="tab-title"><ApartmentOutlined /> 工作流绑定</div>
            <div style="font-size: 12px; color: #999; margin-bottom: 10px; line-height: 1.5; max-width: 680px;">
              选择该 Agent 运行时使用的工作流。勾选的第一个为<span style="color: #4f46e5; font-weight: 600;">主工作流</span>，
              未绑定任何工作流时使用全局默认工作流。
              <a-button type="link" size="small" style="padding: 0 0 0 4px;" @click="openWorkflowEditor">
                管理工作流
              </a-button>
            </div>
            <a-checkbox-group v-model:value="formData.workflow_bindings" style="width: 100%; max-width: 680px;">
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
          </a-tab-pane>

          <!-- Tab: IM 渠道 -->
          <a-tab-pane key="im" tab="IM 渠道">
            <div class="tab-title"><CustomerServiceOutlined /> IM 渠道集成</div>
            <div style="font-size: 12px; opacity: 0.6; margin-bottom: 10px; line-height: 1.6; max-width: 680px;">
              绑定飞书/钉钉机器人后，用户在 IM 单聊或群里 @机器人 即可直接与该 Agent 对话，无需登录本系统。
              需先在对应开放平台创建企业自建应用并开启机器人能力。
              如需绑定多 Agent 协同的 AI 员工团队，请到<a href="#/employees" style="text-decoration: underline;">AI 员工</a>页面配置。
            </div>

            <div style="max-width: 680px;">
              <div v-for="ch in agentChannels" :key="ch.id" class="channel-item">
                <div>
                  <div style="font-size: 13px; font-weight: 500;">
                    {{ ch.name }}
                    <a-tag :color="ch.channel_type === 'feishu' ? 'blue' : 'default'" style="font-size: 11px;">{{ ch.channel_type }}</a-tag>
                    <a-tag color="cyan" style="font-size: 11px;">Agent</a-tag>
                    <a-tag :color="ch.status === 'active' ? 'green' : 'default'" style="font-size: 11px;">
                      {{ ch.status === 'active' ? '启用' : '停用' }}
                    </a-tag>
                  </div>
                  <div style="font-size: 11px; opacity: 0.55; margin-top: 2px;">
                    App ID: {{ ch.credentials?.app_id || '—' }}
                  </div>
                </div>
                <a-space :size="4">
                  <a-button size="small" type="link" @click="editChannel(ch)">编辑</a-button>
                  <a-button size="small" @click="testChannel(ch)" :loading="testingChannelId === ch.id">测试</a-button>
                  <a-button size="small" @click="toggleChannel(ch)">{{ ch.status === 'active' ? '停用' : '启用' }}</a-button>
                  <a-popconfirm title="删除该渠道？" @confirm="removeChannel(ch)">
                    <a-button size="small" danger>删除</a-button>
                  </a-popconfirm>
                </a-space>
              </div>
              <div v-if="agentChannels.length === 0" style="color: #999; font-size: 12px; padding: 4px 0 10px;">
                尚未绑定 IM 渠道
              </div>

              <a-button v-if="!channelFormVisible" size="small" type="dashed" block @click="showChannelForm">
                <PlusOutlined /> 绑定 IM 机器人
              </a-button>

              <div v-if="channelFormVisible" class="channel-form">
                <a-form layout="vertical" size="small">
                  <a-form-item label="渠道类型" required>
                    <a-radio-group v-model:value="channelForm.channel_type" button-style="solid" size="small">
                      <a-radio-button value="feishu">飞书</a-radio-button>
                      <a-radio-button value="dingtalk">钉钉</a-radio-button>
                    </a-radio-group>
                  </a-form-item>
                  <a-form-item label="渠道名称" required>
                    <a-input v-model:value="channelForm.name" placeholder="如：飞书客服机器人" />
                  </a-form-item>
                  <a-form-item label="App ID" required>
                    <a-input v-model:value="channelForm.app_id" placeholder="cli_xxx" />
                  </a-form-item>
                  <a-form-item :label="editingChannelId ? 'App Secret（留空则不修改）' : 'App Secret'" :required="!editingChannelId">
                    <a-input-password v-model:value="channelForm.app_secret" placeholder="飞书应用的 App Secret" />
                  </a-form-item>
                  <a-space :size="8">
                    <a-button size="small" @click="channelFormVisible = false">取消</a-button>
                    <a-button size="small" @click="testChannelForm" :loading="testingForm">测试凭证</a-button>
                    <a-button type="primary" size="small" :loading="savingChannel" @click="saveChannel">
                      {{ editingChannelId ? '保存修改' : '绑定' }}
                    </a-button>
                  </a-space>
                </a-form>
              </div>
            </div>
          </a-tab-pane>

          <!-- Tab: 成员授权 -->
          <a-tab-pane key="share" tab="成员授权">
            <div class="tab-title"><ShareAltOutlined /> 成员授权</div>
            <ResourceShareSection
              resource-type="agent"
              :resource-id="agentId"
              resource-label="Agent"
            />
          </a-tab-pane>

          <!-- Tab: 测试对话 -->
          <a-tab-pane key="test" tab="测试对话">
            <div class="tab-title"><MessageOutlined /> 快速测试</div>
            <div class="test-chat">
              <div class="chat-messages" ref="chatMessagesRef">
                <div v-if="testMessages.length === 0" class="chat-empty">
                  <div style="color: #999; font-size: 13px;">
                    向 <strong>{{ agentDetail?.name }}</strong> 发送消息开始测试
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
          </a-tab-pane>

          <!-- Tab: 版本历史 -->
          <a-tab-pane key="versions" tab="版本历史">
            <div class="tab-title"><HistoryOutlined /> 版本历史</div>
            <a-timeline v-if="agentDetail.versions?.length > 0" style="margin-top: 8px; max-width: 680px;">
              <a-timeline-item v-for="ver in agentDetail.versions" :key="ver.id"
                :color="ver.status === 'published' ? 'green' : 'gray'">
                <div style="font-size: 13px;">
                  <span style="font-weight: 600;">v{{ ver.version }}</span>
                  <span style="color: #999; margin-left: 8px;">{{ formatDate(ver.created_at) }}</span>
                </div>
                <div v-if="ver.changelog" style="font-size: 12px; color: #666;">{{ ver.changelog }}</div>
              </a-timeline-item>
            </a-timeline>
            <div v-else style="color: #999; font-size: 13px;">暂无版本记录（首次保存配置后自动生成）</div>
          </a-tab-pane>
        </a-tabs>
      </a-card>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, MessageOutlined, InfoCircleOutlined,
  SettingOutlined, ToolOutlined, BookOutlined, HistoryOutlined,
  PaperClipOutlined, ApartmentOutlined, LinkOutlined, CopyOutlined,
  CustomerServiceOutlined, ShareAltOutlined, FolderOpenOutlined,
  RobotOutlined, SaveOutlined, ArrowLeftOutlined,
} from '@ant-design/icons-vue'
import { agentsApi, toolsApi, knowledgeApi, modelsApi, workflowApi, channelsApi } from '@/api/client'
import { formatTime } from '@/utils/time'
import ResourceShareSection from '@/components/ResourceShareSection.vue'

const route = useRoute()
const router = useRouter()
const agentId = Number(route.params.id)

const activeTab = ref('basic')
const detailLoading = ref(false)
const saving = ref(false)
const loadError = ref('')
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
  allowed_input_types: ['text'] as string[],
  max_file_size_mb: 10,
  max_files_per_message: 5,
  welcome_message: '',
  avatar_emoji: '',
  suggested_questions: [] as Array<{ icon: string; title: string; desc: string; question: string }>,
})

// --- Test chat ---
const testMessages = ref<any[]>([])
const testInput = ref('')
const testLoading = ref(false)
const chatMessagesRef = ref<HTMLElement>()

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
function toolTypeColor(t: string) {
  return ({ internal: 'blue', business: 'green', api: 'purple', database: 'orange', mcp: 'cyan' } as any)[t] || 'default'
}
const toolOptions = computed(() =>
  allTools.value.map((t: any) => ({
    label: t.name,
    value: t.name,
    toolType: t.tool_type,
    desc: t.description
  }))
)
function filterToolOption(input: string, option: any) {
  const kw = input.toLowerCase()
  return option.label?.toLowerCase().includes(kw) || option.desc?.toLowerCase().includes(kw)
}
function modelTypeLabel(t: string) {
  return ({ chat: '对话', reasoning: '推理', vision: '视觉', embedding: 'Embedding', rerank: 'Rerank', speech: '语音' } as any)[t] || t
}
function formatDate(d: string) {
  return formatTime(d, 'minute')
}
function goBack() {
  // 新窗口打开时没有上一页历史，退回列表页
  if (window.history.length > 1) router.back()
  else router.push('/agents')
}

function getChatUrl(token: string) {
  const origin = window.location.origin
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

function openWorkflowEditor() {
  window.open('/#/workflow', '_blank')
}

// ===== 数据加载 =====
async function loadDetail() {
  detailLoading.value = true
  loadError.value = ''
  try {
    if (modelOptions.value.length === 0) await fetchModelOptions()
    if (allWorkflows.value.length === 0) await fetchWorkflows()

    const res = await agentsApi.fullDetail(agentId)
    agentDetail.value = res.data
    const d = res.data
    const config = d.config || {}

    formData.name = d.name || ''
    formData.description = d.description || ''
    formData.status = d.status || 'draft'
    formData.is_active = d.is_active ?? true
    formData.system_prompt = config.system_prompt || ''
    formData.model_config_id = config.model_config_id ?? null
    if (!formData.model_config_id && config.model) {
      const matched = modelOptions.value.find(o => o.model_id === config.model)
      if (matched) formData.model_config_id = matched.id
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
    formData.workflow_bindings = (d.workflow_bindings || []).map((w: any) => w.workflow_id)

    loadPrivateKBs(agentId)
    loadChannels(agentId)
  } catch (err: any) {
    const status = err.response?.status
    loadError.value = status === 403 ? '无权访问该 Agent'
      : status === 404 ? 'Agent 不存在或已被删除'
      : '加载 Agent 详情失败'
  } finally {
    detailLoading.value = false
  }
}

async function fetchModelOptions() {
  try {
    const res = await modelsApi.selectable()
    modelOptions.value = res.data || []
  } catch { modelOptions.value = [] }
}
async function fetchWorkflows() {
  try {
    const res = await workflowApi.list()
    allWorkflows.value = res.data || []
  } catch { allWorkflows.value = [] }
}
async function fetchTools() {
  try {
    const res = await toolsApi.list()
    allTools.value = res.data || []
  } catch { allTools.value = [] }
}
async function fetchKnowledgeBases() {
  try {
    const res = await knowledgeApi.list()
    allKnowledgeBases.value = res.data || []
  } catch { allKnowledgeBases.value = [] }
}

// ===== 保存 =====
async function saveConfig() {
  saving.value = true
  try {
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
    await agentsApi.bindTools(agentId, formData.tool_bindings)
    await agentsApi.bindKnowledge(agentId, formData.knowledge_bindings)
    await agentsApi.bindWorkflow(agentId, formData.workflow_bindings)
    message.success('Agent 配置已保存')
    await loadDetail()
  } catch (err: any) {
    message.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

// ===== 测试对话 =====
async function sendTestMessage() {
  if (!testInput.value.trim() || !agentDetail.value) return
  const userMsg = testInput.value.trim()
  testInput.value = ''
  testMessages.value.push({ id: Date.now(), role: 'user', content: userMsg })
  testLoading.value = true
  await nextTick()
  if (chatMessagesRef.value) chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight

  try {
    const res = await fetch('/api/v1/conversations/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: JSON.stringify({ user_id: 1, agent_id: agentId, message: userMsg }),
    })
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}))
      const detail = errorData.detail || ''
      let friendlyMsg = detail || `请求失败 (HTTP ${res.status})`
      if (res.status === 404) friendlyMsg = 'Agent 不存在或已被删除'
      else if (res.status === 403) friendlyMsg = '该 Agent 未启用，请先在基础信息中启用'
      else if (res.status === 422) friendlyMsg = '请求参数有误，请刷新页面后重试'
      else if (res.status >= 500) friendlyMsg = 'AI 服务暂时不可用，请稍后重试'
      testMessages.value.push({ id: Date.now() + 1, role: 'agent', content: friendlyMsg, meta: { error: true } })
      return
    }
    const data = await res.json()
    testMessages.value.push({
      id: Date.now() + 1,
      role: 'agent',
      content: data.reply || '（Agent 未返回内容）',
      meta: { intent: data.intent, confidence: data.confidence, need_human: data.need_human },
    })
  } catch (err: any) {
    testMessages.value.push({
      id: Date.now() + 1, role: 'agent',
      content: '网络请求失败，请检查服务是否正常运行: ' + err.message,
      meta: { error: true },
    })
  } finally {
    testLoading.value = false
    await nextTick()
    if (chatMessagesRef.value) chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }
}

// ===== 专属知识库 =====
const agentPrivateKBs = ref<any[]>([])
const expandedPrivateKB = ref<number | null>(null)
const privateKBDocs = ref<any[]>([])
const privateKBDocsLoading = ref(false)
const showPrivateKBForm = ref(false)
const privateKBCreating = ref(false)
const privateKBForm = reactive({ name: '', description: '' })
const privateKBFileInput = ref<HTMLInputElement | null>(null)
const privateKBUploadTarget = ref<any>(null)

async function loadPrivateKBs(aid: number) {
  try {
    const res = await agentsApi.listPrivateKBs(aid)
    agentPrivateKBs.value = res.data || []
  } catch (err: any) {
    agentPrivateKBs.value = []
    if (err.response?.status !== 403 && err.response?.status !== 404) {
      message.error('加载专属知识库失败: ' + (err.response?.data?.detail || err.message))
    }
  }
}
function openPrivateKBForm() {
  privateKBForm.name = ''
  privateKBForm.description = ''
  showPrivateKBForm.value = true
}
async function createPrivateKB() {
  if (!privateKBForm.name.trim()) {
    message.warning('请填写知识库名称')
    return
  }
  privateKBCreating.value = true
  try {
    await agentsApi.createPrivateKB(agentId, {
      name: privateKBForm.name.trim(),
      description: privateKBForm.description.trim() || undefined,
    })
    message.success('专属知识库已创建并绑定到本 Agent')
    showPrivateKBForm.value = false
    await loadPrivateKBs(agentId)
  } catch (err: any) {
    message.error('创建失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    privateKBCreating.value = false
  }
}
async function removePrivateKB(kb: any) {
  try {
    await agentsApi.deletePrivateKB(agentId, kb.id)
    message.success('专属知识库已删除')
    if (expandedPrivateKB.value === kb.id) expandedPrivateKB.value = null
    await loadPrivateKBs(agentId)
  } catch (err: any) {
    message.error('删除失败: ' + (err.response?.data?.detail || err.message))
  }
}
async function promotePrivateKB(kb: any) {
  try {
    await agentsApi.promotePrivateKB(agentId, kb.id)
    message.success('已转为公共知识库，可在知识库管理中查看')
    await loadPrivateKBs(agentId)
  } catch (err: any) {
    message.error('转公共失败: ' + (err.response?.data?.detail || err.message))
  }
}
async function togglePrivateKBDocs(kb: any) {
  if (expandedPrivateKB.value === kb.id) {
    expandedPrivateKB.value = null
    return
  }
  expandedPrivateKB.value = kb.id
  privateKBDocsLoading.value = true
  try {
    const res = await agentsApi.privateKBDocuments(agentId, kb.id)
    privateKBDocs.value = res.data || []
  } catch (err: any) {
    privateKBDocs.value = []
    message.error('加载文档失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    privateKBDocsLoading.value = false
  }
}
function triggerPrivateKBUpload(kb: any) {
  privateKBUploadTarget.value = kb
  privateKBFileInput.value?.click()
}
async function handlePrivateKBUpload(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  const kb = privateKBUploadTarget.value
  input.value = ''
  if (!file || !kb) return
  const hide = message.loading(`正在导入 ${file.name} 并生成向量索引...`, 0)
  try {
    const res = await agentsApi.importPrivateKBDoc(agentId, kb.id, file)
    const d = res.data || {}
    message.success(`导入完成：${d.rows ?? 0} 行 / ${d.chunks ?? 0} 分块`)
    if (expandedPrivateKB.value === kb.id) await togglePrivateKBDocs(kb)
    await loadPrivateKBs(agentId)
  } catch (err: any) {
    message.error('导入失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    hide()
  }
}
async function removePrivateKBDoc(kb: any, doc: any) {
  try {
    await agentsApi.deletePrivateKBDoc(agentId, kb.id, doc.id)
    message.success('文档已删除')
    await togglePrivateKBDocs(kb)
    await loadPrivateKBs(agentId)
  } catch (err: any) {
    message.error('删除失败: ' + (err.response?.data?.detail || err.message))
  }
}

// ===== IM 渠道 =====
const agentChannels = ref<any[]>([])
const channelFormVisible = ref(false)
const editingChannelId = ref<number | null>(null)
const savingChannel = ref(false)
const testingChannelId = ref<number | null>(null)
const testingForm = ref(false)
const channelForm = reactive({ name: '', app_id: '', app_secret: '', channel_type: 'feishu' })

async function loadChannels(aid: number) {
  try {
    const res = await channelsApi.list({ agent_id: aid })
    agentChannels.value = res.data.items || []
  } catch {
    agentChannels.value = []
  }
}
function showChannelForm() {
  editingChannelId.value = null
  channelForm.name = ''
  channelForm.app_id = ''
  channelForm.app_secret = ''
  channelForm.channel_type = 'feishu'
  channelFormVisible.value = true
}
function editChannel(ch: any) {
  editingChannelId.value = ch.id
  channelForm.name = ch.name
  channelForm.app_id = ch.credentials?.app_id || ''
  channelForm.app_secret = ''
  channelForm.channel_type = ch.channel_type || 'feishu'
  channelFormVisible.value = true
}
function validateChannelForm(): boolean {
  if (!channelForm.name.trim()) { message.error('请填写渠道名称'); return false }
  if (!channelForm.app_id.trim()) { message.error('请填写 App ID'); return false }
  if (!editingChannelId.value && !channelForm.app_secret.trim()) {
    message.error('请填写 App Secret'); return false
  }
  return true
}
function buildChannelPayload(): Record<string, any> {
  return {
    channel_type: channelForm.channel_type,
    name: channelForm.name.trim(),
    target_type: 'agent',
    agent_id: agentId,
    credentials: {
      app_id: channelForm.app_id.trim(),
      app_secret: channelForm.app_secret.trim()
    }
  }
}
async function saveChannel() {
  if (!validateChannelForm()) return
  savingChannel.value = true
  try {
    if (editingChannelId.value) {
      await channelsApi.update(editingChannelId.value, buildChannelPayload())
      message.success('渠道已更新，消息泵将在 1 分钟内重连')
    } else {
      await channelsApi.create(buildChannelPayload())
      message.success('渠道已绑定，消息泵将在 1 分钟内自动连接')
    }
    channelFormVisible.value = false
    editingChannelId.value = null
    await loadChannels(agentId)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '保存失败')
  } finally { savingChannel.value = false }
}
async function testChannel(ch: any) {
  testingChannelId.value = ch.id
  try {
    const res = await channelsApi.test(ch.id)
    if (res.data.success) {
      message.success('凭证有效，连接正常')
      await loadChannels(agentId)
    } else {
      message.error(res.data.detail || '连接失败')
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '测试失败')
  } finally { testingChannelId.value = null }
}
async function testChannelForm() {
  // 未保存的表单：先临时创建（停用状态）再测试，失败即删除
  if (!validateChannelForm()) return
  testingForm.value = true
  let tempId: number | null = null
  try {
    const payload = buildChannelPayload()
    payload.status = 'disabled'
    const created = await channelsApi.create(payload)
    tempId = created.data.id
    const res = await channelsApi.test(created.data.id as number)
    if (res.data.success) {
      message.success('凭证有效')
    } else {
      message.error(res.data.detail || '凭证校验失败')
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '测试失败')
  } finally {
    if (tempId) {
      try { await channelsApi.remove(tempId) } catch {}
    }
    testingForm.value = false
  }
}

async function toggleChannel(ch: any) {
  try {
    await channelsApi.update(ch.id, { status: ch.status === 'active' ? 'disabled' : 'active' })
    await loadChannels(agentId)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '操作失败')
  }
}
async function removeChannel(ch: any) {
  try {
    await channelsApi.remove(ch.id)
    message.success('渠道已删除')
    await loadChannels(agentId)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '删除失败')
  }
}

onMounted(async () => {
  await Promise.all([fetchTools(), fetchKnowledgeBases()])
  await loadDetail()
})
</script>

<style scoped>
.agent-config-page {
  padding: 0 0 24px;
}
.header-card {
  margin-bottom: 16px;
}
.header-row {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 12px;
}
.header-left {
  display: flex; align-items: center;
}
.header-title {
  font-size: 16px; font-weight: 600; display: flex; align-items: center;
}
.header-sub {
  font-size: 12px; color: #999; margin-top: 2px;
}
.load-error {
  background: #fff; border-radius: 12px; padding: 24px;
}
.tabs-card {
  border-radius: 12px;
}
.config-tabs :deep(.ant-tabs-content-holder) {
  padding-left: 8px;
}
.tab-title {
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
  display: flex; align-items: center; gap: 6px;
}
.binding-item {
  padding: 8px 10px; border-radius: 8px; margin-bottom: 4px;
  border: 1px solid transparent;
}
.binding-item:hover {
  background: rgba(79, 70, 229, 0.04);
  border-color: rgba(79, 70, 229, 0.15);
}
.binding-name {
  font-size: 13px; font-weight: 500;
}
.binding-desc {
  font-size: 12px; color: #999;
}
.private-kb-item {
  border: 1px solid rgba(128,128,128,0.25); border-radius: 8px;
  padding: 10px 12px; margin-bottom: 8px; max-width: 680px;
}
.channel-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border: 1px solid rgba(128,128,128,0.2);
  border-radius: 8px; margin-bottom: 8px; max-width: 680px;
}
.channel-form {
  border: 1px dashed rgba(128,128,128,0.35); border-radius: 8px;
  padding: 12px; margin-top: 4px; max-width: 680px;
}
.suggestion-edit-item {
  padding: 4px 0;
}
.test-chat {
  max-width: 680px;
  border: 1px solid rgba(128,128,128,0.2); border-radius: 12px;
  overflow: hidden;
}
.chat-messages {
  height: 420px; overflow-y: auto; padding: 16px;
}
.chat-empty {
  display: flex; justify-content: center; padding-top: 60px;
}
.chat-msg {
  display: flex; margin-bottom: 12px;
}
.chat-msg.user { justify-content: flex-end; }
.chat-msg.agent { justify-content: flex-start; }
.chat-bubble {
  max-width: 80%; padding: 8px 12px; border-radius: 12px;
  background: rgba(79, 70, 229, 0.06);
}
.chat-msg.user .chat-bubble {
  background: #4f46e5; color: #fff;
}
.chat-bubble.chat-error {
  background: rgba(255, 77, 79, 0.08);
}
.chat-role {
  font-size: 11px; opacity: 0.55; margin-bottom: 2px;
}
.chat-text {
  font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
}
.chat-meta {
  margin-top: 4px; display: flex; gap: 4px;
}
.chat-input-area {
  padding: 12px; border-top: 1px solid rgba(128,128,128,0.15);
}
</style>
