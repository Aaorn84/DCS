# 电子球童 / Golf Caddie

面向业余球手的语音球童开发版。手机与网页使用同一份TypeScript规则、状态和策略核心；后台仅使用PostgreSQL，负责账号、同步复核、历史与赛后服务。当前不是经过实地验收的上线版本。

## 当前源码

- `prototype/shared/core/`：唯一场中规则、状态、地图几何和击球策略实现。
- `prototype/services/api/`：认证、PostgreSQL事件事务、同步、首次问答、赛后服务及生产WSGI入口。
- `prototype/apps/mobile/`：本机规则执行、离线检查点、同步与前台语音接线。
- `demo-local/`：接入共用核心的网页演示。
- `skills/golf-caddie/`：技能资料、数据工具、报告服务镜像及测试。镜像服务于技能打包，不是第二套场中规则。
- `球场数据接入样本/`：地图来源与规范化样本。
- `versions.json`：组件版本，不能代替上线验收。

`archive/`和`dist/`中的旧备份及过期构建已按用户批准删除，当前运行与交付应以本仓库源码和验证记录为准，见[冗余审查](prototype/docs/redundancy-audit.md)。

## 本机运行

需要Python3.12及Node>=22.13；Node24已用于当前回归。仓库根目录执行：

```sh
python3 -m pip install --target .runtime/python -r prototype/requirements-development.txt
python3 -B prototype/scripts/run_local_demo.py --port 8791
```

打开 http://127.0.0.1:8791，重新注册账号。启动器使用项目专用的本机PostgreSQL；旧SQLite账号、资料与球局已删除，未做迁移。私有数据库、配置和依赖位于Git忽略的`.runtime/`，不可打包或分享。

外部数据库通过`CADDIE_DATABASE_URL`配置，先显式初始化schema，再用DML-only账号运行；详见[PostgreSQL统一存储](prototype/docs/postgres-only.md)及[生产部署](prototype/docs/scale-foundation.md)。正式服务使用Gunicorn与共享Redis，开发HTTP服务不用于公网部署。

## 测试

```sh
python3 -B prototype/scripts/run_local_tests.py
python3 -B prototype/scripts/run_local_tests.py --suite benchmark
```

数据库测试使用独立PostgreSQL测试库中的随机schema，结束后清理，不写入应用库。手机/后台核心一致性、离线恢复、账号隔离、幂等和规则流程均有回归。CI另使用PostgreSQL与Redis服务；本机尚未执行真实Redis联调。

## 验收边界

凤凰山地图与桩位仍属于来源坐标演示；未实地核验的边界不能当作真实击球导航。真实GPS、原生完整构建、耳机/风噪/锁屏语音、飞行模式整场与低空间恢复仍需真机验收。宿主机接口耗时不代表端到端语音响应，当前小样本测试不代表十万或百万用户容量。

当前架构和能力见[共用核心](prototype/docs/shared-core-architecture.md)、[原生验收](prototype/docs/offline-native-acceptance.md)。历史设计文档已经标注退役范围，不作为现行接口或运行命令依据。

手机离线开局：提前下载球场后，可在本机完成问答、Carry核对、Tee和起始洞选择；新球局联网后再注册同步。详见[离线协议](prototype/docs/offline-round-sync.md)。首次账号认证及下载需要联网，原生语音/GPS整场实机验收尚未完成。

规则与策略现分为统一规则、系统策略、个人档案及球场分析四层，见[分层说明](prototype/docs/strategy-layers.md)。

已支持1.4/1.5固定核心的[升级续局](prototype/docs/versioned-round-resume.md)，原球局不迁移、不删除，新球局使用当前核心。

最新默认核心1.6.0，保留1.4/1.5续局；球局释放、Carry继承、补传资料合并和跨核心成绩对比已修复，见[说明](prototype/docs/four-consistency-fixes.md)。
