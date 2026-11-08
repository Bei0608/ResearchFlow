# 文档读者测试

## 测试方式

本轮没有调用独立子代理，因此未声称完成“无上下文第三方模型”测试。先进行基于
典型评审问题的可发现性检查；用户后续可把文档索引交给一个全新会话复测。

| 读者问题 | 应从哪里得到答案 | 检查结果 |
|---|---|---|
| 当前哪些是必做、增强和范围外？ | `requirements_traceability.md` | 可回答 |
| 评审人怎样保存、修改并提交评分？ | `reviewer_workflow.md` B/C节 | 可回答 |
| 草稿是否进入正式统计？ | `reviewer_workflow.md`、`ambiguities.md` A-13 | 可回答：不进入分数统计 |
| 人工评分和程序指标如何区分？ | `AGENTS.md`、`data_model_and_modules.md` | 可回答：分事实表和source |
| 没有模型密钥和私有PDF能否演示？ | 根README、`reviewer_workflow.md` | 可回答：幂等bootstrap已实现 |
| 哪些决定仍需用户确认？ | `ambiguities.md`、`decisions.md` | 可回答：A-01原题全文、A-14提交时机 |
| 为什么不用React、Celery和微服务？ | `technical_design.md`关键选择 | 可回答：最小闭环优先及相应代价 |
| 当前真实完成到哪里？ | `project_status.md` | 可回答：P0–P8完成，待用户确认发布 |
| 如何生成和核验报告？ | `reviewer_workflow.md` E节、计划P6 | 可回答 |
| 实施时先做什么、后做什么？ | `implementation_plan.md` | 可回答：P0至P8顺序 |

## 额外一致性检查

- 文档明确区分“已确认”“建议”和“尚未实现”；
- 区分V1.0历史的85项与V1.1当前132项测试，不把自动化测试写成人工评分；
- 未把本地版权 PDF 描述为随仓库发布的数据；
- 未把 Proposed 决策写成用户已确认；
- 所有本地 Markdown 链接已通过路径检查。

## 建议的独立复测提示词

把 `docs/product/README.md` 及其链接文档提供给全新会话，询问：

> 请仅根据这些文档说明 V1.1 的必做范围、人工评审完整流程、程序/人工评分边界、
> 仍待确认的业务决定、当前真实状态和下一阶段验收。如果文档不足，请明确指出。

若回答把 Planned 当成 Done、把 Recommended 当成 Confirmed，说明对应文档仍需加强。

