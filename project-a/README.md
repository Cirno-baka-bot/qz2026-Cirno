# 工程题 A：文章管理系统（数据层）

> **本题为扩展题内容，二选一完成即可。** 选做一道，不强制。
> 请在功能分支上开发，完成后通过 Pull Request 合并回 main。

## 项目背景

实现一个文章管理系统的**数据层**：文章模型、附件管理、操作审计、并发安全。核心挑战：合理的模型设计、Django 信号驱动的审计日志、文件附件管理、并发安全的计数器。

## 功能需求

### 必须实现

1. **数据模型**
   - `Article`：标题、正文、作者（外键 → 用户，`CASCADE`）、状态（`draft` / `published` / `archived`）、浏览量（默认 0）、`created_at` / `updated_at`（自动记录）
   - `Attachment`：文件名、文件（`FileField`）、关联文章（外键 → `Article`，`CASCADE`，`related_name="attachments"`）、上传时间
   - `AuditLog`：操作类型（`create` / `update` / `publish` / `archive` / `delete`）、关联文章（外键 → `Article`，`SET_NULL`，`null=True`）、操作人（外键 → 用户，`SET_NULL`，`null=True`）、时间戳、变更摘要（`JSONField`）
   - 合理设置 `__str__`、`Meta` 排序、`verbose_name`

2. **附件管理**
   - 登录用户可为自己的文章上传附件（`FileField`，存到 `MEDIA_ROOT/attachments/`）
   - 文章详情页展示附件列表
   - 作者可删除自己的附件
   - `settings.py` 配置 `MEDIA_URL` / `MEDIA_ROOT`，开发服务器能访问静态文件

3. **操作审计（信号驱动）**
   - 每次文章创建、状态变更、删除，自动写入 `AuditLog`
   - **必须用 Django 信号**（`post_save` / `pre_delete`）实现，禁止在视图里手动 `AuditLog.objects.create`
   - 变更摘要用 `JSONField` 记录变更前后字段差异，如 `{"status": {"old": "draft", "new": "published"}}`
   - 文章详情页底部展示该文章的审计日志（按时间倒序）

4. **并发安全浏览量**
   - 文章详情页每次访问浏览量 +1
   - **必须用 `F("views") + 1` 原子更新**
   - 写注释说明：为什么 `article.views += 1; article.save()` 在并发下会丢更新

### 加分项

1. **封面图缩略图**：上传时自动生成 200px 宽缩略图（用 `Pillow`，存到 `MEDIA_ROOT/thumbnails/`）
2. **文章统计视图**：`/stats/` 展示总文章数、总浏览量、各状态文章数、最近 10 条审计日志
3. **软删除**：文章删除时不真删，设 `is_deleted=True`，审计日志保留；列表页过滤已删除文章
4. **附件下载计数**：每次下载附件 +1（`F("downloads") + 1`），展示在附件列表

## 技术要求

- Python 3 + Django
- 必须包含：
  - `README.md`：项目说明、功能列表、依赖安装、运行方式
  - `requirements.txt`（含 `Pillow`）
  - 可运行的 `manage.py`
- 密码存储必须用 Django 内置哈希（`set_password`），禁止明文
- 审计日志必须用信号实现，禁止在视图里手动 `create`
- 代码遵循 PEP 8

## 评分标准

| 维度 | 权重 | 说明 |
| --- | --- | --- |
| 必须功能完成度 | 40% | 模型 + 附件 + 信号审计 + 并发浏览量 |
| 代码质量 | 25% | 模型设计、信号设计、无冗余、有注释 |
| 加分项 | 20% | 实现了多少可选功能 |
| 工程规范 | 15% | git 提交历史、分支管理、PR 流程、README 完整性 |

## 提交要求

- 项目代码放在本目录 `project-a/` 下
- 在功能分支上开发，完成后通过 Pull Request 合并回 main
- 保持过程性提交，提交信息应说明改动内容
- 截止前（10月7日 23:59）仓库状态为准
