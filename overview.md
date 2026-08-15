# Agent 绑定工作流 — 实现总结

## 目标
完成「Agent 管理支持配置 Workflow 流」：后台可在每个 Agent 的配置中绑定一个或多个工作流，运行时优先按 Agent 绑定加载对应工作流执行。

## 已完成功能

### 1. 后端：Agent 工作流绑定 API
- **新增端点**
  - `PUT /api/v1/agents/{id}/workflow` — 设置/替换 Agent 的工作流绑定（第一个绑定自动设为主工作流 `is_primary=true`）。
  - `GET /api/v1/agents/{id}/detail` 响应增加 `workflow_bindings` 字段，包含 `workflow_id`, `name`, `code`, `status`, `is_primary`, `node_count`。
- **列表展示**
  - `GET /api/v1/agents` 列表接口返回每个 Agent 的主工作流摘要（`workflow` 字段），便于表格一眼识别绑定关系。
- **删除保护**
  - 已绑定的工作流在删除时会返回 `400` 错误并提示被绑定的 Agent 数量。

### 2. 运行时：按 Agent 解析工作流
- `app/runtime/executor.py` 的工作流加载逻辑重构：
  - 优先读取 `AgentWorkflowBinding`（`is_primary` 优先），命中则 `source=agent binding`。
  - 无绑定则回退到全局默认工作流（`source=global default`）。
  - 仍无则回退到硬编码 legacy MVP 图。
  - 缓存 key 改为按 `agent:{id}` 与 `default` 隔离，Agent 绑定变更时立即失效。

### 3. 前端：Agent 配置抽屉新增「工作流绑定」
- `admin/src/api/client.ts` 新增 `agentsApi.bindWorkflow(id, workflowIds)`。
- `admin/src/views/Agents.vue`：
  - Agent 表格新增「工作流」列，展示主工作流名称。
  - 配置抽屉新增「工作流绑定」区域，列出所有工作流（状态 tag、节点数、编码/描述），支持多选。
  - 保存时同步调用绑定接口。
  - 提供「管理工作流」入口，一键跳转到工作流编排页面。

### 4. 顺手修复的遗留问题
- `admin/src/components/WorkflowNode.vue` 存在模板编译 bug（`v-if` 与 `<template v-else>` 之间夹了文本节点，导致 `vite build` 崩溃）。修复后生产构建通过。

## 验证结果
- ✅ Python 语法检查通过
- ✅ 绑定 API：`PUT /agents/2/workflow` 成功，`is_primary=true`
- ✅ 列表字段：商品客服 Agent 显示「商品客服 Agent 工作流」
- ✅ 删除保护：绑定的工作流无法删除
- ✅ 运行时：日志确认 `source=agent binding (id=2)`
- ✅ 对话测试：Agent #2 正常返回商品推荐结果
- ✅ 前端 TypeScript 零错误
- ✅ 前端生产构建成功（13.12s）

## 关键文件变更
- `app/schemas/agent.py`
- `app/repositories/agent_repo.py`
- `app/repositories/workflow_repo.py`
- `app/api/v1/endpoints/agents.py`
- `app/runtime/executor.py`
- `admin/src/api/client.ts`
- `admin/src/views/Agents.vue`
- `admin/src/components/WorkflowNode.vue`（修复构建 bug）
