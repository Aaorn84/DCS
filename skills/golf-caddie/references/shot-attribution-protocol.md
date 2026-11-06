# 逐杆事件归因与可回滚学习候选 v0.1.0

当前交付：技能v0.1.8，状态内核v0.4.0，新模块shot_chain及其JSON原型。输入为已经标准化的事件候选，不开发底层ASR、任意自然语言训练、云数据库、GPS APP正式接口或专利权利要求文件。旧v0.1.6手机联调原型保持原版本；本轮新增功能通过本地Python接口/CLI验证，不能声称已经接入那个手机页面。

## 运行

在技能目录：

```sh
python3 -B scripts/shot_chain_cli.py --scenario assets/shot-chain-example.json
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

默认内存数据库、local-demo身份；`--database /tmp/shot-chain.sqlite`可持久化。CLI也接受stdin JSON-lines，每行一个请求。它不提供网络认证；服务集成必须由宿主认证身份构造Engine。

```json
{"action":"create","round_id":"r1"}
{"action":"event","round_id":"r1","event":{"event_id":"u1","type":"execution_report","source":"voice","occurred_at":"2026-11-06T08:00:00+08:00","confidence":{"asr":0.95,"attribution":0.9},"candidates":[{"id":"c1","value":{"club":"7i"}}]}}
{"action":"shot","round_id":"r1","shot_id":"s1"}
{"action":"state","round_id":"r1"}
{"action":"replay","round_id":"r1"}
```

上述execution例子需要之前已经建立s1且它是当前未完成击球；没有球位/击球依据不能为了得到commit先伪造一杆。示例scenario含明确的open_shot事件及完整闭环，杆序保持null。

直接Python调用：`engine.command(round_id,event_id,'attribution_event',event,expected_version=known_version)`。CLI默认以event_id作为幂等命令键；网络回执丢失时重用原ID和内容，不生成新ID重播。相同逻辑event_id用其他传输键重送，也不会新增节点或击球，但会产生一个重复回执的聚合日志版本。同ID不同内容拒绝。所有成功事件同SQLite事务写入；拒绝时正式状态和账本均保持原状，CLI输出reject原因。

## 事件类型和职责

11种语音主类型：fact_request、player_intent、decision_commitment、execution_report、shot_outcome、feel_or_cause、correction、score_report、state_transition、interaction_override、companion_dialogue。每个事件只有一个主类型，candidates允许多个候选解释。词义分类由上游完成，本模块校验分类、来源和候选，再维护状态。

内部入口另有system_advice、gps_context、course_context，分别由system/gps/course来源提供。voice/user_correction不能冒充系统建议。只接收final标准化事件，partial必须在此前的原始证据层暂存。

| 类型 | 结构化值或作用 |
| --- | --- |
| system_advice | club/target/route/style，记录建议曾经存在，不代表球员接受或执行 |
| player_intent | 同上，记录想法，不写实际用杆 |
| decision_commitment | 同上，确定选择；变更已知选择需explicit=true |
| execution_report | club/style，实际执行；“还是用了7铁”的标准化结果应进入这里 |
| shot_outcome | longitudinal=short/long/on_target/unknown，lateral=left/right/on_line/unknown，lie=fairway/rough/bunker/water/green/ob/unknown |
| feel_or_cause | self_report字符串，保持“球员自述”，不是系统诊断的真实原因 |
| correction | candidate.corrects_node定位当前有效节点，explicit=true；value只放更正字段 |
| fact_request | 查询候选/后果比较；记录请求，不凭它产生击球或精确距离/规则答案 |
| score_report | value含total/relative/putts/penalties；未知分项null；explicit_confirmation=true才正式记分 |
| state_transition | explicit=true，value.kind=open_shot/finish_shot/enter_hole/end_round |
| interaction_override | 明确quiet/quiet_holes/resume/scores_only/normal，或引用previous_decision |
| companion_dialogue | 留在交流事件，不写击球、成绩或长期模型 |

source=voice/gps/course/user_correction/system；occurred_at必须带时区。confidence分开asr与attribution，可为null，不以高置信度代替解歧。

## 建立、归属和引用

明确建立击球的标准化转换：

```json
{"event_id":"open1","type":"state_transition","source":"voice","occurred_at":"2026-11-06T08:00:00+08:00","explicit":true,"value":{"kind":"open_shot","shot_id":"s1","hole":1,"stroke_number":null}}
```

这代表宿主已经有建立该杆的依据，不是要求用户每杆念口令。只有GPS移动或缺少语音，不能自动发送open_shot或推算杆序。已知杆序同一洞不得重复；不知道继续null，不由执行报告加一。

candidate可显式给shot_id/hole/stroke_number，缺shot_id时仅绑定当前已建立、未完成的击球。没有唯一上下文就保持未知并澄清，不用最近聊天位置代替球位。结果与自述原因跟随已绑定执行；执行优先引用本杆决定/意图/建议。跨洞更正由corrects_node定位原杆，不倒退当前球洞。

“按原来的”由`interaction_override`、`reference=previous_decision`和一个value为空的候选表示：只引用同一杆最近仍有效的决定，不引用已撤回/被替代/失效的决定，不代表实际已执行，也不解除静默。

每杆保存advice、intent、decision、execution、outcome、cause、gps七个槽及完整history；不存在的槽在shot_view中显示unknown/value=null。节点含shot_id、hole、stroke_number、source、status、valid、独立置信度、occurred_at、previous_event_id、version、supersedes及supersedes_version、证据和依赖、learning_eligibility。修正通过追加事件产生新节点，旧节点在投影标记superseded，原始输入仍保留在命令日志；valid标识证据当前是否有效。

显式撤销某槽使用correction、explicit=true、candidate.corrects_node和retract=true；原节点投影标记retracted，槽恢复unknown，并撤回相关派生候选，原始事件保留，不恢复未经验证的更早版本。

成绩修正使用candidate.score_target={hole,read_versions}精确指向要改的成绩字段，value仅含total/putts/penalties；explicit与explicit_confirmation均须true，读版本必须覆盖每个被改字段。保留score_revisions的before/after及版本，独立推数、GPS不受影响。

重复补充“短”和“右”会形成同一杆合并结果的新版本；与既有事实冲突的普通报告不会静默覆盖，必须更正或显式解歧。学习候选及各槽版本独立，不因改杆重写GPS端点或独立成绩。

## 策略影响三级门控

候选effects必须由可信只读策略组件提供，包含club、target、route、score、hole_state、learning、safety。原型只比较后果，不训练或冒充完整高尔夫策略算法；没有后果数据时按影响未知处理。

- 低：两种理解不改变策略后果，保留候选/距离范围，不打断；不因相同后果把某个解释选成事实。
- 中：会影响历史记录等，但current_action=false，不影响当前击球，暂存，留待换洞或赛后宿主自然补采；本原型不自行发起赛后对话。
- 高：当前归属、球杆、路线、成绩、状态、学习或安全后果不同，提出一个澄清问题。未回答不提交。quiet/preparing或scores_only的约束优先时，高影响仍阻止提交，但把问题暂缓，不能为解歧打断击球。

内核同时直接比较shot/hole/ordinal及value内club/target/route/total/putts/penalties/relative；外部effects错误标成相同，也不能掩盖直接字段差异。其余复杂安全含义依赖上游策略组件正确表达，不能宣称已完成人类语义风险判断。

全局至多一个待答问题，和旧核心question表互相门控。后续高影响事件可暂存，不叠加第二问题。显式解歧事件：同一主type、explicit=true、resolves_event_id指向原事件，candidates只包含原结果中的一个完整候选；如果相关槽已变化，旧解歧拒绝，需基于最新状态重新归因。

输出action为commit/defer/clarify/reject。commit只是该事件有依据的部分已落账；fact_request和companion_dialogue的commit不代表发生了击球。rejected输入不进入正式状态，CLI返回action=reject和原因。

## GPS、球场与学习资格

球场仍提供布局、par、地理对象，GPS提供候选位置；语音提供执行、意图和结果，三者互补。course_context引用已存在的active final course evidence。candidate.object_refs引用evidence_id/object_id，校验对象属于目标洞，保留地图版本依赖。地图更新使引用对象的节点/派生结果失效，不会删除独立真实执行。

gps_context只保存候选端点；value沿用shot_evidence的start/end、single_stroke_confirmed、intervening_strokes、relief_or_provisional、gap_open、max_position_error_sum_m字段。GPS候选hole与已绑定杆的洞号不同，保留conflict，不改写原洞号，也不自动裁定谁错。实际对象几何匹配、传感器融合与定位质量判断由宿主提供，原型没有新造测绘或越障模型。

只有已知实际杆号、可靠球位端点、同洞同一杆关联成立，且宿主传入真实已授权recording_consent=true时，才产生可审阅的总距学习候选。缺落点、杆号、间断或精度不足不造距离，并保留已知执行。所有carry_calibration与long_term_model保持false；本轮“短/右/打厚”不会改球包、carry、分布或长期人格。

learning_candidate依赖执行节点与GPS节点；更正8铁为9铁，8铁学习候选失效；若同一GPS证据仍完整且已有授权上下文，产生9铁总距候选。它仍不是已训练的个人模型。原始GPS水平总距不等于carry。

score_report可只给hole，不要求补造一杆。relative需要active course_context中该洞par才能换算，缺par暂存；total与换算结果不一致拒绝。显式确认后才写总杆/分项，总杆已含罚杆。相对成绩转换保留par及地图来源；来源修订则相关确认事实失效，需复查。

quiet_holes包含当前洞，仅在明确enter_hole转换时减一；GPS候选变化不消耗静默洞数。scores_only抑制非成绩澄清，不等于删去已有事实；resume才明确恢复静默。宿主语音投递仍遵循既有版本门控与比赛功能限制。

## 验收

新增47项自动测试：45项归因/修正/门控及槽视图测试、2项CLI流程测试，共计183项技能回归。覆盖用户要求的12类场景，另覆盖相对杆数/缺par、过期解歧、partial拒绝、地图更新、证据失效、静默洞数和高置信度不替代安全解歧。

这些是标准化输入的确定性测试；例句作为测试文本保留，实际判定依据是结构化候选，不宣称任意原始中文已自动正确解析。没有新增正式APP接口、云端数据库、ASR训练或权利要求文件。


## 七条约束的验收映射（v0.1.8）

| 核心约束 | 可观察验收结果 |
| --- | --- |
| 多轮维护球局 | 意图、决定、执行、结果可分轮到达；重启重放等价，不要求每杆交流 |
| 六类事实分离 | 建议或决定不会生成实际用杆，自述打厚不成为系统诊断 |
| 按影响处理 | 高置信度仍须评估影响；低影响留候选，中影响暂存，高影响且允许开口才澄清 |
| 可审计、可回滚 | 重试不多记，修正保留旧值/来源；只使相关派生数据和学习候选失效 |
| 输入来源不越权 | GPS执行报告拒绝；语音冒充球场来源拒绝；用户更正位置另存候选，原始GPS证据字节不变 |
| 不完整证据 | 没落点不造距离，没杆号不拿建议补实际杆；GPS总距不是carry |
| 一轮单问题 | 新澄清不能与既有问题叠加；静默/准备状态下高影响问题也暂缓 |

来源越权检查针对可信宿主传入的规范化source；原型不具备验证传感器签名或识别说谎的能力。宿主必须建立来源与认证边界，不能让模型或不可信客户端自行宣称source=course/gps。语音观察可以指出地图疑点并形成修订提案，不能把球员自述当成已核实测绘。当前186项回归通过，其中本轮新增3项跨来源边界测试；状态引擎算法版本保持0.4.0。
