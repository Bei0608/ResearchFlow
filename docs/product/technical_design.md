# 技术方案

## 1. 当前基线

现有项目是 Python 3.12 模块化单体，已包含 FastAPI、LangChain Agent、LangGraph、
PostgreSQL、Milvus、Redis、MCP、Alembic、Prometheus、Docker Compose 和 85 项测试。
现有评测通过 JSON 数据集和 CLI 脚本产生 JSON 报告，但结果没有形成可修改、可
审计的业务实体，也没有人工评审页面、评分修订、统计和报告生命周期。

## 2. 最小方案

继续使用模块化单体，在现有 FastAPI 中新增评测领域模块和最小服务端页面：

```text
Browser / CLI / CI
        |
FastAPI API + Jinja2 Review UI
        |
Evaluation Application Services
   |            |             |
PostgreSQL   Existing Agent   Report Renderer
 business     / RAG runner      JSON + HTML
 metadata
        |
Redis cache/rate-limit     Milvus vectors
```

V1.1 不引入 React、微服务、Celery、MinIO。程序评测由统一 Python Service 执行，
CLI 和 API 调用相同服务；规模变大后再把同一 Service 放入 Worker，避免先设计两套
执行逻辑。

## 3. 关键选择与代价

| 选择 | 理由 | 代价/边界 |
|---|---|---|
| 模块化单体 | 改动小、容易测试，适合当前规模 | 不能独立扩缩每个领域 |
| PostgreSQL 作为业务事实源 | 已部署，事务、JSONB和约束足够 | 大型报告/原始文件后续需对象存储 |
| Jinja2 + 原生JS | 最少前端成本即可完成评审流程 | 交互和组件生态弱于SPA |
| 同步Service + CLI | 先完成业务闭环，复用现有脚本 | 长任务不能占用API；V1.1 API只允许小型演示运行 |
| 不可变发布版本 | 实验可复现 | 修正内容必须新建版本 |
| 修订而非覆盖评分 | 可审计、统计有确定来源 | 表和查询更复杂 |
| 人工/程序指标分表或显式source | 防止混淆 | 报表需要两套聚合 |
| JSON + HTML 报告 | 同时服务CI和人工查看 | PDF需后续渲染链路 |
| Repository层做Workspace隔离 | 所有入口共享安全边界 | 每个查询都必须携带作用域 |

## 4. 核心执行流程

### 程序评测

```text
create run -> snapshot config -> execute cases -> store outputs
-> execute program evaluators -> aggregate program metrics
-> mark READY_FOR_REVIEW -> create review task
```

运行失败也保存已完成案例和错误，不把部分成功伪装成完整成功。

### 人工评审

```text
open task -> open case -> save DRAFT -> revise -> SUBMIT
-> aggregate latest submitted human scores -> generate report
```

### 基线门禁

```text
candidate metrics + active baseline + versioned gate policy
-> per-rule comparison -> PASSED / FAILED / INCOMPLETE
```

人工评审未完成时，人工 Gate 应为 `INCOMPLETE`，而不是失败或零分。

## 5. API 与页面边界

REST API 负责所有业务写入；页面通过同一 API/Service，不直接访问数据库。主要
资源为 workspace、application/version、evaluation dataset/version、rubric/version、
run/result、review task/revision、metric、baseline、gate 和 report。

最小页面：

- `/review/tasks`：我的任务；
- `/review/tasks/{id}`：进度和案例列表；
- `/review/tasks/{id}/cases/{case_id}`：评审表单；
- `/api/v1/evaluation-runs/{id}/summary`：程序/人工分区统计；
- `/api/v1/evaluation-runs/{id}/reports`：生成和列出报告；
- `/api/v1/reports/{id}/content`：受权限保护的JSON/HTML报告内容。

## 6. 一致性与幂等

- 保存草稿使用 `expected_revision` 做乐观并发控制；
- 重复请求携带 `Idempotency-Key`，相同用户/资源/Key 返回原结果；
- 提交评审在事务中验证完整性、写 revision、更新任务进度和审计；
- 报告只读取指定 run 的不可变快照和最新有效提交；
- 聚合可重新计算，不把缓存统计视为唯一事实。

## 7. 安全

- 复用现有 JWT 用户身份；
- 新建个人默认 Workspace，资源都携带 `workspace_id`；
- Repository 查询同时使用资源 ID 和 Workspace ID；
- 越权统一返回 404 或按既定策略返回 403，不返回其他用户内容；
- 修改评分、发布版本、设置 Baseline、生成报告写入审计事件；
- 报告转义用户输入，防止存储型 XSS。

## 8. 数据与测试分离

建议目录：

```text
data/demo/                         # 可提交的原创演示资料和seed manifest
evaluations/demo/                  # 可展示的运行输入/预期输出
tests/fixtures/                    # 程序测试夹具，不作为业务运行结论
evaluations/results/               # 本地生成结果，默认忽略Git
reports/generated/                 # 本地报告，默认忽略Git
```

演示 Seed 必须带 `environment=demo`。人工评分只能由明确的评审操作生成；若为了
页面截图提供示例评分，必须使用 `source=demo_seed`，不能标记为 `human`。

## 9. 测试策略

- 单元：评分校验、状态机、聚合、Gate、报告 ViewModel；
- Repository：唯一约束、版本不可变、修订并发、Workspace 隔离；
- API：完整评审流程、字段错误、幂等和越权；
- 页面：关键表单渲染、HTML转义、保存/提交路径；
- 集成：现有真实 RAG 运行写入统一模型；
- 端到端：Docker 干净环境加载 demo seed，完成验收场景；
- 回归：现有 85 项测试和 V1.0 质量指标不得下降。

## 10. 可观测性

新增指标至少包括评测运行数量/耗时/失败、待评审数量、草稿/提交数、报告生成
耗时和 Gate 结果。日志包含 request_id、run_id、task_id，不记录答案全文或 Token。
