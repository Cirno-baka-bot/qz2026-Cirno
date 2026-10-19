---
type: test
scope: workspace
audience: developer
summary: 工程题 A 测试从 43 项精简为 16 项，聚焦作业核心要求
breaking: false
demo_ready: false
tests:
  - "cd project-a && .venv/bin/python manage.py test articles --noinput"
  - "cd project-a && .venv/bin/python scripts/verify_concurrency.py"
  - "cd project-a && uvx --from ruff==0.14.0 ruff check articles/tests.py"
  - "cd project-a && uvx --from ruff==0.14.0 ruff format --check articles/tests.py"
  - "git diff --check"
artifacts:
  - project-a/articles/tests.py
  - project-a/AI/verification.md
  - project-a/AI/运行说明.md
  - project-a/AI/CLAUDE.md
---

## What changed

`articles/tests.py` 从 567 行、43 项缩减为 273 行、16 项。保留 5 项信号审计、10 项网页与附件测试、1 项编辑与浏览量交错更新的回归测试。移除额外后台和边界场景测试，以及不再使用的导入；保留的测试断言不变。

精简前 43 项和精简后 16 项均通过；独立并发脚本验证 4 个线程、24 次访问的浏览量准确累加；Ruff 检查和格式检查通过。运行说明、验收记录与索引已同步，业务代码未改动。

## Why it matters

缩小学习与审阅范围，使测试围绕原题的信号审计、附件作者权限、文章操作和并发浏览量。保留正常流程、无效表单、越权场景与关键交错更新验证。

## Demo posture / limitations

这次不代表原 43 项覆盖全部保留：Admin、事务回滚、raw 导入、部分字段保存、缺失文件、CSRF、模板转义、独立登录登出等不再有单独测试。独立多连接并发验证仍保留。本轮未修改业务行为、数据库或原题 README，未执行浏览器验收，也不代表生产就绪或已经发布。

运行说明和验收记录遵循仓库现有约定存放于忽略的 `AI/`，不会随普通 Git 提交分发；本变更条目与测试文件可正常纳入版本控制。

## 已完成计划

- [x] 原 43 项测试通过，按原题核对保留范围。
- [x] 精简额外测试，保留核心权限与旧实例编辑回归测试。
- [x] 精简后 16 项测试、独立并发验证和 Ruff 检查通过，核对差异范围。
- [x] 同步运行说明、验收记录和索引，归档本任务；其他进行中的任务保持原样。
