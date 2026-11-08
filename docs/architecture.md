# ResearchFlow V1.1 架构与设计决策

## Agent 与 Workflow 为什么并存

LangChain Agent 面向开放式、多轮交互，由模型选择论文和记忆工具；LangGraph
Workflow 面向严格论文问答，由代码固定检索、证据判定、回答、拒答和异常降级
路径。前者强调灵活，后者强调可审计、可测试。API、MCP 与 CLI 复用同一业务层，
不复制 RAG 实现。

## 状态与存储边界

| 数据 | 主键/标识 | 存储 | 目的 |
|---|---|---|---|
| 用户身份 | `user_id` | PostgreSQL | 用户、Argon2 哈希、启用状态 |
| 登录会话 | JWT `jti` | PostgreSQL | Refresh Token 轮换与撤销 |
| 安全审计 | `event_id` | PostgreSQL | 登录、改密、Token、研究调用轨迹 |
| 工作空间 | `workspace_id` | PostgreSQL | 多用户资源作用域和owner/reviewer角色 |
| Agent应用 | `application_id` | PostgreSQL | 被评测目标及接入类型 |
| Agent版本 | `agent_version_id` | PostgreSQL | 模型/Prompt/工具/检索配置快照；发布后不可变 |
| 评测集版本/案例 | `dataset_version_id` / `case_id` | PostgreSQL | 规范化内容哈希；发布后不可变 |
| 量表版本/准则 | `rubric_version_id` / `criterion_id` | PostgreSQL | 评分范围、权重和必填规则；发布后不可变 |
| 评测运行/案例结果 | `run_id` / `case_result_id` | PostgreSQL | 状态、输出、证据、耗时、Token与错误 |
| 程序指标 | `program_metric_id` | PostgreSQL | 固定source=program及Evaluator版本 |
| 人工评审任务 | `task_id` / `assignment_id` | PostgreSQL | reviewer分配、进度与完成状态 |
| 人工修订/评分 | `revision_id` / `score_id` | PostgreSQL | 不可变历史、乐观锁；与程序指标分表 |
| 聚合指标/报告 | `aggregate_metric_id` / `report_id` | PostgreSQL + 文件 | 可重建统计投影与带哈希JSON/HTML产物 |
| Baseline/门禁 | `baseline_id` / `gate_evaluation_id` | PostgreSQL | 活动基线、版本化规则和三态发布结论 |
| 会话所有权 | `thread_id` | PostgreSQL | 阻止跨用户 checkpoint 访问 |
| 图会话状态 | `thread_id` | PostgresSaver | 消息、工具调用和图状态 |
| 长期用户记忆 | 用户命名空间 | PostgresStore | 跨会话偏好和目标 |
| 论文向量 | `chunk_id` | Milvus | 原文、元数据和向量 |
| 限流/检索缓存 | 哈希键 | Redis | 多实例共享计数与低延迟复用 |

Checkpointer、Store 和向量库解决的是三个不同问题，不能互相替代。JWT 只证明
调用者身份；`thread_id -> user_id` 归属校验进一步限制其可以访问的会话。

## RAG 与缓存

```text
PDF -> Page Document -> clean -> overlap chunk -> SHA-256 IDs
    -> Qwen Embedding -> Milvus -> MMR -> threshold
    -> grounded answer / deterministic refusal
```

默认取 `4 * top_k` 候选，以 `lambda=0.65` 做 MMR 去冗余，再使用稠密相似度
阈值 `0.45`。相似度表示相关性，不等于事实置信度，所以 Workflow 还有结构化
证据充分性判断。

检索采用 cache-aside：查询参数、collection 和索引版本共同生成 SHA-256 Key。
命中时跳过 Embedding/Milvus；索引新增成功后递增 Redis 版本号，旧缓存因 Key
变化自然失效，无需扫描删除。Redis 故障时记录指标并回退到真实检索。

## 安全模型

- API Token 校验签名、算法、有效期、issuer、audience、token type 和 claims；
- Refresh Token 在 PostgreSQL 中轮换，旧 Token 重放失败；改密撤销全部会话；
- Redis Lua 脚本原子执行 `INCR + EXPIRE`，所有 API 副本共享窗口；
- MCP HTTP 令牌独立签发，绑定 MCP resource audience 和 scopes，普通 API
  Access Token 不能替代；令牌主体还必须对应活跃用户；
- 审计写入采用 best-effort，审计库短暂异常不会让核心请求产生二次故障；
- MCP 的工具注解只是客户端提示，真正授权由 HTTP 资源服务器完成。

当前 Token Exchange 适合本项目第一方 API/MCP 部署；它不是完整的第三方 OAuth
2.1 授权码服务器。面向任意外部 MCP 客户端时，应连接独立 Authorization Server。

## 数据迁移与可靠性

Alembic `0001_v1` 建立身份、安全与会话基础；`0002_v11`至`0007_v11`依次增加
Workspace/应用、评测目录、运行、人工评审、统计报告和质量门禁。容器启动
顺序是依赖健康检查 -> `alembic upgrade head` -> API；迁移为事务 DDL，并保留
应用侧幂等建表作为现有开发数据库的兼容兜底。

模型/Embedding 有超时和有限重试；Workflow 区分证据不足与依赖故障；SSE 使用
`stream_mode="updates"` 发送真实节点完成事件；Redis 缓存/限流异常均有降级路径；
readiness 同时检查 PostgreSQL、Milvus 和 Redis。

## 评测与发布结论链路

```text
AgentVersion + DatasetVersion
        -> EvaluationRun -> CaseResult -> ProgramMetric
        -> ReviewTask -> ReviewRevision -> HumanScore
        -> AggregateMetric -> JSON/HTML Report
        -> Baseline + GatePolicy -> PASSED / FAILED / INCOMPLETE
```

程序和人工事实不混表、不生成隐式总分。聚合仅使用最新有效人工提交；报告是可重建
的派生产物。Gate通过`source + namespace/evaluator version + metric key`精确定位指标，
缺Baseline、缺指标或人工未完成时返回INCOMPLETE而不是零分。

## 质量与交付

测试分为纯单元测试、真实 PDF 集成测试、隔离空库初始化和容器端到端验收。检索门禁检查 Hit、
Recall、MRR；答案门禁检查路由、关键词、引用合法性与拒答。GitHub Actions 在
PR 上执行编译、离线迁移、测试、确定性Gate、空库幂等bootstrap和Docker Build；
`v*` Tag在重新验证后触发GHCR镜像发布。

## 已知边界

1. 没有邮箱找回、管理员控制台和完整第三方 OAuth 授权码流程；
2. 审计目前提供用户自查，不是不可篡改的 SIEM 归档；
3. 小论文集指标不能外推到开放域，阈值随语料变化需重做评估；
4. 生产 Secrets 仍需由部署平台/Vault/KMS 托管。
