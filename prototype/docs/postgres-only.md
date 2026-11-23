# PostgreSQL统一存储

2026-11-23起，后台只使用PostgreSQL。SQLite适配、内存数据库、文件数据库参数、旧库保留账号的重置脚本均已移除；无PostgreSQL URL或schema未初始化时明确报错，不创建替代数据库。

本次按用户授权删除旧账号、会话、档案与球局所在的SQLite文件，不做迁移和备份。已移除原8791服务数据库和一个遗留测试数据库及其WAL/SHM，共6个文件。地图源数据、核心测试夹具和合成训练样本是代码/数据源，保留。

## 本机开发

在仓库根目录使用隔离安装目录；`.runtime/`受Git忽略，含数据库、密码和依赖，不可提交或分享：

```sh
python3 -m pip install --target .runtime/python -r prototype/requirements-development.txt
python3 -B prototype/scripts/local_postgres.py start
python3 -B prototype/scripts/run_local_demo.py --port 8791
python3 -B prototype/scripts/run_local_tests.py
python3 -B prototype/scripts/run_local_tests.py --suite benchmark
```

可用系统PostgreSQL工具替代随开发依赖安装的二进制，通过`CADDIE_PG_BIN`指定目录。本机集群只监听127.0.0.1，独立端口55432；数据在`.runtime/postgres`。Unix socket放在当前用户独占的ASCII临时目录，避免客户端对中文目录连接参数解析异常。数据库目录与私有配置不会因后续服务重启而清空。

- `caddie`：应用库，使用DML-only的`caddie_app`账号，密码随机生成并保存在权限0600的私有配置中。
- `caddie_test`：隔离测试库，所有测试使用随机schema，完成后删除；测试不会向应用库注册账号或记录球局。
- 本机8791服务已改用`run_local_demo.py`，不再传入文件数据库路径。

纯规则与地图策略测试不依赖数据库，依然使用相同的共享TypeScript。涉及存储的API、事件、状态和国际化测试全部使用PostgreSQL，不另设轻量数据库替身。

## 部署已有PostgreSQL

先安装`prototype/requirements-production.txt`，使用schema-owner凭据在环境变量中设置`CADDIE_DATABASE_URL`，显式运行：

```sh
python3 -B prototype/scripts/bootstrap_postgres.py
```

schema来源为`services/api/schema.sql`，版本记录在`schema_meta`。正式请求不会自动建表或修复缺失表。应用运行账号只需schema USAGE和表SELECT/INSERT/UPDATE/DELETE；生产入口仍要求共享Redis及监控令牌，详见[扩容说明](scale-foundation.md)。

本次为新库初始化，不支持从旧数据格式导入。后续真实用户上线后须使用版本化迁移和旧版本续局方案，不能沿用此次直接删除数据的处理方式。

## 已验证与限制

前一轮PostgreSQL/SQLite双路径实现已删除。已验证文件路径配置被拒绝且不会创建文件、缺失表不会在运行期被自动建回、账号隔离、并发去重、离线同步和DML-only权限。

同一宿主机、凤凰山第1洞、30次紧凑HTTP询问：此次PostgreSQL-only p50/p95为4.323/7.951ms，首查询11.061ms，开局276.275ms。前一轮开发SQLite路径参考为4.039/5.395ms，首查询11.000ms；这是不同数据库后端的本机回归对照，不是端到端语音指标。真实网络、手机和ASR/TTS未测。Redis共享限流与远程CI尚未在本机执行。

最终回归：PostgreSQL API共94项，93项通过、1项真实Redis检查待执行；业务142项及客户端104项通过，共339项通过。严格类型、手机入口语法与Python语法检查通过。CI已统一为PostgreSQL+Redis服务；远程CI未在本轮触发。

当前schema版本2，新增公共球场包、账号私有下载参考和独立手机球局索引；升级通过显式bootstrap执行，普通请求不自动迁移。

当前schema3新增原始球局时间、记分口径摘要及账号内字段贡献索引，显式升级会补齐索引，不修改原成绩和逐杆。见[一致性修复](four-consistency-fixes.md)。
