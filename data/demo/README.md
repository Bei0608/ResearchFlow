# ResearchFlow 演示数据

本目录只包含为项目验收原创的合成资料，不包含真实用户数据、私有数据或论文原文。
内容允许随 ResearchFlow 项目复制、修改和用于演示。

用途：

- 在没有模型 API Key 和本地 PDF 时加载一个可复现的评测运行；
- 验证人工评审的保存、修改、提交、统计和报告流程；
- 明确区分演示业务数据与 `tests/fixtures/` 中的程序测试夹具。

这里不提供预填人工评分。`evaluations/demo/program_metrics.json` 中的分数全部标记
为 `source=program`；未来人工评分只能由评审操作产生。

运行：

```powershell
python -m scripts.manage_demo_data verify
python -m scripts.manage_demo_data install
python -m scripts.manage_demo_data reset
```

默认安装位置是 `runtime/demo`，它是可写生成目录，不提交 Git。源数据仍位于
只读的 `data/demo` 与 `evaluations/demo`。

