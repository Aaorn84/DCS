# 旧场中实现退役（2026-11-23）

首次问答由 `onboarding.py` 处理，赛后分析、逐洞复盘和自愿教练由 `postgame_service.py` 与原有只读统计模块处理。`application.py` 只路由这些应用事件，明确拒绝 active/finish_confirm 阶段；不能借问答服务记杆、改分或处理事故。`round_view.py` 读取核心投影，不进行旧账本回填或重新解释击球。

场中唯一规则与状态实现是 `shared/core/roundEngine.ts`，唯一策略实现是 `strategy.ts`。手机直接执行，网页通过 `shared_web.py` 调用常驻 Node。多语言有限语法适配也转入同一核心，不再调用旧旅程归约器。`report_geometry.py`、`surface_uncertainty.py`、`projected_ledger.py` 仅供成绩分析、落点分类和展示，没有击球/罚杆状态迁移。

已删除旧 `journey.py`、全部 `journey_*` 分派器，以及 Python `ball_rules`、`ball_outcome`、`round_session`、`shot_chain`、开球/攻果岭/短杆策略、旧GPS切洞状态机和对应版本链。账本投影已改名为 `round_ledger`，不再读取旧 `ball_rules` 或 `confirmed_shot_distances` 字段。

`POST /journey` 只接受 `action:core_event` 进入问答/球局流程；旧 `action:event` 和 `POST /round-state` 返回 HTTP 410。客户端不能提交协议降级字段。旧 CLI、手机 IntegrationLab、RoundSession 客户端、未使用的domain/voiceFlow独立记分流程及两洞合成会话入口同时退役。离线准备必须携带 local_engine_version:1/core_version:1.2.0，同步仅接受 local_round_command；已删除 message/GPS 自由文本重放模式。

`Engine` 只负责账号隔离、幂等、版本检查、事务和重放，不再包含另一套打球/记分规则。仅接受 application_event、shared_web_event、offline_rules_event、international_event；旧命令种类拒绝并回滚。

兼容旧分派器的测试已删除；保留并更新认证、存储组件、原始落点、技术统计、复盘和同步原子性测试。新增首次问答/保底杆/记忆/赛后隔离、退役入口拒绝测试；场中行为由共用核心及网页闭环测试覆盖。测试数据库临时创建，不迁移旧协议数据。

性能：同此前 darwin arm64/Python3.12/Node24 环境，临时SQLite、本地HTTP、凤凰山第1洞、30次询问、紧凑视图，旧共用入口基线 p50/p95 4.013/5.672ms，本次拆分后 3.616/5.304ms；首次方案 8.937ms、开局 213.508ms。单轮本机测量仅作回归参考，不含真实网络、浏览器渲染、ASR/TTS和手机端到端语音。

场中实现退役阶段验收：73项Python API/应用/同步测试、89项JavaScript共用核心/恢复/网页测试、136项保留的Python数据与分析测试通过。共用核心和JourneyClient严格TypeScript检查、App/voice语法检查通过；多语言当前入口演示可重放。未安装完整原生依赖，未做真机麦克风或语音端到端验收。


## 兼容层清理（核心1.2.0 / shared-core-2）

新流程不再读取或迁移旧单文档、未压缩状态、内嵌地图包或旧不可变包格式。手机直接引用shared/core；旧localRoundEngine/localRoundDialogue转发文件和Python local_round_engine转发模块均已删除。后台下载统一生成带core_version、dataset与local_command_semantics的完整核心包，build不再有local_rules开关。手机prepare同样取消模式参数，自由文本/GPS离线队列及enqueue入口已删除。

每条共用命令必须明确semantics:2，地图包必须声明当前核心版本。未带版本的请求拒绝，原状态与同步游标不变；没有按旧语义解释的分支。底层读入旧格式时明确报错，不迁移旧球局。新命名空间下仍保留双槽提交、损坏检测和原子恢复；过期测试缓存清理仍然执行，它是删除旧数据，并非兼容加载。

显式拒绝旧HTTP入口、核心版本不匹配保护、只读成绩统计和历史设计文档保留，均不执行旧场中逻辑。天气研究模式属于独立功能，不在本次球局兼容层清理范围。

本轮本机HTTP测量：相同临时SQLite、凤凰山第1洞、30次查询、紧凑视图，清理前p50/p95=3.616/5.304ms，清理后3.658/5.161ms；首次方案9.240ms、开局215.564ms。只作本机回归参考，不含真实网络与原生语音链路。

兼容层最终验收：75项API/同步/应用服务测试、94项JavaScript核心/恢复/存储/网页测试、136项Python数据与分析测试通过；共用核心与本机持久化/同步模块严格TypeScript检查、App/voice语法检查通过。原生完整构建及真机端到端语音仍未验收。

当前核心为1.4.0；/sync独立记分写入已关闭，/records隐藏旧round文档，保留非球局个人记录接口。四项审查问题及验收见[four-audit-fixes.md](four-audit-fixes.md)。
