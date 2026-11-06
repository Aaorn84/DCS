# 三路输入会话协议 v0.1.0

技能v0.1.6；状态内核v0.3.0；round_session适配器v0.1.0。

## 架构与交付

用户只需语音交流，后台联合球场、GPS、语音维护状态。新增确定性会话适配器，接入已登录的开发API与独立手机联调页面：

`APP/测试工具 → Bearer身份 → /round-state → session_event → 三路证据/单项提问/确认提案 → 同一SQLite事务 → 状态与可追溯结果`

一个session_event的多个内部步骤共享一个聚合提交版本，事件与其证据、提案或确认同成同败，按提交日志可重放。新模块只实现限定中文流程，不代表通用语义理解、完整策略规划或真实数据服务已经完成。

交付目录：`/Users/aaron/Workspace/电子球童/prototype-v0.1.6`。旧手机APP原型保留；新联调构建独立使用，避免旧voiceFlow和/sync重复写分。新状态账本是本流程事实源，旧records并未自动迁移或同步投影。

## 身份与接口

沿用/auth/register、/auth/login获取Bearer令牌。HTTP开发服务仅供本机或可信联调网络，不是公网生产服务。

`POST /round-state`，Content-Type: application/json，Authorization: Bearer TOKEN。

- `{ "action":"create", "round_id":"r1" }`：同账号同ID创建或恢复，返回state。
- `{ "action":"snapshot", "round_id":"r1" }`：读当前state。
- `{ "action":"replay", "round_id":"r1" }`：从事件重放，返回state。
- `{ "action":"event", "round_id":"r1", "operation_id":"op1", "event":{...} }`：提交会话事件；可带expected_version。

owner仅来自认证会话，客户端不得指定。事件不接受raw command、operations、permission patch或reliable_transition。模型只能产候选，不可调用原始数据库命令。API仅暴露会话适配层。

成功事件响应：`{result:{text,saved,version,speak_allowed,...},state:{version,facts,evidence,patches,derived,questions,outbox,interpretations,session}}`。text可能为空；saved仅代表本轮正式记分成功，不是候选已保存。错误400为格式/语义/不存在球局等，401为认证问题，409为幂等或聚合版本冲突并附current。请求体上限64KiB；大地图需未来对象服务或分块协议，本版不支持。

operation_id与完整事件保持不变才能安全重试；同键变内容返回409。event_id标识输入，revision标识同段修订，phase=partial/final；观察时间observed_at使用带时区ISO时间，服务端另记接收时间。partial语音只留证，不问答、不写分。

## 三类事件

### 球场

```json
{"type":"course","event_id":"map1","observed_at":"2026-11-06T08:00:00+08:00","data":{"course_id":"synthetic","map_version":"1","crs":"WGS84","synthetic":true,"holes":[{"number":1,"par":4,"bbox":[120.999,30.999,121.004,31.002],"objects":[{"id":"g1","kind":"green_center","latitude":31.001,"longitude":121.003}]}]}}
```

此坐标为合成数据，不代表真实球场。bbox顺序西/南/东/北；本版最多18洞、每洞100个参考点。kind支持green_center、hazard_reference、landing_reference、ob_reference。障碍/OB参考点不是边界，不能用它裁定进区、OB、救济或算“越过障碍”的距离。图形拓扑、动态旗位、当地规则、供应商授权与真实地图校验均未接入。未来高差、果岭坡度保留不可用。

### GPS

```json
{"type":"gps","event_id":"gps1","observed_at":"2026-11-06T08:01:00+08:00","data":{"latitude":31,"longitude":121.001,"accuracy_m":2}}
```

这是设备观测，不自动等于球位。以精度形成保守经纬度矩形包络，完全落在单一球洞bbox内才可匹配当前洞；需精度≤30米、时间距接收不超过60秒且不超前5秒。多洞匹配保留候选，不给确定当前目标距离；迟到定位不倒退当前定位。

唯一匹配可更新当前洞号，不证明上一洞已经完成。首次默认不主动询问；用户明确说“换洞时提醒记分”后，可靠换洞且上洞缺分、无待答问题、未静默/准备击球时，只轻问一次。回答“五杆”绑定被问的上一洞，不误记到当前洞。无回应不重复催问；“不要主动提醒”关闭，“安静”持续抑制，“继续/恢复语音”才恢复。

“还有多少/还有多少米/还有多少码”当前仅计算设备位置到该洞唯一果岭中心的水平直线距离，返回origin=device_gps、target=green_center、carry=false，按米或码合理取整；不称旗杆距离、球位距离或实打距离。未实现绕障路线、障碍近远沿或本杆选杆。经纬度范围和矩形算法不支持跨日期变更线/极区。

### 语音转写

```json
{"type":"voice","event_id":"u1","revision":1,"phase":"final","observed_at":"2026-11-06T08:02:00+08:00","text":"这洞六杆"}
```

限定闭环示例：这洞六杆 → 这一洞几推？ → 两推 → 若par4则追问罚杆 → 没有罚杆/一罚/不清楚 → 复述含罚杆总分 → 确认 → 正式保存。可以直接说“一号洞六杆，两推，一罚”，归属指定洞而不倒退当前洞。

推数/罚杆可说“不清楚/跳过这一项”保持null；“先不记/取消记录/跳过这洞”取消待记流程。没有问到的罚杆不填0。报分只建立待确认草稿，不能由GPS或沉默补齐。总杆已含罚杆，推数+罚杆超过总杆不得提交。当前只记录罚杆数，不推定OB次数或处罚原因。

“撤销上一条记分/撤销刚才的记分”补偿本会话最后一次成功记分，保留地图、当前洞及独立后续事件；同字段有后续修改仍遵循核心冲突规则。“一号洞五杆”可重新提出该洞分数，不因旧分存在自动覆盖，仍需逐项和明确确认。

“我还是用了7铁，有点短，右边”等复杂描述目前保留证据并返回unsupported，不把它误作总杆，不改长期7铁能力。更丰富的语义适配器应产生候选并走歧义评估/确认层，不扩大本版语法匹配冒充通用理解。

## 冲突、失效与播报

地图或GPS更新按context.course_snapshot/context.device_position与原始证据依赖失效已有距离。当前设备位置与已确认球位仍分开；不记录未证实杆序、不拼造起落点、不把总位移当carry。

确认过程中有其他事件写入，旧聚合确认失效，适配器重新复述并要求再次确认，不自动绕过冲突。ASR修订使旧证据失效时也不能确认旧草稿，应重新报分。score_target保存被问球洞，实际当前球洞另存。

speak_allowed是响应时的基本静默/准备及版本检查，不能冒充实体耳机的最终投递保证。联调APP在地图/GPS样本提交时停止语音，前台识别把final送入接口；后台即暂停。自动定位流/真实耳机接入必须在播放前校验版本和依赖并按delivery_id去重，现有outbox原语可供接入，当前会话回复尚未全部走实体投递回执。

未实现：后台GPS、锁屏与耳机唤起、完整球场几何、供应商API、通用对话模型决策、生产身份/保留删除策略。协议和测试不能替代双端真机及18洞实地验证。
