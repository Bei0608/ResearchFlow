# P8 最终验收记录

## 验收范围

本记录覆盖空库可复现性、完整评审业务流、V1.0兼容能力、自动化测试、容器和文档。
临时数据库与demo程序结果均明确标记为验收数据，不把它们写成真实人工结论。

## 隔离空库与幂等性

- 使用无持久卷的临时PostgreSQL容器，映射宿主端口55432；
- 从零执行`0001_v1`至`0007_v11 (head)`；
- 连续两次执行`bootstrap_demo_platform`；
- 两次返回相同user、application、dataset、baseline/candidate run和task ID；
- 最终计数：1 user、1 application、2 runs、1 task、1 policy、1 gate；
- Gate为passed，JSON/HTML报告均completed；验收后精确删除临时容器。

第一次隔离尝试发现`.env`覆盖显式`POSTGRES_URI`并误连主库，因此不计入有效验收。
修复所有`load_dotenv(override=True)`、加入回归测试并重建临时数据库后重新完成以上结果。

## API与浏览器完整流程

在隔离数据库/API上验证：登录成功、任务1个、案例4个；草稿revision=1；相同幂等键
返回同一revision；纠错后重新提交；最终4/4 submitted、completion=1.0、人工缺失数0；
Gate passed；JSON/HTML报告completed；另一用户读取资源返回404。

浏览器从`/review`登录后查看输入、输出、证据、“程序指标（仅供参考）”和人工量表，
完成提交及纠错。1280px和494px视口均无全局横向溢出，控制台无warning/error。

## V1.0兼容性

- Access登录、Refresh轮换、Logout撤销及撤销Token重放401；
- MCP列出3个工具并返回真实RT-2证据；
- PostgreSQL Store完成测试记忆写入、读取、搜索和删除；
- Milvus真实检索返回3条结果；
- 检索评测：Hit@5=1.000、Mean Recall@5=1.000、MRR=0.972；
- 答案评测：10案例、综合分0.988333、路由1.000、关键词0.966667。

## 8–12分钟演示路径

1. 启动Compose并检查readiness、Alembic head；
2. 运行完整bootstrap并展示输出ID和Gate状态；
3. 登录`/review`，解释程序指标与人工量表分区；
4. 保存一例部分草稿，重开确认恢复；
5. 修改并提交，再创建纠错修订，说明历史不覆盖；
6. 完成任务，展示完成率、样本数、缺失数；
7. 打开JSON/HTML报告并追溯到案例；
8. 展示Baseline Gate逐规则原因、CI退出码和跨用户404。

## 结论与边界

P0–P8全部必做闭环完成，MUST-01至MUST-17均有证据。原题全文仍未提供，无法声称
满足未知原题之外的要求；双评审仲裁、异步Worker、数据血缘、LLM-as-Judge和PDF报告
保持DEFERRED。当前工作树尚未提交；commit、`v1.1.0` Tag和push等待用户确认。
