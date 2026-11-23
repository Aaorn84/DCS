# 国际化接口与验收

## 当前边界

共用原球局状态机，新增 `international_event` 协议2及认证后的 `/international` 接口。不是四套独立SKILL。中文 `/journey` 新事件采用协议37，协议32及更早历史回放不变。国际化测试聚合独立于中文演示，避免切换语言破坏已有测试记录。

可运行的是语义接口、地区配置、有限外语输入样例、完整结构化球局及回放。不是海外商业上线版本。英语、日语和韩语的任意自然语言理解、完整回复本地化、真机ASR/TTS、海外球场覆盖及区域生产部署仍待接入与验证。`capabilities` 必须如实返回此状态。

## 独立地区配置

测试页默认中文，保留英语、日语、韩语切换；登录后显示账户保存的语言，选择语言后点“保存语言与单位”生效。中文询距样例可直接发送。

当前用户设置只显示语言与距离单位，不询问市场或时区，也不在测试状态面板展示这两项。保存设置和运行流程只提交语言、距离单位。接口已有的market_region、timezone字段保留用于历史回放兼容，未填写时沿用内部默认值；它们不是用户必填项。事件时间戳仍包含时区，不依赖用户设置。

`configuration`（包含保留的内部字段）：

| 字段 | 接受值 | 意义 |
|---|---|---|
| locale | zh-CN / en-US / en-GB / ja-JP / ko-KR | 输入、回复与声音语言；未知语言明确拒绝 |
| market_region | US / EEA / UK / JP / KR | 产品市场配置，不自动判断法律适用性 |
| distance_unit | yd / m | 默认码，用户可改变 |
| temperature_unit | C / F | 独立温度偏好 |
| wind_unit | m/s / mph / km/h | 独立风速偏好 |
| timezone | IANA时区 | 显示偏好；事件时间仍必须含时区 |
| data_region | null / US / EEA / UK / JP / KR | 部署意向，不代表实际存储已迁移 |

默认值用于开发，不证明用户所在地区。切换语言不自动切换单位或市场。欧洲首发国家及语言需明确后再增加；en-GB不是“欧洲所有语言”。温度/风速配置目前保存在接口中，尚未连接天气显示层。data_region当前不执行数据库路由。

## 标准化事件

宿主提供：`protocol_version:2`、稳定 `event_id`、含时区 `observed_at`、输入类型及数据；认证账户来自宿主，不能从事件指定owner。标准化候选结构：

```json
{
  "type": "semantic",
  "event_id": "voice-001",
  "observed_at": "2026-11-08T09:00:00+09:00",
  "candidate": {
    "type": "execution_report",
    "slots": {"club": "7i"},
    "confidence": 0.96,
    "alternatives": []
  }
}
```

球杆使用 `driver / 3w / 5i / 7i / pw / putter` 等标识，不保存为各语言别名。原始对话或外部候选完整留在事件日志中，兼容适配器再转换为既有内核输入；不可绕过内核直接写事实。

已接入：fact_request（distance / strategy / previous_distance）、player_intent（conservative / attack）、decision_commitment、execution_report、score_report、state_transition、interaction_override、profile_answer、confirmation。数值、字段、枚举和当前待答问题均有校验。

profile_answer每次一个槽位：memory、name、proactive、shot_recording、number、miss、course、tee、goal、condition。number仅在当前Carry或开始球洞问题中有效，不能替代推杆数等其他待答问题。用户声明Carry仍是自报，GPS位移不得转成Carry。

shot_outcome / feel_or_cause / correction / companion_dialogue 保留标准分类，但本国际化兼容适配器尚不接收这些类型的状态提交，明确报错；原归因引擎仍存在，后续应通过有版本的语义适配器接入，禁止把它们降级成决定或实际执行。候选解释改变球杆、归属、策略或事实时只澄清一题，未回答不提交。

### 输入适配

- semantic：用于宿主模型输出，先校验再提交。
- utterance：仅有限样例解析；例如 How far? / 残り距離は？ / 얼마 남았어?。见脚本PHRASES；未知表达不传给中文口令解析器，不冒充任意NLU。
- configure：保存独立配置。
- resume / gps：复用已有旅程与定位约束；定位不生成击球。

语义接口使用同一Engine事务、owner隔离、expected_version、追加事件和重放。重复event_id同内容无动作，不同内容拒绝。API客户端断网重试必须保留原operation_id与event_id。通用同意仍由最新有效问题拥有，不确认挂起的旧决定。

## 输出与语音

`result`保留语义候选、处理状态、text、speak_allowed、审计用source_text。配置确认和未知输入提示有本地化资源；其他未适配回复返回 `translation_required` 且禁止语音播报。source_text用于测试和审计，不直接给外语语音播放。不要宣称整个回复层已翻译。

原生useVoice支持独立locale参数和球杆词汇提示。切换语言先停止旧聆听；锁屏仍不宣称可用。现有中文App默认不变。`InternationalClient`对接新接口，业务UI不应把旧中文对话入口切换为外语识别后继续提交旧解析器。

## 球场、供应商与区域生产接入

球场宿主继续提供已有WGS84、course_id、map_version及来源；授权、更新时间、实地精度、球洞/发球台/障碍覆盖由真实供应方验证。现有合成/凤凰山数据不能充当海外覆盖。未来高差、果岭坡度缺失保持不可用。

生产接入分别评估ASR/LLM/TTS/天气/球场供应方的地域可用性、延迟、数据使用与保留条件；不得通过locale自动选择跨境处理方。用户长期记忆意愿、当前球局必要记录与模型训练授权分别处理。

上线前还需：生产认证与HTTPS、备份恢复、限流/监控、并发验证、数据保留与删除/导出流程、处理商清单、跨境处理机制、商店发布与订阅。PostgreSQL存储和地区配置不是上述能力的替代品。此文是工程验收边界，不是法律合规认证。

## 验证与运行

```sh
python3 -B skills/golf-caddie/scripts/international_demo.py --locale ja-JP
python3 -B -m unittest discover -s skills/golf-caddie/tests -p test_international.py
# 在prototype目录运行HTTP测试：
python3 -B -m unittest discover -s tests -p test_international_http.py
```

离线演示使用合成时钟、内存数据库，不访问用户球局。覆盖语言配置、首次使用/跳过认识、赛前、开局、询距、实际用杆、记分确认、教练关闭、结束球局和历史回放。多语言语义流程相同不代表自然语言质量或当地实战效果已经合格。

母语球手验收需另建录音与人工标注集：口音、数字、否定/更正、意图与实际执行区别、混合语言、含糊指代、打断、低信噪、陌生球场和断网。商业上线的验收应包括当地实地18洞，不以当前中文回归测试数量替代。

协议1解析已冻结于international_legacy.py，保留历史回放；协议2增加中文询距等有限样例，不重解释旧事件。
