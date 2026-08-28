# 处理任务删除 + 踢出队列功能说明

日期：2026-08-29

---

## 需求

用户反馈多模态知识库「处理任务」列表中有多个任务一直处于「排队中」，
需要支持删除这些任务，并且把它们从 Redis 任务队列中踢出去。

---

## 实现

### 后端

| 文件 | 改动 |
| --- | --- |
| `app/multimodal/repositories/processing_repo.py` | 新增 `delete_task(db, task_id)` |
| `app/multimodal/services/task_queue_service.py` | 新增 `remove_from_queue(task_id)` 对 `mm:task:queue` 执行 `LREM`；新增 `delete_task(db, task_id)` 先踢队列再删库 |
| `app/multimodal/schemas/processing.py` | 新增 `BatchDeleteTasksRequest` / `BatchDeleteTasksResponse` / `TaskDeleteResponse` |
| `app/multimodal/schemas/__init__.py` | 导出新 schema |
| `app/multimodal/api/endpoints.py` | 新增 `DELETE /multimodal/tasks/{task_id}` 单删 + `DELETE /multimodal/tasks` 批量删除 |

删除规则：

- `pending`：先从 Redis 队列 `LREM` 踢出，再删除数据库记录
- `failed / success`：直接删除数据库记录
- `processing`：返回 `409`，禁止删除，提示等任务完成或失败后再试

### 前端

| 文件 | 改动 |
| --- | --- |
| `admin/src/api/client.ts` | 新增 `multimodalApi.deleteTask(id)` 和 `multimodalApi.batchDeleteTasks(ids)` |
| `admin/src/views/multimodal/ProcessingTasks.vue` | 表格增加行选择、每行「删除」按钮、顶部批量删除提示条、确认弹窗 |

UI 细节：

- 执行中（processing）的任务删除按钮禁用，避免误删
- 单行删除使用 `a-popconfirm`
- 批量删除使用 `a-modal.confirm`，提示会从队列踢出 pending 任务
- 删除成功后自动刷新列表并显示 `message.success`

---

## 接口示例

### 单删

```bash
curl -X DELETE http://localhost:8000/api/v1/multimodal/tasks/45 \
  -H "Authorization: Bearer <token>"
```

响应：

```json
{
  "task_id": 45,
  "deleted": true,
  "removed_from_queue": 1,
  "error": null
}
```

### 批量删除

```bash
curl -X DELETE http://localhost:8000/api/v1/multimodal/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"task_ids": [45, 46, 47]}'
```

响应：

```json
{
  "total": 3,
  "deleted": 3,
  "removed_from_queue": 2,
  "results": [
    { "task_id": 45, "deleted": true, "removed_from_queue": 1, "error": null },
    { "task_id": 46, "deleted": true, "removed_from_queue": 0, "error": null },
    { "task_id": 47, "deleted": true, "removed_from_queue": 1, "error": null }
  ]
}
```

---

## 验证

- 本地：单删 pending 任务 #45、批量删 #54/#56、单删失败任务 #46 均成功
- 本地 / 云端 `npm run build` 均通过，TypeScript 零错误
- 云端 43.155.144.168 已同步并重启 `ai-agent-platform` + `ai-agent-mmworker`，健康检查 OK

---

## 注意事项

- `removed_from_queue` 为 0 不代表失败，只是该任务当时已不在队列里（例如已被 Worker 消费走）
- 如果 Worker 在删除前已经取走任务并标记为 `processing`，删除请求会被拒绝，任务会正常执行到结束
- 本次改动**未执行任何 git 命令**，代码未提交，由用户自行 commit
