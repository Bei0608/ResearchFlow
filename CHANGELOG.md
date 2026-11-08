# Changelog

## V1.1.0 - 2026-11-08

### Added

- 原创、可分发且不含人工评分的 Agent 评测 demo bundle；
- `verify/install/reset` 演示数据管理命令和安全命名空间标记；
- V1.0 程序测试与质量指标兼容基线；
- 6 项演示数据一致性、幂等性、评分来源和安全重置测试；
- P1 数据盘点、需求追踪、决策和阶段状态记录。
- Workspace、成员关系、Agent Application 与不可变 Agent Version；
- `0002_v11` Alembic迁移、个人Workspace自动创建及旧用户幂等补建；
- 配置快照敏感字段扫描、Workspace作用域API、审计和越权测试。
- 版本化Evaluation Dataset/Case与Rubric/Criterion目录；
- `0003_v11`迁移、草稿CRUD、发布校验、发布后不可变和Workspace隔离；
- 规范化JSON SHA-256、数据库内容唯一约束及演示JSON幂等Importer。
- EvaluationRun、CaseResult、ProgramMetric及`0004_v11`迁移；
- 统一同步Runner、Evaluator接口、部分失败保留和不可逆结束状态；
- 运行读取API、无模型demo持久化CLI及原检索/答案CLI兼容改造。
- ReviewTask/Assignment/Review/Revision/HumanScore及`0005_v11`迁移；
- 草稿恢复、乐观锁、幂等保存、完整提交、纠错修订和任务自动完成；
- reviewer成员接入、角色隔离、审计及Jinja2最小人工评审页面。
- AggregateMetric、Report及`0006_v11`迁移；
- 程序/人工分区聚合、完成率与缺失数、最新有效人工提交统计；
- 可追溯案例且自动转义的JSON/HTML报告、SHA-256和受保护下载API。
- Baseline、GatePolicy、GateEvaluation及`0007_v11`迁移；
- 绝对下限/最大回退规则、PASSED/FAILED/INCOMPLETE及逐规则原因；
- 报告Gate区块、数据库/离线CLI退出码和CI演示门禁。
- 完整无模型demo幂等bootstrap、CI空PostgreSQL迁移与双次初始化检查；
- 显式环境变量优先级修复、Windows CLI UTF-8输出修复及对应回归测试；
- P8空库、API、浏览器、V1.0兼容性和发布文档验收。

### Verified

- 本机及 Docker 内无模型密钥完成 verify/install/unchanged/reset；
- 全量测试 91 passed；
- P2全量测试提升至102 passed；
- P3全量测试提升至110 passed，真实PostgreSQL重复导入返回同一版本ID；
- P4全量测试提升至117 passed；真实数据库验证完整运行与部分失败保留；
- 改造后检索指标保持基线，答案在线运行通过门禁但记录到模型输出漂移。
- P5全量测试提升至120 passed；真实数据库完成4案例人工评审与修订闭环；
- 浏览器验证评审页面和窄屏布局，控制台无warning/error。
- P6全量测试提升至125 passed；真实数据库验证旧修订/草稿不进入人工均值；
- 容器HTTP生成JSON/HTML报告成功，跨用户统计访问返回404。
- P7全量测试提升至131 passed；真实DB重复门禁结果一致；
- 真实CLI验证passed/failed/incomplete退出码分别为0/2/3。
- 检索和答案质量门禁保持 V1.0 基线。
- P8全量测试提升至132 passed；隔离空库迁移到`0007_v11 (head)`；
- 两次bootstrap复用相同用户、应用、数据、运行和任务，Gate为passed；
- 浏览器完成4/4评审流程，JSON/HTML报告完成，跨用户访问返回404。

## V1.0.0 - 2026-11-05

### Added

- Redis 共享限流、检索 cache-aside 与索引版本失效；
- Alembic 初始迁移及容器启动自动升级；
- 用户改密、Refresh 会话全量撤销和安全审计事件；
- 资源受众/Scope 绑定的 MCP JWT、protected-resource metadata 与受保护 HTTP；
- 检索/答案发布门禁、V1 baseline、CI Docker Build 和 GHCR Release 工作流；
- Redis readiness、缓存/限流 Prometheus 指标及生产 Caddy MCP 路由；
- 缓存、共享限流、安全令牌和审计相关自动化测试。

### Changed

- API 与 MCP 服务版本升级为 `1.0.0`；
- 生产 Compose 将 PostgreSQL、Redis、API、MCP 放入内部网络，由 Caddy 统一入口；
- Windows MCP 演示客户端强制 UTF-8 输出，兼容论文中的特殊字符。

### Verified

- 85 项 pytest 全部通过；
- 检索：Hit@5=1.000、Mean Recall@5=1.000、MRR=0.972；
- 答案：综合分=0.988、路由准确率=1.000、关键词召回=0.967；
- 真实容器完成注册、登录、MCP Token Exchange、受保护工具调用、改密撤销与审计验收。
