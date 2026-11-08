# 数据结构和主要模块划分

## 1. 数据关系总览

```text
User --< WorkspaceMember >-- Workspace
Workspace --< AgentApplication --< AgentVersion
Workspace --< EvaluationDataset --< EvaluationDatasetVersion --< EvaluationCase
Workspace --< Rubric --< RubricVersion --< RubricCriterion

AgentVersion + EvaluationDatasetVersion -> EvaluationRun
EvaluationRun --< EvaluationCaseResult --< ProgramMetric
EvaluationRun --< ReviewTask --< ReviewAssignment
ReviewAssignment + CaseResult -> Review --< ReviewRevision --< HumanScore

EvaluationRun --< AggregateMetric
AgentApplication --< Baseline
GatePolicy + EvaluationRun + Baseline -> GateEvaluation
EvaluationRun -> GeneratedReport
```

## 2. 表结构草案

所有 ID 使用 UUID 字符串；时间保存 UTC；JSON 配置必须同时保存 `schema_version`。

### Workspace 与成员

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_workspaces` | id, name, owner_id, created_at | owner必须为活跃用户 |
| `researchflow_workspace_members` | workspace_id, user_id, role | `(workspace_id,user_id)`唯一 |

V1.1 角色为 `owner/reviewer`，不提前建立复杂 RBAC。

### Agent 应用与版本

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_applications` | id, workspace_id, name, target_type | workspace内名称唯一 |
| `researchflow_agent_versions` | id, application_id, version, status, config_snapshot, git_commit, created_by | 发布后不可修改 |

`config_snapshot` 包含模型、Prompt、工具、检索和运行参数；敏感值只保存配置引用，
不保存 API Key。

### 评测集

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_evaluation_datasets` | id, workspace_id, name, description | workspace内名称唯一 |
| `researchflow_evaluation_dataset_versions` | id, dataset_id, version, status, content_hash | `(dataset_id,version)`唯一 |
| `researchflow_evaluation_cases` | id, version_id, external_id, input_json, expected_json, metadata | `(version_id,external_id)`唯一 |

状态：`DRAFT -> PUBLISHED -> ARCHIVED`。Published 版本及其 Case 不允许 UPDATE/DELETE。

### 量表

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_rubrics` | id, workspace_id, name | workspace内名称唯一 |
| `researchflow_rubric_versions` | id, rubric_id, version, status, instructions | 发布后不可变 |
| `researchflow_rubric_criteria` | id, rubric_version_id, key, title, min_score, max_score, weight, required | key在版本内唯一 |

量表版本进入评审任务后不可替换，避免同一任务使用不同口径。

### 评测运行和案例输出

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_evaluation_runs` | id, workspace_id, agent_version_id, dataset_version_id, status, trigger, config_snapshot, git_commit, timestamps, error | 引用不可变版本 |
| `researchflow_case_results` | id, run_id, case_id, status, output_json, evidence_json, trace_json, latency_ms, token_usage, error | `(run_id,case_id)`唯一 |
| `researchflow_program_metrics` | id, run_id, case_result_id?, evaluator_key, evaluator_version, metric_key, value, details, created_at | `source`固定program |

Run 状态：

```text
CREATED -> RUNNING -> READY_FOR_REVIEW
                   -> FAILED
READY_FOR_REVIEW -> COMPLETED
```

只要存在案例输出，失败运行也保留已生成数据。

### 人工评审

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_review_tasks` | id, run_id, rubric_version_id, status, due_at | run+rubric可重复但名称需区分 |
| `researchflow_review_assignments` | id, task_id, reviewer_id, status | `(task_id,reviewer_id)`唯一 |
| `researchflow_reviews` | id, assignment_id, case_result_id, latest_revision, status | `(assignment_id,case_result_id)`唯一 |
| `researchflow_review_revisions` | id, review_id, revision, status, overall_comment, reason, created_at, submitted_at | `(review_id,revision)`唯一 |
| `researchflow_human_scores` | id, revision_id, criterion_id, score, comment | `(revision_id,criterion_id)`唯一 |

ReviewRevision 状态：`DRAFT -> SUBMITTED -> SUPERSEDED`。修改已提交评分时创建下一
revision；旧 revision 变为 `SUPERSEDED`，但不删除。人工分不与 ProgramMetric 共表，
从结构上防止混淆。

### 统计、基线、门禁和报告

| 表 | 关键字段 | 约束 |
|---|---|---|
| `researchflow_aggregate_metrics` | run_id, source, metric_key, value, sample_count, missing_count, details | source为program/human |
| `researchflow_baselines` | application_id, run_id, activated_by, activated_at, active | 每应用最多一个active |
| `researchflow_gate_policies` | workspace_id, name, version, rules_json, status | 发布后不可变 |
| `researchflow_gate_evaluations` | run_id, baseline_run_id, policy_id, status, results_json | 同组合可重算并留时间 |
| `researchflow_reports` | run_id, format, status, storage_path, content_hash, generated_at, error | 路径不得由用户直接控制 |

AggregateMetric 是可重建投影，不是评分事实源。报告引用的所有版本和指标必须固定。

## 3. 数据示例：两类评分明确分离

程序指标：

```json
{
  "source": "program",
  "evaluator_key": "citation_validity",
  "evaluator_version": "1.0",
  "metric_key": "citation_validity",
  "value": 1.0
}
```

人工评分：

```json
{
  "source": "human",
  "reviewer_id": "user_xxx",
  "rubric_version": "grounded-answer-v1",
  "revision": 2,
  "status": "SUBMITTED",
  "scores": [
    {"criterion": "faithfulness", "score": 4, "comment": "证据支持主要结论"}
  ]
}
```

API 和报告不能返回一个没有解释公式的 `total_score` 将二者混合。

## 4. 模块划分

```text
app/
├── workspaces/
│   ├── models.py          # 领域数据类
│   ├── repository.py      # 作用域查询
│   └── service.py
├── applications/
│   ├── models.py
│   ├── repository.py
│   └── service.py         # Agent版本快照/发布
├── evaluation/
│   ├── datasets/          # 评测集和版本
│   ├── rubrics/           # 量表和准则
│   ├── runs/              # Run状态机、CaseResult
│   ├── evaluators/        # 程序Evaluator插件
│   ├── reviews/           # 任务、草稿、修订、提交
│   ├── metrics/           # 聚合统计
│   ├── gates/             # Baseline与门禁
│   └── reports/           # JSON/HTML报告
├── api/
│   ├── routers/           # REST API
│   └── review_ui/         # Jinja页面和静态资源
└── existing modules...    # agent/rag/memory/mcp/security
```

## 5. 模块职责边界

- Router：身份、请求校验、状态码，不写业务规则；
- Service：状态转换、事务边界、权限意图和审计调用；
- Repository：SQL、Workspace 过滤和并发控制；
- Evaluator：纯输入到指标结果，不能写数据库；
- Aggregator：只从事实表计算统计，可重复执行；
- Report Builder：把冻结数据转为 ViewModel；
- Renderer：JSON/HTML 序列化，不重新计算业务指标；
- Review UI：只调用 Service/API，不直接访问 Repository。

## 6. 与现有模块的关系

- `app/evaluation/answer_quality.py` 迁入 `evaluators/`，保留兼容导入层；
- 两个 `scripts/evaluate_*.py` 改为调用统一 Evaluation Service；
- `app/workflows/` 和 `app/rag/` 继续负责产生 Agent 输出，不感知人工评审；
- `app/security/` 扩展 Workspace 权限和审计事件；
- `app/observability/` 增加 run/review/report 指标；
- 现有 API 路径保持兼容，新资源放在 `/api/v1/evaluation-*`。

## 7. 数据迁移策略

1. 新建 V1.1 Alembic migration，不修改 `0001_v1`；
2. 新表先无业务数据，提供显式 demo seed 命令；
3. 现有 JSON 评测集通过 importer 生成 EvaluationDatasetVersion；
4. 对导入内容计算规范化 SHA-256，重复导入返回原版本；
5. 现有结果 JSON 仅作为历史文件，不伪造数据库运行记录；
6. 验证升级、当前 revision、空库 seed 和重复 seed 幂等。

