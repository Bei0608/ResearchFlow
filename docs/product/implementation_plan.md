# 阶段实施计划表

## 阶段状态约定

`NOT_STARTED`、`IN_PROGRESS`、`BLOCKED`、`DONE`。每阶段结束必须在
`project_status.md` 记录完成内容、真实验证、遗留问题和下一步，不能仅更新本表。

## 总计划

| 阶段 | 目标 | 主要需求 | 状态 |
|---|---|---|---|
| P0 | 治理与验收基线 | MUST-10/11/17 | DONE |
| P1 | 可复现演示数据和现状冻结 | MUST-08/09 | DONE |
| P2 | Workspace、应用和不可变版本 | MUST-12/16 | DONE |
| P3 | 评测集与量表版本 | MUST-13 | DONE |
| P4 | 程序评测运行持久化 | MUST-14 | DONE |
| P5 | 人工评审保存、修改、提交闭环 | MUST-01~05 | DONE |
| P6 | 统计与报告 | MUST-06/07/09 | DONE |
| P7 | Baseline、质量门禁与CI | MUST-15 | DONE |
| P8 | 容器验收、文档与发布 | 全部MUST | DONE |
| E1 | 异步任务 | SHOULD-02 | DEFERRED |
| E2 | 数据中台与血缘 | SHOULD-05 | DEFERRED |
| E3 | Agent轨迹和高级评测 | SHOULD-03/06 | DEFERRED |

## P0：治理与验收基线

1. 检查当前目录、代码、评测数据、迁移和 Git 状态；
2. 建立根目录长期提示词；
3. 建立原题来源、需求追踪和歧义记录；
4. 建立评审人完整操作流程；
5. 建立技术方案、数据模型和模块边界；
6. 建立决策、状态、真实对话日志；
7. 对文档进行链接、术语、范围和读者问题检查。

验收：所有文档存在；每项 MUST 有验收方法；不存在把建议写成原题事实的表述。

## P1：可复现演示数据和现状冻结

1. 盘点现有 JSON 评测集、PDF 依赖和生成结果；
2. 设计不含版权论文的原创最小知识文档；
3. 建立 `data/demo`、`evaluations/demo` 和 `tests/fixtures` 边界；
4. 创建演示 Agent 输出、程序指标和量表，不生成伪人工评分；
5. 编写幂等 Seed/Reset 命令，Reset 只删除明确 demo namespace；
6. 记录 V1.0 的 85 项测试和质量指标作为兼容基线；
7. 在无模型密钥场景完成一次 demo data 加载测试。

验收：克隆仓库后仅依赖 Docker 即可加载演示数据；测试数据和演示数据有显式标签。

## P2：Workspace、应用和不可变版本

1. 确认 A-03~A-09 业务规则；
2. 设计并审查 Workspace/Application/AgentVersion migration；
3. 实现 Repository 和唯一/外键约束；
4. 实现个人默认 Workspace；
5. 实现应用创建、列表和版本快照；
6. 实现发布后不可修改规则；
7. 增加跨 Workspace 越权测试；
8. 更新审计事件和 OpenAPI。

验收：两个用户资源隔离；发布版本不可更新；配置快照不包含密钥。

## P3：评测集与量表版本

1. 新增 Dataset/Version/Case 表和状态机；
2. 新增 Rubric/Version/Criterion 表和约束；
3. 实现草稿创建、案例增删改；
4. 发布前校验内容完整性；
5. 发布后禁止原地修改；
6. 编写现有 JSON 数据集 importer；
7. 使用 content hash 实现重复导入幂等；
8. 增加版本、边界值和越权测试。

验收：同一文件重复导入不生成重复版本；已发布内容无法被修改。

## P4：程序评测运行持久化

1. 定义 Run/CaseResult/ProgramMetric 状态和 DTO；
2. 把检索评测抽象为 Evaluator；
3. 把答案质量评测抽象为 Evaluator；
4. 编写统一 Evaluation Runner；
5. CLI 改为调用 Runner，同时保留原命令兼容；
6. 保存配置、Git Commit、输出、错误、耗时和 Token；
7. 实现失败后保留部分结果；
8. 用真实现有数据运行并核对旧指标。

验收：数据库中的聚合值与现有 JSON 报告一致；程序指标均标记 evaluator/version。

## P5：人工评审闭环

1. 新建 ReviewTask/Assignment/Review/Revision/HumanScore 表；
2. 实现任务分配和“我的任务”查询；
3. 实现案例详情和量表 ViewModel；
4. 实现草稿保存和重开恢复；
5. 实现 expected revision 乐观锁；
6. 实现必填校验和正式提交；
7. 实现已提交评分创建修订；
8. 实现任务进度和完成状态；
9. 建立 Jinja2 最小页面和原生JS交互；
10. 增加越权、重复保存、并发修改和XSS测试；
11. 按 reviewer_workflow 完成人工验收录像/记录。

验收：评审、保存、退出恢复、修改、提交、修订全流程通过，历史不被覆盖。

## P6：统计与报告

1. 明确人工和程序指标命名空间；
2. 实现程序指标聚合；
3. 实现仅使用最新有效提交的人工指标聚合；
4. 统计 sample_count、missing_count 和完成率；
5. 建立报告 ViewModel；
6. 实现 JSON Renderer；
7. 实现自动转义的 HTML Renderer；
8. 保存报告状态、路径和 content hash；
9. 增加固定数据快照测试和失败重试测试；
10. 人工核对报告中的样本和分数来源。

验收：报告能追溯到案例；人工与程序指标分区；草稿不计入正式均值。

## P7：Baseline、质量门禁与 CI

1. 新建 Baseline/GatePolicy/GateEvaluation；
2. 实现每应用一个 active baseline；
3. 定义绝对阈值和允许回退两种规则；
4. 实现 `PASSED/FAILED/INCOMPLETE`；
5. 将 Gate 结果写入报告；
6. CLI 根据 Gate 返回明确退出码；
7. CI 使用 demo 数据运行可重复门禁；
8. 测试缺失人工评分、无baseline和指标下降场景。

验收：同一 Candidate 对同一 Baseline/Policy 结果可重复；失败原因具体到规则。

## P8：容器验收、文档与发布

1. 更新 Compose、migration 启动顺序和健康检查；
2. 从空数据库执行 migration + demo seed；
3. 运行所有单元、集成和端到端测试；
4. 执行 8–12 分钟评审人操作脚本；
5. 生成并检查最终 JSON/HTML 报告；
6. 复测 V1.0 API、MCP、RAG、记忆和安全功能；
7. 更新 README、架构、运维、简历和 CHANGELOG；
8. 完成需求追踪证据路径；
9. 清点遗留问题与范围外内容；
10. 用户确认后再提交、打 Tag 和推送。

验收：所有 MUST 为 VERIFIED 或有明确未完成说明；干净环境操作可复现。

## 可选增强进入规则

只有当 P0–P8 的必做闭环完成且真实问题证明需要时，才进入 E1–E3。每个增强需
单独补需求、决策和验收，不能以“企业一般会用”为唯一理由加入。
