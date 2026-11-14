# 中文先行的多语言数据流程

## 目的与现状

同一案例先定义中文上下文、用户话语、语义标签、预期状态变化、应采取的动作和回复约束；再建立英语、日语、韩语变体。各语言共享球童纪律，但分别核验表达。这里只准备数据、审核门槛与供应商中立JSONL导出，不调用付费接口、不修改模型权重、不自动收集用户对话。

首批9个合成情境、36个语言版本：实际用杆与意图区分、询距、没有罚杆、球杆修正、关闭教练、事实回答后的同意、不足Carry信息、短杆地图优先、天气缺失。中文/美式英语/日语/韩语各9份；en-GB尚无独立样本。所有版本均为待审核，初始可训练数量为0。不要把这些草案称为母语审核通过或职业球童认可的数据。

资产：`assets/training/golf-dialogue.jsonl`。工具：`scripts/training_data.py`。测试：`tests/test_training_data.py`。

## 一条案例的结构

| 字段 | 用途 |
|---|---|
| case_id / family_id | 案例身份与共享情境族；改写、翻译不能换族来逃避留出集 |
| split | 按family_id确定train / validation / test，所有语言同组 |
| provenance | 合成或真实来源、独立训练授权、去标识状态与依据引用 |
| semantic_target | 与球局协议一致的事件分类及语言无关槽位 |
| expected_state | 状态路径、equals/unchanged/unknown/not_created及预期值 |
| expected_action | 回答、澄清、记录候选、请求确认、提交、暂存或不变；最多一问 |
| reply_constraints | 不猜Carry、不把决定当执行等行为标准 |
| variants | 各语言上下文、话语、参考回复、翻译来源和两维审核 |

expected_state是评估标注，不是模型可直接执行的数据库操作。当前工具检查格式、共享标准和数据资格，尚未自动把这些路径断言绑定到实际引擎；原状态机另有自身测试。天气和短杆等语义标签也不表示国际化兼容适配器已经实现其全部槽位。后续模型仍只输出候选，由现有内核校验、归因及提交。

## 审核而非自动“通过”

每个语言版本分别维护domain和language两项审核：pending / approved / rejected。中文也需要球童业务及中文表达审核，外语另需相应语言合格审核者。每次approved必须记录非空审核者标识以及审核内容的SHA-256；更改上下文、话语、参考回复、语义、状态、行为约束或授权资料后，旧审核失效。

工具只校验记录和内容一致性，不能认证审核者身份或母语能力。生产审核界面应由有权限的人工审核者操作并记录审计，不能让模型自动填approved。当前没有自动批准命令。

人工审核步骤：

1. 检查整个情境及所有共享标签，区分建议、意图、决定、执行、结果、自述原因和修正。
2. 检查对应语言是否自然、数字与否定是否明确、最多一问及伙伴语气是否合适。
3. 对最终内容计算指纹；审核者在该语言版本的review内分别登记结果、身份标识和指纹。
4. 重新validate。若有任何内容修改，撤回旧审核，审核完成后再计算新指纹。

```sh
python3 -B skills/golf-caddie/scripts/training_data.py fingerprint \
  skills/golf-caddie/assets/training/golf-dialogue.jsonl \
  --case actual-club --locale zh-CN
```

## 授权与隐私

合成样本不取真实用户位置、过去经历、姓名或录音。已同意为球童保存资料不等于同意用于模型训练。

真实用户案例只有在training_permission=granted、具有consent_reference、privacy_status=deidentified_reviewed且有deidentification_reference时，才可能进入审核后的导出。引用应指向宿主真实的授权和去标识审核记录；不能编造依据。工具无法核验外部记录真伪，也不执行自动匿名化，真实数据导入需宿主工作流完成。

用户撤回授权后先更新来源登记并阻止新导出；已导出批次通过manifest追溯并撤回/重建。已训练权重不会被本工具自动删除影响，须按供应商能力和产品政策处理，不能承诺“立即忘掉”。原始语音、GPS与私密聊天不在此工具自动采集范围。

## 划分与导出

情境族经SHA-256固定划分，约80/10/10；小样本实际数量不保证精确比例，首批为7/1/1。更改标签和翻译不改变分组。新增同义改写必须复用原family_id，不能用新ID绕过留出集。

```sh
python3 -B skills/golf-caddie/scripts/training_data.py validate \
  skills/golf-caddie/assets/training/golf-dialogue.jsonl
python3 -B skills/golf-caddie/scripts/training_data.py report \
  skills/golf-caddie/assets/training/golf-dialogue.jsonl
# 审核通过后；当前种子数据会明确阻止导出，不写文件。
python3 -B skills/golf-caddie/scripts/training_data.py export \
  skills/golf-caddie/assets/training/golf-dialogue.jsonl \
  --locale zh-CN --locale en-US --locale ja-JP --locale ko-KR \
  --purpose train --split train --output /tmp/caddie-training.jsonl
```

训练输出含messages及追溯元数据；模型目标是candidate、action和reply_constraints，不输出可直接执行的状态补丁。该格式供应商中立，选定训练供应方后再适配其上传格式。当前只准备语义/行为监督任务，不代表陪伴自然对话或ASR已经训练。

评估可用 `--purpose eval --split validation` 或 `--split test` 导出带状态预期和参考回复的已审核案例。训练导出禁止validation/test。待审核、拒绝、授权撤回、隐私待处理的数据不出现在任何合格批次；没有合格记录时导出失败，不制造空训练集。

每批附manifest：原始数据文件SHA-256、输出SHA-256、记录数、情境族及用途/划分。文件已存在时不覆盖。正式训练前仍需检查语义近似重复，family_id不能自动识别全部跨族改写。

## 下一阶段验收

先扩大中文真实问题覆盖并审核标准答案，再由母语审核者扩展各语言独有说法、口音和表达。使用独立录音测试ASR；使用独立情境测试NLU和状态机；使用母语球手盲评策略、简洁度、分寸和陪伴语气。记录每种语言的准确率、误提交率、澄清负担及不应改变状态的保持率。

决定模型、供应方、预算与数据边界后才能发起实际训练。分别报告“数据已准备”“审核通过”“模型已训练”“独立评估通过”，不能互相替代。
