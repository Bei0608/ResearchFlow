# ResearchFlow V1.1

ResearchFlow 是一个面向具身智能、VLA 与机器人控制论文的多用户 AI 研究
助手。项目把 PDF RAG、LangChain Agent、确定性 LangGraph 工作流、长期记忆、
FastAPI、受保护的 MCP、可观测性与自动化质量门禁整合为一套可测试、可部署的
工程架构。

## V1.1 能力

- PDF 清洗、重叠分块、稳定 `document_id/page_id/chunk_id` 与幂等增量索引；
- Qwen Embedding（1024 维）、Milvus、MMR 检索、Redis 检索缓存与索引版本失效；
- 带文件/物理页码引用的证据回答，以及证据不足时的确定性拒答；
- LangChain Agent 自主选择论文/记忆工具，LangGraph 固定编排严谨问答路径；
- PostgresSaver 会话状态、PostgresStore 跨会话记忆与多用户 thread 所有权；
- Argon2、JWT Access/Refresh 轮换撤销、改密、审计事件和 Redis 共享限流；
- FastAPI REST、真实节点级 SSE、OpenAPI、JSON 日志与 Prometheus 指标；
- MCP Python SDK v2：stdio 与受 Bearer Token 保护的 Streamable HTTP；
- Alembic 数据迁移、Docker Compose、Caddy HTTPS、CI 与 GHCR Release 工作流；
- 132 项自动化测试，以及会阻止回归发布的检索/答案质量门禁；
- 版本化评测目录、程序运行、人工评审修订、分区统计、JSON/HTML报告、
  Baseline对比和三态发布门禁。

## 架构

```text
CLI / Swagger / MCP Client
          |                       |
          v                       v
 FastAPI :8000              MCP HTTP :8001
 JWT / SSE / Audit          resource-bound JWT
          +-----------+-----------+
                      v
       LangChain Agent / LangGraph Workflow
                      |
           Redis retrieval cache
                      |
       Qwen Embedding + Milvus MMR RAG

PostgreSQL: identity, refresh sessions, audit, thread ownership,
            checkpoints and long-term memory
Redis: shared rate limiting, retrieval cache and index version
```

严格问答路径：

```text
START -> prepare -> retrieve -> evaluate -> judge
                                  |         |-- answer -> generate -> END
                                  |         `-- insufficient -> refuse -> END
                                  `-- error ---------------------> degrade -> END
```

更多设计取舍见 [架构文档](docs/architecture.md)。

面向下一阶段评测中台建设的需求、验收、评审流程和实施计划，统一维护在
[产品与实施文档索引](docs/product/README.md)。

## 技术栈

Python 3.12、LangChain 1.4、LangGraph 1.2、FastAPI、MCP Python SDK 2、
PostgreSQL 16、Milvus、Redis 8、Alembic、Qwen Embedding、DeepSeek、Docker
Compose、Caddy、Prometheus、pytest、GitHub Actions。

## 快速开始

### 1. 创建环境

```powershell
mamba create -n researchflow python=3.12
mamba activate researchflow
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

填写 `.env` 中的模型密钥和数据库配置。生成 JWT 密钥：

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. 启动完整服务

Milvus 默认由已有 Docker 服务监听 `localhost:19530`；本仓库 Compose 启动 API、
MCP、PostgreSQL 和 Redis，并在 API 启动前自动执行 Alembic 迁移。

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

- Swagger：<http://127.0.0.1:8000/docs>
- Readiness：<http://127.0.0.1:8000/api/v1/health/ready>
- MCP：`http://127.0.0.1:8001/mcp`
- 指标：<http://127.0.0.1:8000/metrics>
- 人工评审页：<http://127.0.0.1:8000/review>

首次准备论文索引：

```powershell
python -m scripts.index_papers
```

索引器只向量化 Milvus 中不存在的稳定 `chunk_id`，成功写入后递增 Redis 索引
版本，使旧检索缓存自动失效。

### 3. 无模型密钥演示数据

项目内置原创合成数据，可在没有模型 API Key、本地论文和 Milvus 时验证后续评审
业务的数据边界：

```powershell
python -m scripts.manage_demo_data verify
python -m scripts.manage_demo_data install
python -m scripts.manage_demo_data install  # 再次执行返回unchanged
python -m scripts.manage_demo_data reset
```

安装只写入被 Git 忽略的 `runtime/demo`；重置只删除安装标记中列出的受管文件，
不会删除同目录下的用户文件。程序指标标记为 `source=program`，数据包不预填人工
评分。详细边界见 [P1数据盘点](docs/product/data_inventory.md)。

要一次建立可登录、可评审、可统计、可生成报告和执行Gate的完整数据库演示：

```powershell
$env:RESEARCHFLOW_DEMO_PASSWORD = "请替换为至少8位的演示密码"
python -m scripts.bootstrap_demo_platform --username researchflow-demo
Remove-Item Env:RESEARCHFLOW_DEMO_PASSWORD
```

命令可重复执行且复用原有业务ID；密码只在首次创建用户时读取且不会输出。该流程
使用预生成候选输出和程序指标，不调用外部模型，也不伪造人工评分。随后访问
`http://127.0.0.1:8000/review`，使用上述账号完成人工评审。

## API 与身份认证

除健康、注册和登录外，业务 API 都要求 `Authorization: Bearer <access-token>`。
用户身份始终取自已签名 JWT 的 `sub`，不信任请求体中的用户 ID。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/auth/register` | 注册，密码保存为 Argon2 哈希 |
| `POST` | `/api/v1/auth/token` | 登录并签发 Access/Refresh Token |
| `POST` | `/api/v1/auth/refresh` | 原子轮换 Refresh Token |
| `POST` | `/api/v1/auth/logout` | 撤销 Refresh 会话 |
| `POST` | `/api/v1/auth/change-password` | 改密并撤销该用户所有 Refresh 会话 |
| `POST` | `/api/v1/auth/mcp-token` | 换取短期、资源绑定的 MCP Token |
| `GET` | `/api/v1/users/me/audit-events` | 查看自己的安全审计事件 |
| `GET` | `/api/v1/workspaces` | 当前用户可访问的Workspace；自动补建个人空间 |
| `POST/GET` | `/api/v1/workspaces/{id}/applications` | 创建或列出Workspace中的Agent应用 |
| `POST/GET` | `/api/v1/applications/{id}/versions` | 创建或列出Agent配置快照 |
| `PUT` | `/api/v1/applications/{id}/versions/{version_id}` | 修改草稿版本；发布后拒绝 |
| `POST` | `/api/v1/applications/{id}/versions/{version_id}/publish` | 发布不可变Agent版本 |
| `POST/GET` | `/api/v1/workspaces/{id}/evaluation-datasets` | 创建或列出评测集 |
| `POST/GET` | `/api/v1/evaluation-datasets/{id}/versions` | 创建或列出评测集版本 |
| `POST/GET` | `/api/v1/evaluation-datasets/{id}/versions/{version_id}/cases` | 管理草稿案例 |
| `POST` | `/api/v1/evaluation-datasets/{id}/versions/{version_id}/publish` | 校验并发布不可变评测集版本 |
| `POST/GET` | `/api/v1/workspaces/{id}/rubrics` | 创建或列出人工评分量表 |
| `POST/GET` | `/api/v1/rubrics/{id}/versions` | 创建或列出量表版本 |
| `POST/GET` | `/api/v1/rubrics/{id}/versions/{version_id}/criteria` | 管理草稿评分准则 |
| `POST` | `/api/v1/rubrics/{id}/versions/{version_id}/publish` | 校验并发布不可变量表版本 |
| `POST/GET` | `/api/v1/workspaces/{id}/evaluation-runs` | 创建或列出程序评测运行 |
| `GET` | `/api/v1/evaluation-runs/{run_id}` | 查看运行、案例结果和程序指标 |
| `POST` | `/api/v1/workspaces/{id}/reviewers` | 将已有用户加入Workspace reviewer |
| `POST` | `/api/v1/evaluation-runs/{id}/review-tasks` | 为就绪运行创建人工评审任务 |
| `GET` | `/api/v1/review-tasks/mine` | 当前评审人的任务列表 |
| `GET` | `/api/v1/review-tasks/{id}` | 查看进度、案例和量表 |
| `PUT` | `/api/v1/review-tasks/{id}/cases/{case_id}/draft` | 幂等保存人工评分草稿 |
| `POST` | `/api/v1/review-tasks/{id}/cases/{case_id}/submit` | 校验并正式提交人工评分 |
| `POST` | `/api/v1/review-tasks/{id}/cases/{case_id}/revisions` | 为已提交评分创建纠错修订 |
| `GET` | `/api/v1/evaluation-runs/{id}/summary` | 查看程序/人工分区统计和评审完成率 |
| `POST/GET` | `/api/v1/evaluation-runs/{id}/reports` | 生成或列出JSON/HTML报告 |
| `GET` | `/api/v1/reports/{id}/content` | 下载有权限访问的报告内容 |
| `PUT/GET` | `/api/v1/applications/{id}/baseline` | 激活或读取应用的活动Baseline |
| `POST/GET` | `/api/v1/workspaces/{id}/gate-policies` | 创建或列出版本化门禁策略 |
| `POST` | `/api/v1/gate-policies/{id}/publish` | 发布不可变Gate Policy |
| `POST/GET` | `/api/v1/evaluation-runs/{id}/gate-evaluations` | 执行或查看质量门禁 |
| `POST` | `/api/v1/chat` | 运行开放式 Agent |
| `POST` | `/api/v1/research` | 运行固定 LangGraph 研究工作流 |
| `POST` | `/api/v1/research/stream` | SSE 推送真实节点进度 |
| `GET/PUT/DELETE` | `/api/v1/users/me/memories/...` | 管理自己的长期记忆 |

同一 `thread_id` 首次使用时会原子绑定当前用户；其他用户访问会得到 `403`。

P1演示评测集和量表可幂等导入已存在的个人Workspace：

```powershell
python -m scripts.import_evaluation_catalog `
  --workspace-id <workspace-id> `
  --user-id <user-id> `
  --dataset evaluations/demo/evaluation_dataset.json `
  --rubric evaluations/demo/rubric.json
```

相同内容再次导入返回原版本ID；发布版本的Case和Criterion不能原地修改。

离线CI可使用随项目提供的确定性夹具执行门禁：

```powershell
python -m scripts.evaluate_gate --fixture evaluations/demo/gate_check.json
```

退出码：`0=passed`、`2=failed`、`3=incomplete`，运行错误使用`1`。

准备已发布的AgentVersion和DatasetVersion后，可将无模型演示运行写入PostgreSQL：

```powershell
python -m scripts.run_demo_evaluation `
  --workspace-id <workspace-id> `
  --user-id <user-id> `
  --agent-version-id <agent-version-id> `
  --dataset-id <dataset-id> `
  --dataset-version-id <dataset-version-id>
```

该命令明确标记为预生成demo，只验证Runner和持久化链路。真实检索与答案质量仍用
`scripts.evaluate_retrieval`、`scripts.evaluate_answers`，两者现在复用同一Runner。

人工评审页面：<http://127.0.0.1:8000/review>。登录后可查看任务、证据和程序指标，
保存部分草稿、正式提交，并为已提交评分创建带原因的纠错修订。程序指标与人工量表
分区展示，人工评分保存在独立事实表。

## MCP 与 Skill

MCP 提供论文目录、原文证据检索、完整研究问答三个工具。stdio 用于本机受信任
进程；HTTP 默认开启鉴权。先用 API Access Token 换取资源受众为 MCP URL 的
短期 Token，再运行客户端：

```powershell
$mcp = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/mcp-token `
  -Headers @{Authorization="Bearer $($token.access_token)"}
$env:MCP_ACCESS_TOKEN = $mcp.access_token
python -m scripts.mcp_client_demo --url http://127.0.0.1:8001/mcp
```

本机 stdio 演示仍可直接运行：

```powershell
python -m scripts.mcp_client_demo
```

`skills/researchflow-paper-research/` 定义领域工具选择、引用与拒答规则。当前 API
完成的是第一方 JWT Token Exchange 和 MCP 资源服务器校验，不冒充完整的第三方
OAuth 2.1 Authorization Server；对公网开放给任意 MCP 客户端时应接入标准授权服务。

## 测试与质量门禁

```powershell
$env:PYTHONUTF8='1'
python -m pytest -v
python -m scripts.evaluate_retrieval
python -m scripts.evaluate_answers
```

当前全量测试为132项通过；V1.0兼容基线中的18条可回答检索题取得 Hit@5=1.000、
Mean Recall@5=1.000、MRR=0.972；10 条答案集综合分=0.988、路由准确率=1.000、
关键词召回=0.967。评估脚本低于 `evaluations/baselines/v1.json` 阈值时返回非零
退出码，适合作为发布门禁。这些结果仅代表仓库内论文集，不代表通用能力。

## 生产部署与发布

```powershell
docker compose --env-file .env -f deploy/compose.prod.yaml config
docker compose --env-file .env -f deploy/compose.prod.yaml up -d --build
```

生产模板使用 Caddy 作为唯一 HTTPS 入口，保护 MCP，隐藏 `/metrics` 和数据库
端口。`ci.yml` 在提交/PR 上运行编译、迁移校验、测试和镜像构建；推送 `v*`
Tag 后，`release.yml` 将版本镜像发布到 GHCR。CI 还会从空PostgreSQL执行全部迁移，
连续两次运行完整demo初始化以验证幂等性。运维步骤见
[运维手册](docs/operations.md)，学习回顾顺序见
[代码学习指南](docs/learning_guide.md)，版本变化见 [CHANGELOG](CHANGELOG.md)。

## 安全边界

- 生产密钥应放入 GitHub Environments、Vault/KMS 或平台 Secret，不写入仓库；
- Redis/PostgreSQL/Milvus 只应位于私网，Caddy 是唯一公网入口；
- MCP Token 会校验签名、issuer、resource audience、scope、类型和用户状态；
- 当前不含邮箱找回、管理员控制台和完整第三方 OAuth 授权码流程；
- `0.45` 是现有小型论文集上的经验阈值，扩充语料后必须重新评估。
