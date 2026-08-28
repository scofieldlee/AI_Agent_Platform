# 时区修正说明 — 全系统统一北京时间

日期：2026-08-29
影响范围：后端全部接口 + 管理后台全部页面 + 对外聊天页 + 云端生产环境

---

## 一、问题定位

用户反馈「处理任务列表的时间不是北京时间」。

排查结果：

| 层 | 状态 |
| --- | --- |
| 数据库（`timestamptz`） | ✅ 正确。存的是正确的瞬时值 |
| 接口输出 | ❌ `2026-08-28T18:38:36.031102Z`（UTC） |
| 前端显示 | ❌ `slice(0,19)` 直接截断，显示为 `2026-08-28 18:38:36` |

真实时间应为 `2026-08-29 02:38:36`（北京时间），界面慢了 8 小时。

**根因**：asyncpg 读回的 `datetime` 一律带 UTC 时区，Pydantic 序列化后带 `Z` 后缀；
前端多处直接截断字符串，没有做时区换算。

> 关键结论：**库里的数据是对的**，不需要迁移历史数据，只需要修「写入口径」和「输出换算」。

---

## 二、解决方案

### 1. 写入端 — 统一时间工具

新增 `app/core/timeutils.py`：

| 函数 | 用途 |
| --- | --- |
| `now()` | 当前时间（aware，带系统时区偏移），**写入数据库统一用这个** |
| `now_naive()` | 当前时间（naive，系统时区墙钟值） |
| `to_local(v)` / `to_local_naive(v)` | 任意时间值 → 系统时区 |
| `local_iso(v)` | 输出为不带偏移的本地时间串，用于手工拼 dict 的接口 |
| `from_timestamp(ts)` | Unix 时间戳 → 系统时区 aware datetime |
| `ensure_process_timezone()` | 对齐进程 TZ（`time.localtime` / 日志时间戳） |

配置项 `app_timezone`（`app/core/config.py`），默认 `Asia/Shanghai`，填 `auto` 则跟随主机系统时区。
时间源始终是**主机系统时钟**（`datetime.now()`），只有时区偏移按配置换算。

替换了 12 个文件中的 `datetime.now(timezone.utc)` / `datetime.utcnow()`。

### 2. 输出端 — 全局响应中间件

新增 `app/core/timezone_middleware.py` 的 `LocalTimezoneMiddleware`（纯 ASGI），
在 HTTP 出口做一次统一改写，同时覆盖「有 response_model 的接口」和「直接返回 dict 的接口」。

改写规则（安全边界）：

- 只匹配**完整的 JSON 字符串值**，且内容是 ISO-8601 时间、并带 **UTC 标识**（`Z` / `+00:00` / `+0000`）
- 因为正则要求从 `"` 开始到 `"` 结束，**不会命中嵌入在长文本里的时间片段**
- 已是本地时间（`+08:00`）或其它偏移的值**不会被二次换算**
- 纯日期（`2026-08-29`）不含 `T`，不受影响
- 流式响应（SSE、文件下载，无 content-length）直接放行，不做缓冲

输出格式：`2026-08-29T02:38:36.031102`（**不带时区偏移的本地墙钟时间**）。
这样前端无论是字符串截断、`dayjs()` 还是 `toLocaleString()`，在任何浏览器时区下都显示北京时间。

### 3. 手工 isoformat 输出点

以下位置绕过了 Pydantic 序列化，改为 `local_iso()`：

`knowledge.py` / `workflow.py` / `auth.py` / `human_center/service.py` /
`monitoring/collector.py` / `order_query|refund_query|inventory_query|logistics_query` /
`local_storage.py` / `obsidian_loader.py` / `memory/service.py`

### 4. 前端

- 新增 `admin/src/utils/time.ts`：`formatTime(v, 'date'|'minute'|'second'|'short')` + `toBeijingTime()`
- `ProcessingTasks.vue`、`AssetDetail.vue`：去掉字符串截断
- `Memories / Knowledge / Agents / Users / Conversations / Tasks / Analytics / Dashboard / Monitoring / WorkflowEditor` 统一改用
- 清理了因此不再使用的 `dayjs` 导入
- `static/chat.html`：新增 `fmtBeijing()`，替换 2 处 `new Date().toLocaleString()`

### 5. 排查脚本

```bash
python scripts/check_timezone.py   # 抽查 13 个接口的时间是否仍为 UTC
```

---

## 三、验证结果

### 本地

抽查 13 个接口，**0 处**仍为 UTC：

| 模块 | 时间字段 | 值 |
| --- | --- | --- |
| 多模态-处理任务 | `started_at` | `2026-08-29T02:38:36.061055` |
| 多模态-知识库 | `created_at` | `2026-08-26T20:17:34.740160` |
| 对话-会话列表 | `created_at` | `2026-08-26T21:11:25.038087` |
| 分析-Trace列表 | `started_at` | `2026-08-26T21:11:25.070069` |
| 人工-任务列表 | `created_at` | `2026-08-26T01:38:54.402742` |
| AI员工-任务 | `started_at` | `2026-08-20T01:59:25.801023` |
| 记忆列表 | `last_accessed_at` | `2026-08-26T13:11:28.058264` |
| 用户列表 | `last_login` | `2026-08-29T03:04:41.120195` |

**端到端写入验证**：新建知识库记录返回 `created_at = 2026-08-29T03:11:43.357118`，
与主机时间 `2026-08-29 03:11:43 CST` 完全一致。

### 云端（43.155.144.168）

| 来源 | 值 |
| --- | --- |
| 接口返回 | `2026-08-27T12:34:55.341599` |
| psql 直查 | `2026-08-27 12:34:55.341599+08` |

两者完全一致。服务器系统时区本就是 `Asia/Shanghai`，无需改动。

前端 `npm run build` 通过，TypeScript 零错误。

---

## 四、改动文件清单

**新增（4）**
- `app/core/timeutils.py`
- `app/core/timezone_middleware.py`
- `admin/src/utils/time.ts`
- `scripts/check_timezone.py`

**修改（22）**
- `app/core/config.py`（+`app_timezone`）
- `app/main.py`（注册中间件 + 进程时区对齐）
- `app/multimodal/services/task_queue_service.py`
- `app/multimodal/repositories/asset_repo.py`
- `app/multimodal/adapters/storage/local_storage.py`
- `app/analytics/tracer.py`
- `app/monitoring/collector.py`
- `app/models/human_task.py`
- `app/human_center/service.py`
- `app/employee/runtime/executor.py`
- `app/employee/runtime/supervisor.py`
- `app/employee/runtime/dag_scheduler.py`
- `app/repositories/employee_repo.py`
- `app/memory/service.py`
- `app/auth/service.py`
- `app/api/v1/endpoints/knowledge.py`
- `app/api/v1/endpoints/workflow.py`
- `app/api/v1/endpoints/auth.py`
- `app/knowledge/loaders/obsidian_loader.py`
- `app/tools/adapters/{order_query,refund_query,inventory_query,logistics_query}.py`
- `admin/src/views/` 下 12 个页面
- `static/chat.html`
- `README.md`（新增「🕐 时区约定」章节）

---

## 五、注意事项

1. **历史数据无需迁移** — 库里存的是正确瞬时值，只是之前展示时少了 8 小时换算。
2. **新增代码的时间戳**必须用 `app.core.timeutils.now()`，不要再用 `datetime.now(timezone.utc)`。
3. **新增接口若手工拼 dict 返回时间**，用 `local_iso()`；走 Pydantic 的由中间件自动处理。
4. 若部署到非北京时间服务器，务必设 `APP_TIMEZONE=Asia/Shanghai` 或把主机时区设为 `Asia/Shanghai`。
5. 本次改动**未执行任何 git 命令**，代码未提交，由用户自行 commit。
