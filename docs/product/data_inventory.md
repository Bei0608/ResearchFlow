# P1 数据盘点与边界

盘点日期：2026-11-06。

## 现有真实开发数据

| 位置 | 内容 | Git状态/边界 | 用途 |
|---|---|---|---|
| `data/papers/*.pdf` | 8篇具身智能论文 | 被忽略，不随项目提交；可能受版权约束 | 真实RAG集成评测 |
| Milvus `research_papers` | 论文Chunk和1024维向量 | 外部Docker运行数据 | 真实检索 |
| PostgreSQL | 用户、Token、thread、checkpoint、记忆、审计 | 外部Docker运行数据 | V1.0业务状态 |
| Redis | 缓存、索引版本、限流窗口 | 可重建运行数据 | 性能与共享限流 |
| `evaluations/datasets/*.json` | 论文检索与答案评测集 | 可提交，但依赖上述论文 | V1.0程序评测 |
| `evaluations/results/*.json` | 本地生成的程序评测报告 | 被忽略 | 临时结果 |

## P1 新增的可分发演示数据

| 位置 | 内容 | 标签 |
|---|---|---|
| `data/demo/knowledge/*.md` | 两篇原创合成知识资料 | `environment=demo`（由清单声明） |
| `data/demo/manifest.json` | 文件边界、来源和隐私声明 | 无私有数据、无人工评分 |
| `evaluations/demo/evaluation_dataset.json` | 4个可回答/拒答案例 | `environment=demo` |
| `evaluations/demo/agent_run.json` | 预生成候选回答、证据、耗时和Token | `pre_generated_no_external_model_required` |
| `evaluations/demo/program_metrics.json` | 路由、关键词、引用程序指标 | `source=program` |
| `evaluations/demo/rubric.json` | 三维人工量表定义 | `human_scores=[]` |
| `evaluations/baselines/v1_compatibility.json` | V1.0真实程序验证快照 | `human_evaluation=null` |

## 明确的数据边界

- `data/demo` 和 `evaluations/demo` 是业务演示数据，可用于后续人工评审；
- `tests/fixtures` 仅用于构造边界和错误场景，不能出现在业务统计中；
- `runtime/demo` 是安装命令生成的可删除命名空间，被 Git 忽略；
- 演示包不预填 `source=human` 的记录；人工评分只能由 P5 的真实评审操作产生；
- 演示运行不证明模型质量，只证明业务流程可以在无外部依赖时复现。

## 安装与重置安全性

安装工具先验证清单、环境标签、案例集合、运行ID、证据来源和评分来源，再复制文件。
安装标记保存每个受管文件的哈希。重复安装相同数据返回 `unchanged`。

重置只读取有效 demo 标记，逐个删除 `managed_files` 中的相对路径；不会递归删除
目标目录，不会删除未受管文件，并拒绝文件系统根目录和项目根目录。
