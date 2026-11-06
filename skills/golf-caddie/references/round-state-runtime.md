# 球局状态引擎运行与接入 v0.5.0

随技能v0.1.9交付的Python标准库实现，不依赖网络或第三方包。

## 已实现范围

- `scripts/round_state.py`：SQLite事务账本、纯reducer、确定性重放、版本/幂等、用户隔离、证据修订、确认提案、补偿回滚、依赖失效、单待答问题及语音outbox。
- `attribute`：保守中文语法适配器，支持明确洞号总杆、问题绑定的杆号/推数/罚杆、计划与实际用杆、明确改杆及同伴过滤。返回候选，不自动保存。复杂、隐含或未支持语句返回unresolved/clarify；不能把它宣传为通用自然语言理解。
- `assess_ambiguity`：注入只读planner比较候选后果；不齐全或失败返回unknown，结果不同则澄清或暂缓；可返回共同可靠答案，不因此批准记录。
- `record_distance`：调用已有击球证据门控，计算并记录单杆水平总距、保存端点依赖。间断、救济、精度不足等拒绝连距；不生成carry。
- `missing_score_question`：依次建议缺失总杆、推数；已知par且+2以上时建议补未知罚杆。只返回一个字段；跳过/估计推数不等于确认事实，不倒推击球链。
- `scripts/round_state_cli.py`：本地JSON-lines入口，可供开发者与APP联调工具调用。

## 信任边界

Engine是服务端领域库，不是公开HTTP服务。`Engine(database, authenticated_owner)`的owner必须由宿主认证会话提供，不能来自用户请求体或大模型。CLI的`--owner`仅作本地测试身份，不提供认证能力。独立连接可并发访问，单连接不跨线程共用。

宿主负责录音/记忆授权、ASR、GPS质量判断、地图/天气来源、正式比赛功能权限、提案证据是否真实支持语义、明确同意识别、当前球位更新、数据保留/删除与TTS设备投递。模型只产候选，不能直接访问`command`或设置权限。派生结果登记`derive`也只供宿主可信算法使用，不接受模型自称算出的精确距离/统计。

本轮未改旧APP服务端、移动端或/chat接口；无真实语音、GPS后台、耳机或生产认证接通。没有新增海拔/坡度能力，也没有训练真实球员模型。

## 最小可运行示例

从技能目录运行：

```sh
python3 -B scripts/round_state_cli.py --database /tmp/caddie-demo.sqlite --owner local-test <<'JSONL'
{"action":"create","round_id":"demo"}
{"round_id":"demo","command_id":"e1","kind":"evidence","payload":{"id":"u1","revision":1,"phase":"final","source":"user","observed_at":"2026-11-06T08:00:00+08:00","text":"一号洞五杆"}}
{"action":"attribute","round_id":"demo","text":"一号洞五杆"}
{"round_id":"demo","command_id":"p1","kind":"propose","payload":{"id":"p1","base_version":1,"evidence_ids":["u1:1"],"operations":[{"path":"holes.1.total","value":5,"status":"confirmed"}]}}
{"round_id":"demo","command_id":"c1","kind":"confirm","payload":{"id":"p1","confirmation_version":2,"explicit":true}}
{"action":"state","round_id":"demo"}
{"action":"replay","round_id":"demo"}
JSONL
```

在新数据库中最终version为3，事实包含一号洞5杆；推数、罚杆保持缺失，绝不填0。示例`explicit:true`代表测试中模拟用户已确认；真实宿主必须等用户明确确认后再发。重复运行同一示例不会重复应用命令。

Python入口：`engine.command(round_id, command_id, kind, payload, expected_version=None)`。所有成功命令都推进聚合版本；state/replay/attribute读取不推进。返回结果含version，命令重复键同载荷返回原结果，不同载荷冲突。异常使本次事务完全回滚。

## 命令协议

| kind | payload主要字段 | 行为 |
| --- | --- | --- |
| evidence | id、revision、phase、source、observed_at；可带text | source=user/gps/course/sensor；partial仅存证；同revision允许partial→final；已提交事实引用旧final后遇新final会失效，须重新确认 |
| gps_transition | evidence_id、hole | 仅final GPS且证据reliable_transition=true；拒绝迟到倒序事件；只更新洞号，不推断击球或完成球洞 |
| control | evidence_id、path、value、explicit | user final与明确指令更新静默/准备状态、主动/教练偏好或策略许可；GPS不能解除静默 |
| question | id、target、field、deps、proactive | target=shots.ID或holes.N；最多一个pending；静默/准备时拒绝，主动须已有授权 |
| answer | id | 标记待答问题完成；宿主先完成归因，再以单独提案保存内容，不自动将“已回答”当事实 |
| interpret | id、evidence_id、candidates、complete | 候选含operations和planner outcome；保存解释及比较报告，不修改正式事实 |
| propose | id、base_version、evidence_ids、operations、read_versions | operations含path/value/status；status=confirmed/estimated/unknown。创建needs_confirmation提案，返回confirmation_version |
| confirm | id、confirmation_version、explicit | 显式确认、活跃final用户证据、聚合版本一致才提交；成绩检查总杆已含罚杆 |
| retract | id、explicit | 补偿指定已提交提案；有后续修改同字段则冲突；其他独立后续记录保留 |
| derive | id、kind、deps、algorithm_version、value | 仅可信计算组件登记distance/club_stats/strategy/coaching；stats拒绝估计值及其间接派生输入 |
| enqueue | id、text、deps、expires_at、scope、strategy、proactive | scope=current/past；自动绑定当前洞；当前策略还强制绑定context.ball_position；保存queued或按门控立即cancelled |
| dispatch | id | 发出前再次检查依赖、静默/准备、策略/主动许可与有效期；返回delivery_id，转为claimed；取消/过期返回text=null |

字段白名单：context.active_hole/ball_position/quiet/preparing；preferences.proactive/coaching；permissions.strategy；holes.N.total/putts/penalties；shots.ID.actual_club/planned_club/hole/position。未知数值用null与unknown；布尔偏好须明确。球位遵循shot_evidence的WGS84、时间、精度、hole_id、ball_position_confirmed字段。

`context.ball_position`是已核实的当前球位；每次可靠球位变化必须更新它，不能只新增另一shot的位置，否则宿主无法声称当前策略仍有效。shot位置是历史端点。一次GPS坐标不等于确认球位。

deps/read_versions为`{fact_path: version}`，派生引用写成`derived:ID`。派生ID不可覆盖，以新ID登记新版本，防止循环和悄悄恢复旧结论。撤回后恢复值也分配新版本，旧语音/统计不能因值相同重新有效。

候选outcome必须含answer、feasible、forced_carry、target、club、score_effect、record_effect、permission_effect，后果值按只读planner可审计规则输出，不编造概率。propose可带interpretation_id；绑定候选时必须匹配其operations，仍有分歧则另带新的final用户resolution_evidence_id、resolved_explicit=true并纳入evidence_ids。直接提案仅用于宿主已经核实的结构化操作，不是绕开归因门控的模型接口。

## 版本、撤回与投递语义

确认绑定提案ID和创建提案后的聚合版本；期间任何写入都会导致旧确认失效。当前采用保守聚合冲突检查，宿主需基于新状态重新提案；不会把并发确认自动挪到新版本。不要因冲突跳过用户确认。

改杆可保留独立距离，撤回位置会递归失效距离/统计/教练结论及待播内容；已被后续修改的字段不允许粗暴撤回。ASR修订使静默事实不确定时，门控继续保持安静，等待明确新指令。

语音claim与SQLite事务绑定，但SQLite与实体耳机之间没有分布式事务。宿主必须按delivery_id去重；网络重试同一dispatch命令会返回原投递结果，不代表应再播一次。claimed不保证用户已经听见；TTS失败重试、取消正在播音频和实际回执由宿主实现。本引擎不能撤销已听到的建议或已打出的球。

原始转写会持久化在SQLite证据及命令日志中。生产接入前宿主须落实授权、保留期限、删除与数据库备份清理；本版本不提供可合规替代宿主删除策略的接口。测试只用合成数据。

## 验证

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

现有算法与打包回归53项；状态内核与CLI累计60项，共113项。覆盖重启重放、双连接冲突、逐字段失效、修订、静默、候选解歧和单杆距离断链。没有以这些测试宣称通用语音理解、完整策略模型、真机或真实球场精度已验证。


## 三路输入补充

球场与GPS仍是事实底座；语音是交互与行为证据。v0.2.0增加course证据来源和evidence依赖引用，详见 [三路输入联合规范](multimodal-inputs.md)。地图修订可递归失效相关派生结果；地图几何计算与真实GPS适配不包含在本库内。


## v0.1.6会话接入

新增session_event复合命令和round_session模块，一个三路输入事件的内部步骤同事务提交；限定问距/报分/逐项补采/明确确认/撤销已通过认证开发API接入独立手机联调构建。详见 [会话协议](round-session-protocol.md)。旧APP未替换，供应商GPS/地图、通用ASR理解和真机依然未接通；上文未接入声明针对旧原型和真实设备。当前技能回归136项，另有独立原型API15项及客户端10项。


## v0.1.7标准化逐杆归因

新增attribution_event命令、shot_chain和shot_chain_cli，见 [逐杆归因协议](shot-attribution-protocol.md)。chain:NODE_ID可作为版本依赖，superseded/无效节点不再作有效输入；学习候选只用于审阅，不自动更新carry或长期模型。当前共183项技能回归；独立v0.1.6 APP原型保持固定旧版本，本轮未升级正式APP接口。


## v0.1.9内置球场参考数据

名商已以reference_only目录内置，builtin_courses可离线查询及注册course evidence，见 [内置球场规范](builtin-course-data.md)。仅在crs=null、coordinate_status=unverified、spatial_use_allowed=false且holes=[]时允许存储未验证目录；session正式地图入口仍拒绝此类目录，不生成GPS距离。当前技能205项回归。
