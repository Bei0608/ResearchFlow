# 项目状态

## 当前快照

- 日期：2026-11-06
- 当前版本：ResearchFlow V1.1 评测与人工评审中心
- 目标版本：V1.1 评测与人工评审中心
- 当前阶段：P8 容器验收、文档与发布
- 阶段状态：DONE
- 下一阶段：观察GitHub CI/Release；增强项保持DEFERRED

## 2026-11-05 / P0 / DONE

### 完成内容

- 检查现有模块、迁移、评测脚本、数据集、Baseline 和 Git 状态；
- 建立长期提示词、原题来源、需求追踪、歧义、评审流程和技术方案；
- 建立数据模型、模块边界、P0–P8实施计划；
- 建立决策、项目状态、真实对话和读者测试文档。

### 实际验证

- 使用 `rg --files` 盘点项目；
- 检查现有 migration、requirements、评测数据和脚本；
- 11 个要求的治理文档存在；
- 本地 Markdown 链接检查通过；
- 典型读者问题可发现性检查记录在 `reader_test.md`。

### 遗留问题

- 没有独立原题全文；
- 当时 D-004 至 D-008 尚待用户确认；
- 没有可分发演示数据和人工评审模型。

### 下一步

用户确认建议后进入 P1。

## 2026-11-06 / P1 / DONE

### 完成内容

- 用户确认 D-004 至 D-008 及 A-02 至 A-13 的建议解释；
- 盘点真实 PDF、Milvus/PostgreSQL/Redis、评测集和生成结果的数据边界；
- 新增两篇原创合成知识资料、4个评测案例、预生成 Agent 运行和三维人工量表；
- 程序指标明确标记 `source=program`，所有 demo 文件明确标记 `environment=demo`；
- 演示包不包含私有数据，不预填任何人工评分；
- 实现 `verify/install/reset` CLI 和幂等安装标记；
- Reset 只删除标记内的受管文件，保留未受管文件，并拒绝根目录目标；
- Docker 镜像只复制原创 demo 和 demo 评测文件，不复制真实论文；
- 冻结 V1.0 的程序测试、检索和答案质量兼容基线；
- README 增加无密钥演示数据命令。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| `python -m pytest tests/unit/test_demo_data.py -q` | 6 passed |
| 无模型密钥 `manage_demo_data verify` | 8个受管文件、4个案例、无人工评分 |
| 首次/重复安装 | `installed` 后返回 `unchanged` |
| 安全重置 | 删除8个受管文件，运行命名空间清理完成 |
| 未受管文件保护 | 单元测试确认 `keep-me.txt` 保留 |
| Docker Build | `researchflow:p1-demo` 构建成功 |
| Docker 内无密钥循环 | verify/install/unchanged/reset 全部成功 |
| Demo bundle SHA-256 | `198407ce96582081641c37f72c54941102282c1c80a1ef72c22f4df9392167ce` |
| `python -m compileall -q app scripts tests` | 通过 |
| `python -m pytest -q` | 91 passed in 21.07s |
| API readiness | PostgreSQL/Milvus/Redis 均为 true |
| 检索质量门禁 | Hit@5=1.000、Recall@5=1.000、MRR=0.972，通过 |
| 答案质量门禁 | 总分=0.988333、路由=1.000、关键词=0.966667，通过 |

答案评测第一次运行因 Docker Desktop 重启后宿主 PostgreSQL 端口未恢复而出现
`PoolTimeout`。重建 PostgreSQL/API/MCP 容器网络映射后，`scripts.test_postgres`
成功，答案评测重新运行并通过。该失败属于运行环境端口映射，不是质量指标回退。

### 验收结论

P1 验收通过：克隆后的演示包不依赖模型 API Key、版权 PDF、Milvus 或数据库即可
验证、安装和重置；Docker 镜像内同样可复现。人工和程序评分边界已在数据、校验、
测试及文档层明确。MUST-08/09 仅完成数据基础，完整业务验收仍依赖 P2–P6。

### 遗留问题

1. 原题全文仍未提供；
2. Git 文件仍未提交，尚无可引用 commit SHA；
3. Demo 尚未写入业务数据库，因为 Workspace/评测表属于 P2–P4；
4. 人工评分仍为空，这是为了不伪造评审数据；真实评分流程属于 P5；
5. 双人盲评、异步任务、PDF报告和数据血缘仍是可选增强。

### 下一步

1. 进入 P2，设计 Workspace/Application/AgentVersion migration；
2. 实现个人默认 Workspace 和作用域 Repository；
3. 实现 Agent 应用与不可变版本快照；
4. 增加跨 Workspace 越权测试和审计事件；
5. P2 验收后再进入评测集与量表版本开发。

## 2026-11-06 / P2 / DONE

### 完成内容

- 新增 `0002_v11` migration：Workspace、成员、Application、AgentVersion及约束；
- 新用户注册时自动创建个人Workspace，旧用户访问时幂等补建；
- 新增Workspace列表、应用创建/列表、版本创建/列表/修改/发布API；
- 配置快照递归拒绝API Key、密码、Token、Secret、Authorization和私钥字段；
- 配置快照使用JSON深拷贝，避免请求对象后续修改污染已保存版本；
- 发布版本不可变，继续修改返回409；
- 仓储层查询同时校验user、workspace和role，owner才可写；
- 应用/版本创建、修改、发布写入用户审计事件；
- README、架构、需求、决策、对话和CHANGELOG同步更新。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P2 API与配置专项测试 | 26 passed |
| 全量测试 | 102 passed in 16.36s |
| Python compileall | 通过 |
| Alembic offline SQL | 通过 |
| PostgreSQL upgrade | `0001_v1 -> 0002_v11` 成功 |
| Alembic current | `0002_v11 (head)` |
| Docker API/MCP Build | 成功 |
| 新用户个人Workspace | owner和other各1个，ID不同 |
| Agent版本发布 | `draft -> published` 成功 |
| 敏感配置 | 422，响应不回显敏感值 |
| 发布后修改 | 409 |
| 跨Workspace读取 | 404 |
| 平台审计 | application/agent_version事件写入成功 |
| API readiness | PostgreSQL/Milvus/Redis均为true |
| 检索质量 | Hit@5=1.000、Recall@5=1.000、MRR=0.972222 |
| 答案质量 | 总分=0.988333、路由=1.000、关键词=0.966667 |

### 验收结论

P2 验收通过：两个用户的Workspace和应用资源隔离；Agent配置快照不接受原始密钥；
草稿可修改、发布版本不可修改；真实PostgreSQL迁移、容器API和审计均已验证。
MUST-12 标记 VERIFIED；MUST-16 完成Workspace/Application部分，任务、评分和报告
隔离将在P3–P6继续验证。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交，AgentVersion暂时只能保存调用方提供的commit字符串；
3. P2不提供Workspace成员管理页面/API，reviewer成员将在评审任务阶段接入；
4. 注册和默认Workspace创建不是单事务，访问时幂等补建作为恢复路径；
5. 评测集、量表、运行、评分、统计和报告尚未实现。

### 下一步

1. 进入P3，新增EvaluationDataset/Version/Case和Rubric/Version/Criterion；
2. 实现草稿编辑、发布前校验和发布后不可变；
3. 把P1 JSON演示数据通过幂等Importer导入P3模型；
4. 增加content hash、重复导入、版本边界和跨Workspace测试；
5. P3验收后进入程序评测运行持久化。

## 2026-11-06 / P3 / DONE

### 完成内容

- 新增 `0003_v11` migration，建立 Dataset/Version/Case 与
  Rubric/Version/Criterion 六张业务表；
- Dataset 和 Rubric 在 Workspace 内名称唯一，Version 在父资源内版本号唯一；
- 草稿案例与评分准则支持新增、查询、修改和删除；
- 发布前校验评测集非空、案例输入/期望非空、量表说明与准则完整、权重和为1；
- 对规范化内容计算 SHA-256，数据库通过唯一索引防止相同内容重复发布；
- 发布后的案例和评分准则不可修改或删除，API返回409；
- 新增评测目录 REST API、OpenAPI定义和创建/发布审计事件；
- 新增 JSON importer 和CLI，可导入P1演示Dataset/Rubric；重复导入返回已有版本；
- Repository层继续强制Workspace成员读取、owner写入，越权统一返回404；
- 新增内存仓库、API生命周期、哈希稳定性、校验和幂等导入测试。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P3 API与Importer专项测试 | 24 passed |
| 全量测试 | 110 passed in 20.76s |
| Python compileall | 通过 |
| Alembic offline SQL | 通过 |
| PostgreSQL upgrade | `0002_v11 -> 0003_v11` 成功 |
| Alembic current | `0003_v11 (head)` |
| Docker API/MCP Build | 成功 |
| API readiness | PostgreSQL/Milvus/Redis均为true |
| Dataset发布 | `draft -> published`，生成64位SHA-256 |
| 发布后修改案例 | 409 |
| 跨Workspace读写 | 404，攻击后owner案例数仍为0 |
| Dataset重复导入 | 两次返回相同dataset_version_id |
| Rubric重复导入 | 两次返回相同rubric_version_id |
| PostgreSQL发布版本记录 | Dataset 2条（1条API验收+1条导入），Rubric 1条 |

### 验收结论

P3验收通过：评测集和量表具备明确的草稿编辑、发布校验、发布不可变和内容寻址
边界；P1演示JSON能够幂等写入真实PostgreSQL。MUST-13标记VERIFIED，MUST-16
完成评测目录部分，运行、任务、评分和报告隔离将在P4–P6继续验证。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交，版本证据尚无真实commit；
3. importer在成功路径上幂等，但导入进程中途异常可能留下草稿，P4事务编排时补偿；
4. `archived` 状态已预留数据库约束，本阶段不提供归档API；
5. 程序评测运行、人工评分、统计和报告尚未实现。

### 下一步

1. 进入P4，新增EvaluationRun、CaseResult和ProgramMetric；
2. 把现有检索与答案评测抽象为统一Evaluator；
3. CLI与服务层复用同一同步Runner并保存部分失败结果；
4. 运行引用已发布的AgentVersion和DatasetVersion；
5. 使用真实现有数据核对数据库聚合值与旧JSON报告。

## 2026-11-06 / P4 / DONE

### 完成内容

- 新增 `0004_v11` migration：EvaluationRun、CaseResult和ProgramMetric；
- Run引用同一Workspace下已发布的AgentVersion和DatasetVersion；
- 状态机限定 `created -> running -> ready_for_review/failed`，结束后不能重新启动；
- 统一Runner逐案例执行并立即持久化，单案例失败不删除已成功的结果和指标；
- CaseResult保存输出、证据、trace、耗时、token usage和错误；
- ProgramMetric强制 `source=program`，保存evaluator key/version、metric key/value和明细；
- 抽取AnswerQualityEvaluator和RetrievalQualityEvaluator，现有两个CLI改用统一Runner；
- 旧CLI保留原命令、JSON报告结构、门禁阈值与退出码；
- 新增无外部模型demo运行CLI，明确标记pre-generated fixture，不伪装为现场模型运行；
- 新增运行创建/列表/详情API，配置快照继续拒绝敏感字段；
- 新增完整运行、部分失败、状态机、指标来源和用户隔离测试。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P4 Runner与API专项测试 | 29 passed |
| 全量测试 | 117 passed in 17.39s |
| Python compileall | 通过 |
| Alembic offline SQL | 通过 |
| PostgreSQL upgrade | `0003_v11 -> 0004_v11` 成功 |
| Alembic current | `0004_v11 (head)` |
| Docker API/MCP Build | 成功 |
| API readiness | PostgreSQL/Milvus/Redis均为true |
| 完整demo运行 | ready_for_review；4 CaseResult；12 ProgramMetric |
| demo程序指标 | route=1.000；keyword=0.875；citation=1.000，与P1 fixture一致 |
| 部分失败运行 | failed；3成功+1失败；保留9个已完成指标；error已保存 |
| 结束后重新启动 | Repository拒绝，返回None |
| 检索CLI实跑 | Hit@5=1.000；Recall@5=1.000；MRR=0.972222，与旧基线一致 |
| 答案CLI实跑 | 总分=0.970833；路由=1.000；关键词=0.916667；门禁通过 |

### 验收结论

P4验收通过：程序运行事实、逐案例输出和程序指标已经进入真实PostgreSQL，完整和
部分失败路径都可追溯；现有CLI共享Runner且继续通过门禁。MUST-14标记VERIFIED，
MUST-09完成程序评分数据库/API部分。

答案在线实跑未伪称与旧基线完全一致：路由保持1.0，但受当前模型输出变化影响，
综合分由0.988333降至0.970833，关键词召回由0.966667降至0.916667；仍高于当前
0.90门禁。P7将对Baseline差异建立显式Gate，而不是依赖人工比对。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交，Run中的git_commit只能由调用方提供；
3. demo静态指标用于验证持久化，明确标记fixture，不代表重新执行模型；
4. 当前Runner同步执行，符合V1.1决定；长任务异步化仍为DEFERRED；
5. 人工评审任务、评分修订、统计和报告尚未实现。

### 下一步

1. 进入P5，新增ReviewTask、Assignment、Review、Revision和HumanScore；
2. 实现待评审任务、草稿保存、重新打开和乐观锁；
3. 实现必填准则校验、正式提交和已提交评分修订；
4. 建立Jinja2最小评审页面与原生JavaScript交互；
5. 验证人工分与ProgramMetric始终分表、分来源展示。

## 2026-11-06 / P5 / DONE

### 完成内容

- 新增 `0005_v11` migration：ReviewTask、Assignment、Review、Revision、HumanScore；
- Workspace owner可按用户名添加reviewer成员，owner/reviewer写权限分离；
- 只有READY_FOR_REVIEW运行、已发布量表和至少一个成功案例才能创建评审任务；
- 创建任务时为成功CaseResult建立Review，支持“我的任务”、任务进度和案例详情；
- 案例页/API同时展示输入、期望、Agent输出、证据、程序指标和人工量表；
- 草稿允许部分评分，每次保存创建新Revision并保留旧记录；
- `expected_revision`实现乐观锁，过期写入返回409；
- `Idempotency-Key`重复请求返回原Revision，不产生重复保存；
- 正式提交校验所有required准则、准则归属及分数范围，缺项返回422；
- 全部案例提交后Assignment和Task自动变为completed；
- 已提交评审不能直接覆盖，必须创建带原因的纠错草稿，再次提交后旧版本superseded；
- 人工分进入独立HumanScore表，不与ProgramMetric混合；
- 新增Jinja2+原生JavaScript评审页 `/review`，不引入独立前端；
- 页面使用textContent展示业务内容，避免把答案/评论作为HTML执行；
- 保存、提交、纠错、任务创建和成员添加均写入审计事件。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P5 API专项测试 | 27 passed |
| 全量测试 | 120 passed in 23.08s |
| Python compileall | 通过 |
| Alembic offline SQL | 通过 |
| PostgreSQL upgrade | `0004_v11 -> 0005_v11` 成功 |
| Alembic current | `0005_v11 (head)` |
| 真实任务案例数 | 4 |
| 草稿幂等重试 | 相同key返回同一revision_id |
| 并发冲突 | 过期expected_revision返回409 |
| 首例修订链 | 4条：3 superseded + 1 submitted |
| 完整任务 | 4/4 submitted；Task/Assignment均completed |
| 数据库事实 | 7 ReviewRevision；19 HumanScore |
| 独立reviewer | 成员role=reviewer，可见任务并可保存 |
| owner代替reviewer写评分 | 404 |
| 浏览器页面 | 登录、任务、案例、指标、量表正常；窄屏单列 |
| 浏览器控制台 | 0 warning/error |
| API readiness | PostgreSQL/Milvus/Redis均为true |

### 验收结论

P5验收通过：评审人能够打开任务和案例、保存并恢复部分草稿、修改草稿、提交完整
评分，并通过新Revision纠错已提交结果；历史未被覆盖，多用户与角色写权限经过真实
PostgreSQL和浏览器验证。MUST-01至MUST-05标记VERIFIED，MUST-09完成事实表和
API分离部分，统计与报告展示留待P6。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交；
3. 页面是最小评审工作台，没有独立前端工程、分页和复杂筛选；
4. V1.1仅支持每任务一位评审人，双盲与仲裁保持DEFERRED；
5. 当前纠错提交会把旧有效提交标为superseded，P6统计必须只取最新submitted；
6. 统计、JSON/HTML报告和Baseline Gate尚未实现。

### 下一步

1. 进入P6，分别聚合program与human指标；
2. 人工统计只读取每个Review最新submitted Revision，草稿不进入均值；
3. 计算sample_count、missing_count、完成率和失败案例；
4. 生成自动转义的JSON/HTML报告并保存content hash；
5. 用P5真实修订数据核对统计不会重复计算旧提交。

## 2026-11-06 / P6 / DONE

### 完成内容

- 新增`0006_v11`：AggregateMetric可重建投影与Report生成状态/路径/哈希；
- 程序指标按evaluator/version/metric聚合，人工指标按rubric/version/criterion聚合；
- 人工统计只查询`status=submitted`的当前有效修订，draft与superseded不计均值；
- 输出案例数、失败数、样本数、缺失数、评审状态数和完成率；
- 二值程序指标计算通过率；未配置规则的指标显式返回null，不生成隐式总分；
- JSON/HTML报告包含运行身份、配置、版本、分区指标、失败案例和案例追溯；
- Jinja开启自动转义，报告文件名仅由服务生成，下载再次执行owner权限检查；
- 报告失败保留failed记录，可重新生成；生成行为写入审计事件；
- Compose持久挂载`reports/generated`，目录内容默认被Git忽略。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P6/API专项测试 | 32 passed |
| 全量测试 | 125 passed in 24.80s |
| Python compileall | 通过 |
| Alembic offline SQL | 20134 bytes，生成成功 |
| Alembic upgrade/current | `0005_v11 -> 0006_v11`；`0006_v11 (head)` |
| 真实运行案例 | 4 succeeded，0 failed |
| 真实评审进度 | 8总数、4 submitted、1 draft、3 pending，完成率0.5 |
| 修订排除核对 | DB有3 superseded；每个人工维度sample_count仍为4 |
| 聚合结果 | 3 program + 3 human，命名空间和source分离 |
| 报告生成 | JSON/HTML均completed，SHA-256长度64 |
| HTML下载 | 容器HTTP 200，13817 bytes |
| 跨用户隔离 | 另一真实用户读取运行统计返回404 |
| 浏览器报告 | 494px窄屏无横向溢出；案例追溯可展开；0 warning/error |
| API readiness | PostgreSQL/Milvus/Redis均为true |

### 验收结论

P6验收通过。报告可从汇总追溯到单个案例；程序指标与人工指标在数据库、API和
HTML/JSON中均分区展示；草稿和旧修订不进入正式均值；生成失败不改变评审事实且
允许重试。MUST-06、07、08、09和16标记VERIFIED。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交；
3. 非二值指标尚无通过阈值，P6显式显示未配置，留给P7 Gate Policy；
4. 统计在GET时同步重算并替换投影，当前规模可接受；
5. Baseline、Gate结论和CI门禁尚未接入报告。

### 下一步

1. 进入P7，建立Baseline、GatePolicy和GateEvaluation；
2. 支持绝对阈值与相对Baseline回退规则；
3. 输出PASSED/FAILED/INCOMPLETE及具体失败原因；
4. 将Gate结果写入报告并提供CI退出码；
5. 使用demo数据验证门禁可重复且指标下降时失败。

## 2026-11-06 / P7 / DONE

### 完成内容

- 新增`0007_v11`：Baseline、GatePolicy和GateEvaluation；
- 数据库部分唯一索引保证每个Application最多一个active baseline；
- Baseline运行必须属于同一Application且为ready_for_review；
- Gate Policy支持草稿创建、发布，发布后没有原地修改入口；
- 支持`absolute_min`绝对下限和`max_regression`最大允许回退；
- 规则通过source/namespace/metric精确匹配程序或人工指标；
- 无Baseline、缺指标、样本缺失和人工未完成均产生INCOMPLETE；
- 输出逐规则候选值、基线值、限制、状态和可读原因；
- 同一Candidate/Baseline/Policy允许重新计算并保留每次Evaluation；
- 最新GateEvaluation进入JSON/HTML报告，不生成隐式综合分；
- 新增数据库/离线CLI，退出码0=passed、2=failed、3=incomplete；
- GitHub Actions加入确定性demo gate，夹具明确标记为程序测试数据。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| P7/报告/API专项测试 | 38 passed |
| 全量测试 | 131 passed in 23.47s |
| Python compileall | 通过 |
| Alembic offline SQL | 22918 bytes，生成成功 |
| Alembic upgrade/current | `0006_v11 -> 0007_v11`；`0007_v11 (head)` |
| 真实活动Baseline | 同应用ready_for_review运行激活成功 |
| 重复门禁 | 同组合连续两次passed，results完全一致 |
| 规则结果 | passed策略2/2规则通过；故意高阈值为failed |
| 人工未完成 | 人工规则返回incomplete，不按0分处理 |
| CLI退出码 | passed=0、failed=2、incomplete=3 |
| 报告 | Gate后的JSON/HTML均completed，SHA-256长度64 |
| 离线CI夹具 | expected=passed，实际passed，退出码0 |
| 浏览器报告 | 发现并修复长run_id窄屏溢出；494px复测body宽479px；0 warning/error |

### 验收结论

P7验收通过：Candidate能与每应用唯一活动Baseline按已发布Policy重复比较，绝对阈值、
相对回退和不完整数据都有明确、可复核结论；Gate写入报告，CLI和CI获得稳定退出码。
MUST-15标记VERIFIED。

### 遗留问题

1. 原题全文仍未提供；
2. 项目文件仍未Git提交；
3. V1.1规则仅支持“越高越好”的下限与回退，不含表达式语言和复杂组合；
4. demo CI门禁验证规则引擎与接线，不冒充在线模型重新评测；
5. P8尚需从空数据库完成容器级全流程验收和最终发布清点。

### 下一步

1. 进入P8，从空数据库执行migration、demo seed和完整验收；
2. 运行全部单元、集成、API、浏览器和兼容性验证；
3. 按8–12分钟评审脚本完成端到端演示；
4. 完成需求证据、运维、简历和发布文档；
5. 用户确认后再提交、打Tag和推送。

## 2026-11-06 / P8 / DONE

### 本阶段目标

- 使用隔离空数据库验证从零迁移与演示数据边界，不破坏现有验收数据；
- 完成单元、集成、容器、API、页面和V1.0兼容性回归；
- 按评审人流程核验评审、统计、报告和Gate完整链路；
- 完成需求证据、运维、项目展示和简历材料，清点发布前遗留项。

### 完成内容

- 新增完整无模型`bootstrap_demo_platform`，幂等建立用户、Workspace、应用版本、
  评测目录、Baseline/Candidate Run、评审任务、Gate和JSON/HTML报告；
- 使用隔离空PostgreSQL从零迁移并连续初始化两次，未删除或重置主验收数据库；
- 修复`.env`覆盖显式环境变量导致隔离进程误连主库的问题，并增加回归测试；
- 修复Windows GBK终端下检索和记忆测试输出Unicode字符失败的问题；
- 完成隔离API、浏览器评审、跨用户隔离及V1.0安全/MCP/RAG/记忆兼容性回归；
- CI增加PostgreSQL空库迁移和双次bootstrap，Release增加确定性Gate；
- 更新README、架构、运维、学习指南、简历证据、CHANGELOG和P8验收记录；
- 所有MUST需求更新为VERIFIED，未把demo程序指标或自动化测试描述成人工结论。

### 实际验证

| 验证 | 真实结果 |
|---|---|
| Python compileall | 通过 |
| 全量测试 | 132 passed in 21.45s |
| 隔离空库迁移 | `0001_v1 -> 0007_v11 (head)` |
| bootstrap幂等 | 两次status=ready，用户/应用/数据/运行/任务ID一致 |
| 隔离库最终计数 | users=1、apps=1、runs=2、tasks=1、policies=1、gates=1 |
| API评审闭环 | 4/4 submitted、completion=1.0、human missing=0、Gate passed |
| 报告 | JSON/HTML均completed |
| 跨用户隔离 | 读取他人评审资源返回404 |
| 浏览器 | 桌面/494px无全局溢出，控制台0 warning/error |
| 检索兼容性 | Hit@5=1.000、Recall@5=1.000、MRR=0.972 |
| 答案兼容性 | 综合0.988333、路由1.000、关键词0.966667 |
| MCP/记忆/安全 | 真实检索、Store写读删、Refresh轮换撤销通过 |
| Compose重建 | API/PostgreSQL/Redis healthy，MCP running |
| Readiness | postgres/milvus/redis均为true |
| Alembic current | `0007_v11 (head)` |
| 文本质量检查 | 26个Markdown链接有效；无尾随空格/冲突标记 |

第一次最终pytest命令误用了未安装pytest的base Python，随后使用项目的
`researchflow`环境重跑并得到上述132项通过；不把前者记为代码失败。第一次隔离
数据库尝试因配置覆盖误连主库，不计入有效验收，修复后删除并重建临时容器重验。

### 验收结论

P8及P0–P8完整必做范围通过。项目可从空数据库复现完整演示，评审、保存、修改、
统计、报告与Gate形成闭环；程序/人工事实保持分离。详细证据见`p8_acceptance.md`。

### 遗留问题

1. 原题全文仍未提供，不能声称满足未知题目之外的要求；
2. 工作树文件仍未提交，暂无可引用commit SHA，符合A-14和“不自动发布”原则；
3. 主数据库保留P1–P8验收数据及一次误连时创建的明确测试账号`p8-other`；
4. 双评审仲裁、异步Worker、数据血缘、LLM-as-Judge和PDF报告保持DEFERRED；
5. GitHub Actions新增任务已做语法与本地等价路径检查，远端实际运行需推送后确认。

### 下一步

1. 用户已于2026-11-08确认发布；
2. 创建release commit和`v1.1.0` Tag并推送GitHub；
3. 观察远端CI/GHCR Release结果；
4. 后续按求职JD决定学习复盘或进入E1–E3，不默认扩大范围。

## 阶段更新模板

每次追加真实阶段快照，不覆盖历史验证：

```text
## YYYY-MM-DD / Px / 状态
### 完成内容
### 实际验证（命令、结果、证据路径）
### 遗留问题
### 下一步
```
