# V1.1 代码学习指南

不要按文件名从头背代码，按一次请求经过的路径阅读。建议每完成一组，就用断点、
日志或测试回答后面的检查题。

## 1. 从严格论文问答主链开始

阅读顺序：

1. `app/workflows/research_workflow.py`：节点、状态和条件边；
2. `app/rag/retriever.py`：Embedding、Milvus、MMR 与缓存；
3. `app/rag/indexer.py`：稳定 ID、增量写入和缓存版本；
4. `scripts/evaluate_retrieval.py`、`scripts/evaluate_answers.py`：什么叫“效果没有退化”。

检查题：相似度足够高为什么仍可能拒答？新增论文后旧缓存为何不会继续命中？

## 2. 再看 Agent、记忆和会话隔离

阅读 `app/agent/`、`app/tools/`、`app/memory/`、`app/middleware/`。重点画出：

```text
user_id -> memory namespace
thread_id -> checkpoint
thread_id -> PostgreSQL owner
```

检查题：同一个用户换 thread 后什么还在？另一个用户猜到 thread ID 后为何读不到？

## 3. 跟一次 API 登录生命周期

阅读：

1. `app/api/routers/auth.py`；
2. `app/security/jwt_tokens.py`；
3. `app/security/repository.py`；
4. `app/security/audit.py`；
5. `tests/unit/test_api.py` 和 `tests/unit/test_security.py`。

检查题：Access 与 Refresh Token 为什么不能互换？改密后为什么旧 Refresh 失效，
而已签发的短期 Access Token 不会立刻消失？

## 4. 学 Redis 的两个不同用途

阅读 `app/api/rate_limit.py` 和 `app/cache/redis_cache.py`。前者用 Lua 保证多个 API
实例原子共享计数；后者用 cache-aside 降低 Embedding/Milvus 调用。两者故障时都
会降级，但业务含义不同。

检查题：限流 Redis 故障时选择 fail-open 有什么风险？为什么缓存失效用版本号，
不直接 `FLUSHDB`？

## 5. 最后看 MCP 与部署

阅读 `app/mcp_server/server.py`、`app/mcp_server/auth.py`、
`scripts/mcp_client_demo.py`、`compose.yaml`、`deploy/compose.prod.yaml` 和 Caddyfile。

检查题：普通 API Token 为什么会被 MCP 拒绝？stdio 为什么不走 HTTP Bearer？
本项目哪里符合资源服务器职责，哪里还不是完整 OAuth 授权服务器？

## 6. 用测试验证理解

先运行单个测试并修改一个断言观察失败，再恢复：

```powershell
python -m pytest tests/unit/test_retriever.py -v
python -m pytest tests/unit/test_cache_and_rate_limit.py -v
python -m pytest tests/unit/test_security.py -v
python -m pytest tests/unit/test_api.py -v
```

最终自己完成三个小练习：增加一个审计事件类型；增加一个缓存指标断言；给 MCP
增加一个只读的“按文件名筛选论文”工具及测试。做到这一步，项目才真正变成你的。

## 7. 沿评测事实链学习V1.1

按业务发生顺序阅读，不要先背数据库表：

1. `app/applications/`、`app/evaluation/catalog*`：为什么发布版本不可原地修改；
2. `app/evaluation/runs*`：Runner如何逐案例保存成功和失败；
3. `app/evaluation/reviews*`：草稿、提交、纠错、乐观锁和幂等键；
4. `app/evaluation/reporting*`：为何旧修订和草稿不进入正式均值；
5. `app/evaluation/gates*`：FAILED与INCOMPLETE有什么本质区别；
6. `scripts/bootstrap_demo_platform.py`：如何从空数据库幂等建立完整演示。

建议亲手做三次实验：删除一个必填分数观察422；用旧`expected_revision`制造409；
把Gate阈值提高观察退出码2。然后画出`CaseResult -> ProgramMetric`和
`Review -> Revision -> HumanScore`两条事实链，解释它们为什么最后才在报告中并列。
