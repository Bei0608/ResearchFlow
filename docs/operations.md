# ResearchFlow V1.1 运维手册

## 本地启动与健康检查

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
docker compose exec -T api python -m alembic current
```

预期依赖容器健康，readiness 的 `postgres/milvus/redis` 均为 `true`，迁移为
`0007_v11 (head)`。显式进程环境变量优先于 `.env`；`.env` 只补充未设置项，避免
CI、隔离测试或部署注入的 `POSTGRES_URI` 被本地文件覆盖。

常用排障：

```powershell
docker compose logs api mcp postgres redis --tail 100
docker compose exec -T redis redis-cli ping
docker compose exec -T api python -m alembic current
docker compose config --quiet
```

## 空库迁移与完整演示初始化

首次部署先迁移，再运行幂等初始化：

```powershell
python -m alembic upgrade head
$env:RESEARCHFLOW_DEMO_PASSWORD = "请使用至少8位的临时演示密码"
python -m scripts.bootstrap_demo_platform --username researchflow-demo
Remove-Item Env:RESEARCHFLOW_DEMO_PASSWORD
```

输出包含Workspace、应用版本、评测集、量表、Baseline/Candidate Run、评审任务、
Gate和报告ID，不输出密码。再次执行应复用相同业务对象，数据库仍只有2个demo Run、
1个任务、1个Policy和1次Gate；报告已有JSON/HTML时不重复生成。初始化使用项目内
预生成程序结果，`environment=demo`，不会调用模型，也不会写入人工评分。

CI以临时PostgreSQL服务执行全部migration并连续初始化两次，验证空库与幂等路径。
生产环境可不创建demo账号；该命令是验收工具，不是服务启动的强制依赖。

## 数据库迁移

```powershell
python -m alembic revision -m "describe_change"
python -m alembic upgrade head
python -m alembic current
```

生成迁移后必须人工审查。生产升级前执行 `pg_dump`，并在同版本副本验证升级。
不要让多个容器并发迁移；生产Compose仅由API启动命令执行迁移。降级可能破坏数据，
仅在已确认影响并有备份时执行。

## 测试与质量门禁

```powershell
$env:PYTHONUTF8='1'
python -m compileall -q app scripts tests
python -m pytest -q
python -m scripts.evaluate_retrieval
python -m scripts.evaluate_answers
python -m scripts.evaluate_gate --fixture evaluations/demo/gate_check.json
```

Gate退出码为 `0=passed`、`2=failed`、`3=incomplete`、`1=运行错误`。确定性fixture
只验证规则引擎和CI接线，不冒充在线模型评测。检索/答案脚本才用于真实论文集质量
回归，输出写入被忽略的 `evaluations/results/`。

## 报告与备份

- PostgreSQL：定时 `pg_dump`，恢复演练同时核对Alembic revision；
- `reports/generated`：保存报告产物并与数据库Report记录一起备份，使用SHA-256核验；
- Milvus：按实际部署备份collection及对象存储；
- Redis：缓存可重建；AOF只在业务需要降低限流窗口丢失时启用；
- 原始PDF：独立版本化和授权管理，仓库默认不提交。

报告由服务端生成受控文件名，下载时再次检查Workspace权限。数据库事实是统计来源，
报告是带哈希的派生产物；报告丢失后可重建，不能反向用HTML覆盖事实表。

## 生产部署与监控

```powershell
docker compose --env-file .env -f deploy/compose.prod.yaml config
docker compose --env-file .env -f deploy/compose.prod.yaml up -d --build
```

Caddy作为唯一公网入口并提供HTTPS；PostgreSQL、Redis、Milvus、API和MCP不直接暴露
公网。生产密钥由平台Secret/Vault/KMS注入。建议告警readiness、5xx、P95时延、
Redis fallback、缓存错误和质量门禁下降。JSON日志用`request_id`关联请求；生产审计
应异步导出到只追加存储或SIEM。

## 发布清单

1. 确认需求表全部MUST为VERIFIED，未把demo指标描述成真实人工结论；
2. 执行全量测试、真实检索/答案评测、确定性Gate和空库初始化；
3. 检查migration为`0007_v11 (head)`、Compose健康、JSON/HTML报告可下载；
4. 更新README、CHANGELOG、架构、项目状态和简历证据；
5. 由用户审查当前未提交文件，再决定commit、`v1.1.0` Tag和push；
6. Tag触发Release Workflow，重新测试并执行Gate后发布GHCR镜像；
7. 生产部署固定Tag或Digest，不依赖浮动`latest`，并保留回滚所需数据库备份。

