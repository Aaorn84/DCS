# 可扩容后台基础（2026-11-23）

本轮完成可运行的基础改造，不代表已验收十万/百万并发。核心规则、移动端本地策略、最近五场策略历史范围不变；现有开发数据不删除、不自动迁移。实际容量按同时球局、同步事件率、语音云服务配额和尾延迟验收。

## 已接入

- `database.py`：现已统一PostgreSQL，开发与生产不再有数据库类型分支，见[统一存储](postgres-only.md)。生产连接池有连接数、等待人数与等待时间上限；SQL参数化，账号身份来自认证。跨进程账号事务锁、唯一键和版本校验保护同一账号写入，不使用进程内锁冒充分布式一致性。
- `Engine.command`：一致读快照中执行规则/策略，提交前在短写事务里重查指令去重、状态版本与记录权。冲突不重放写入、不猜补杆数。跨账号计算不再占用一个长写事务。
- `shared_core.py`：每API进程默认2个持久Node工作进程；按账号/球局作用域稳定路由缓存，每进程8包/32MiB上限。等待人数和时间有界，满载明确返回503，运行器失败不自动重试写命令。
- `wsgi.py`：复用原Handler路由；Gunicorn多进程/线程入口、应用并发上限、Redis共享IP/账号/登录主体限流、429/503及Retry-After。客户端仍须用原事件ID重试。只有明确配置的代理网段可提供X-Real-IP。
- `/health`进程存活、`/ready`数据库/规则核心/Redis就绪检查；`/metrics`受独立令牌保护，记录有界路径/状态计数及延迟桶。Server-Timing区分应用耗时与HTTP总耗时。多实例需逐实例采集，不通过负载均衡随机抓一次冒充全集群。
- 生产入口强制PostgreSQL与共享Redis；不允许带建表模式运行。开发ThreadingHTTPServer保留本机联调用途，不作为公网部署方案。
- 备份脚本原子生成自定义格式pg_dump、权限0600、输出SHA256；数据库凭据不放命令行。正式环境还需外部定时调度、加密对象存储和保留策略。
- 一次性手机清旧测试缓存逻辑已在冗余审查中移除，启动时不再扫描或删除其他版本球局；这不等同于已完成跨核心版本续局。

## 部署

1. 使用独立环境安装`prototype/requirements-production.txt`，发布时锁定并扫描实际依赖版本；安装Node>=22.13和匹配数据库版本的PostgreSQL客户端。
2. 准备专用PostgreSQL和Redis。数据库使用TLS验证与独立数据库；Redis设置认证、TLS和资源上限，不与可随意淘汰的业务缓存共用。生产API必须为DML账号；应用层按owner隔离，当前尚未配置数据库RLS。
3. 使用单独schema-owner凭据设置`CADDIE_DATABASE_URL`，运行`python prototype/scripts/bootstrap_postgres.py`。不导入旧测试数据，不清除已有开发库。正式演进应使用经过审查的版本化迁移，当前仅提供首版schema初始化。
4. 给运行账号授予public schema的USAGE和相关表SELECT/INSERT/UPDATE/DELETE，撤销CREATE/管理权限。切换为运行账号URL；建表仅由初始化命令执行，不再有运行期建表开关。设置`CADDIE_REDIS_URL`、至少32字符的`CADDIE_METRICS_TOKEN`和明确的CORS来源。
5. 在仓库根目录运行：

   ```sh
   gunicorn --chdir prototype/services/api -c /absolute/path/to/prototype/deploy/gunicorn.conf.py 'wsgi:create_app()'
   ```

   不使用preload。默认2个API进程，每进程8HTTP线程、2个Node工作进程、最多8个PG连接；部署N个副本时，DB连接预算至少按N×2×8计算，再预留维护和任务连接。参数需压测确定，不能无限调大。
6. 配置HTTPS反向代理，参考`deploy/nginx.conf.example`；同时限制慢请求、连接、请求体和公网入口流量。只在可信代理网段接收X-Real-IP；共享球场Wi-Fi的IP限额需结合实测调节，账号限额独立生效。
7. 仅在ready通过后接流量；先灰度，监控冲突率、429/503、PG锁等待/池等待、核心队列、p95/p99、CPU/内存及客户端语音分段耗时。

## 验证与压测

- `test_scale_foundation.py`覆盖并行核心容量、队列拒绝/超时回收、账号限额隔离、WSGI拒绝过载、登录限流、有界指标，以及计算时其他账号可写入、冲突不提交。
- `test_postgres_integration.py`使用真实PostgreSQL，覆盖并发重复写入、同步事件/游标原子提交、账号隔离、跨账号事务锁、DML-only运行账号、WSGI问答开局与策略。
- CI增加一次性PostgreSQL17和Redis7服务，执行上述测试及跨实例Redis限额检查。CI配置已写入仓库，本轮尚未提交或触发远程CI。
- `benchmark_scale_http.py`明确要求`--allow-test-writes`，只能对独立测试部署执行；会创建测试账号和球局，不得指向真实用户库。分开报告首次查询、后续查询和应用处理时间。

```sh
CADDIE_TEST_POSTGRES_URL=... PYTHONPATH=prototype python -B -m unittest discover -s prototype/tests -p test_postgres_integration.py
CADDIE_TEST_REDIS_URL=... PYTHONPATH=prototype python -B -m unittest discover -s prototype/tests -p test_scale_foundation.py
python prototype/scripts/benchmark_scale_http.py --base-url http://127.0.0.1:8787 --users 8 --turns 10 --allow-test-writes
python prototype/scripts/backup_postgres.py /secure/backups/caddie-YYYYMMDD.dump
```

恢复演练必须使用新的隔离目标数据库，通过pg_restore校验逐杆、成绩、事件、回执和账号隔离；不得在原库直接练习覆盖恢复。定期确认备份可解密、可恢复，并记录实际RPO/RTO。

## 尚未交付的规模阶段

- 未部署外部PostgreSQL、Redis、域名/TLS、备份调度和多机集群；本机开发服务已切到新的PostgreSQL空库，旧文件库已删除。
- 尚未建设对象存储/CDN地图分发、跨用户公共地图引用去重、异步分析任务队列、历史统计增量物化和完整追踪告警平台。
- 尚未实现在线旧核心版本的续局路由/兼容窗口。正式用户升级前必须保留旧版本执行能力和同步接口，完成新旧版本、撤销、断网重连验收；不能依赖清数据升级。
- Redis共享限流测试已接入CI，本机未执行真实Redis/故障切换验收。多可用区容灾、读副本、分区/分库按实测负载引入，不预先宣称实现。
- 小样本本机测试不覆盖云端ASR/TTS、手机、弱网、真实地图大包、长时间稳定性或百万用户容量；上线前仍需阶梯负载、突发开局/集中同步、故障注入和恢复演练。

## 前一轮双路径改造实测记录（数据库路径现已退役）

环境：macOS arm64、Python3.12、Node24、Gunicorn23，临时SQLite与独立临时PostgreSQL；没有连接现有用户库。真实PostgreSQL5项契约测试通过，包括DML-only账号；备份恢复到另一个临时数据库后10张表逐表一致，备份权限0600。常规API回归87项通过，PostgreSQL5项在独立运行中通过；真实Redis共享限流1项本机未执行。JavaScript104项、业务Python141项及核心类型/手机语法检查通过。

相同单用户HTTP脚本、凤凰山第1洞30次紧凑查询：改造前p50/p95为3.592/5.055ms，改造后4.039/5.395ms；首查询10.502→11.000ms。短事务和版本复核增加少量工作，没有以删检查换速度。

Gunicorn2个API进程、每进程2个Node工作进程，8个独立账号、每账号10次串行请求，共80次请求全部200。最后一次PostgreSQL测试采用已有的增量视图协议：客户端HTTP总体p50/p95为16.987/139.852ms；首次8次查询105.415/139.852ms；后续72次13.630/123.385ms；应用处理80次14.966/120.189ms。该短测约169请求/秒，不是稳定容量承诺，冷查询与进程调度造成的尾延迟仍须在实际部署上定位与优化。

上述测试不含ASR/TTS、手机渲染、移动网络与实地GPS，不代表端到端语音体验或十万/百万用户容量。远程CI、真实Redis故障切换、长时间压测仍待执行。

临时HTTP错误重试、探针独立性与本地初始化竞态的后续修复见[reliability-fixes.md](reliability-fixes.md)。
