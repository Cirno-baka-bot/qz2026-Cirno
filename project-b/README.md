# 工程题 B：内容管理系统（接口层）

> **本题为扩展题内容，二选一完成即可。** 选做一道，不强制。
> 请在功能分支上开发，完成后通过 Pull Request 合并回 main。

## 项目背景

实现一个内容管理系统的**接口层**：文章状态工作流、REST API、Django Admin 定制、认证与权限。核心挑战：多状态状态机、API 设计与认证、Admin 深度定制、权限校验。

## 功能需求

### 必须实现

1. **数据模型**
   - `Article`：标题、正文、作者（外键 → 用户，`CASCADE`）、状态（`draft` / `in_review` / `published` / `archived`）、浏览量（默认 0）、`created_at` / `updated_at`（自动记录）
   - 合理设置 `__str__`、`Meta` 排序、`verbose_name`

2. **文章工作流（状态机）**
   - 状态转换：`draft` → `in_review` → `published` → `archived`
   - 只有作者本人能执行状态转换（非作者返回 403）
   - 非法转换（如 `draft` → `published` 跳过审核、`archived` → `draft` 回退）返回 400
   - 文章列表页：支持按状态筛选 + 按作者筛选 + 按标题搜索（`icontains`）+ 分页（每页 10 条）

3. **REST API**
   - `GET /api/articles/`：返回文章列表（JSON），支持 `?status=` 和 `?page=` 参数
   - `GET /api/articles/<id>/`：返回单篇文章详情
   - `POST /api/articles/<id>/transition/`：执行状态转换，body 含 `{"to": "in_review"}`
   - API 返回标准 JSON 格式：成功 `{"data": ..., "message": "..."}`，失败 `{"error": "..."}` + 对应 HTTP 状态码
   - API 端点需登录认证（session 或 token 均可），未认证返回 401
   - 权限：只有作者能调用 `transition`，非作者返回 403

4. **Django Admin 定制**
   - `Article` 在 Admin 中可增删改查
   - 自定义 `list_display`（标题、作者、状态、浏览量、创建时间）
   - 自定义 `list_filter`（状态、作者）
   - 自定义 `search_fields`（标题）
   - 自定义 `actions`：批量发布（`draft`/`in_review` → `published`）、批量归档
   - 只读权限：非作者用户访问 Admin 时只能看，不能改（用 `has_change_permission` 控制）

5. **认证与权限**
   - 用户注册（用户名 + 密码，`set_password` 哈希存储）
   - 登录 / 登出（session）
   - 未登录用户只能浏览已发布文章的 API
   - 所有写操作（状态转换）必须校验登录 + 作者权限

### 加分项

1. **API 版本化**：`/api/v1/articles/` 和 `/api/v2/articles/`，v2 返回额外字段（如 `word_count`、`reading_time`）
2. **全文搜索**：`GET /api/articles/?q=keyword` 支持标题 + 正文搜索
3. **操作限制**：同一用户每分钟最多 5 次状态转换（用内存计数或数据库计数均可，写清实现思路）
4. **WebSocket 实时通知**：文章状态变更时，通过 WebSocket 通知该作者的其他在线会话（用 `channels` 或轮询模拟均可，写清思路）
5. **API 文档**：用 `drf-spectacular` 或手写 OpenAPI spec，生成 `/api/docs/` 页面

## 技术要求

- Python 3 + Django（可用 DRF，也可纯 Django 视图 + JSON 响应）
- 必须包含：
  - `README.md`：项目说明、功能列表、依赖安装、运行方式、API 端点文档
  - `requirements.txt`
  - 可运行的 `manage.py`
- 密码存储必须用 Django 内置哈希，禁止明文
- 所有写操作必须校验登录 + 权限
- 代码遵循 PEP 8

## 评分标准

| 维度 | 权重 | 说明 |
| --- | --- | --- |
| 必须功能完成度 | 40% | 模型 + 工作流 + API + Admin + 认证 |
| 代码质量 | 25% | 状态机设计、API 结构、权限逻辑、无冗余、有注释 |
| 加分项 | 20% | 实现了多少可选功能 |
| 工程规范 | 15% | git 提交历史、分支管理、PR 流程、README 完整性 |

## 提交要求

- 项目代码放在本目录 `project-b/` 下
- 在功能分支上开发，完成后通过 Pull Request 合并回 main
- 保持过程性提交，提交信息应说明改动内容
- 截止前（10月7日 23:59）仓库状态为准
