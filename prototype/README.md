# 电子球童完整旅程原型

手机主流程已使用 `shared/core` 的统一规则、状态、地图和策略模块，后台通过常驻Node复核同一份TypeScript。`demo-local`网页也已通过`core_event`接入同一份规则、状态与策略核心；网页场中不再调用旧规则链路。首次问答和赛后分析继续使用应用服务。首次认识与同步仍使用认证`/journey`接口，从首次认识走到下一场。运行与边界见仓库README及skills/golf-caddie/references/complete-journey.md。

后台需 Node >=22.13（可用 `CADDIE_NODE_BINARY` 指定）；核心启动失败不回退另一份规则。架构、缓存和本次测试数据清理见 [shared-core-architecture.md](docs/shared-core-architecture.md)。

后台仅支持PostgreSQL。仓库根目录运行`python3 -B prototype/scripts/run_local_demo.py --port 8791`；外部数据库通过`CADDIE_DATABASE_URL`配置，见[统一存储](docs/postgres-only.md)。API入口为`python3 -B services/api/server.py`；手机填写可访问的API地址。前台语音已有接线，真实GPS、后台、锁屏与正式球场适配尚待实现/验收。旧场中分支、会话接口及技术联调页已移除，见[退役清单](docs/legacy-retirement.md)。

测试：仓库根目录运行`python3 -B prototype/scripts/run_local_tests.py`，数据库测试使用独立PostgreSQL测试schema。新增首次使用到下一场的HTTP闭环、认证隔离与版本冲突测试。手机TypeScript检查通过不代表已构建或安装原生包。

跨场散布、独立记分入口、落点搜索和历史比较基准的修复见[四项审查修复](docs/four-audit-fixes.md)。

生产后台的PostgreSQL、Gunicorn、限流、压测与部署说明见[可扩容后台基础](docs/scale-foundation.md)。开发HTTP服务仅供本机联调。

手机离线开局：提前下载球场后，可在本机完成问答、Carry核对、Tee和起始洞选择；新球局联网后再注册同步。详见[离线协议](docs/offline-round-sync.md)。首次账号认证及下载需要联网，原生语音/GPS整场实机验收尚未完成。

规则与策略现分为统一规则、系统策略、个人档案及球场分析四层，见[分层说明](docs/strategy-layers.md)。

已支持1.4/1.5固定核心的[升级续局](docs/versioned-round-resume.md)，原球局不迁移、不删除，新球局使用当前核心。

最新默认核心1.6.0，保留1.4/1.5续局；球局释放、Carry继承、补传资料合并和跨核心成绩对比已修复，见[说明](docs/four-consistency-fixes.md)。
