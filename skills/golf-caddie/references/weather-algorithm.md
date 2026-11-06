# 风温湿度混合模型 v0.1.1

入口：[weather_engine.py](../scripts/weather_engine.py)，混合算法：[weather_hybrid.py](../scripts/weather_hybrid.py)。纯Python标准库，直接接收原始天气；不需要外部传“调整几码”，也不需要球速、起飞角或旋转。旧的简化弹道原型仍保留为显式research模式，说明见 [旧弹道原型](weather-physics-legacy.md)，不冒称完整三维模拟。

此版本交付代码、测试与参数校准提案流程，尚非已实场发布的选杆引擎。输出是标注的估算范围，recommendation_allowed仍为false；不能删掉标记或把中点当精确码数。技能的专业判断、静默与比赛边界照常适用。

## 输入与有效性

JSON样例：[weather-hybrid-example.json](../assets/weather-hybrid-example.json)，数值均为合成演示。

- mode='hybrid'；rules_mode必须practice或informal；正式比赛/未知模式禁用补偿。
- 目标：target_distance、distance_unit='m'/'yd'、target_bearing_deg（真北顺时针）。缺方向时拒绝补偿，不能默认向北。高度差当前未实现，非空传入直接拒绝；未知高差显示不可用。
- weather：temperature_c、relative_humidity_pct（0—100）、wind_speed_mps、wind_from_deg、可选wind_gust_mps、source、observed_at（含时区）、可选station_pressure_pa与pressure_kind='station'。
- max_weather_age_seconds由APP明确配置；未来/过期数据拒绝数值补偿。各字段的来源、采样地点/高度与时效由适配器核验；源站统一时间戳不能冒充每项独立观测时间。
- profile：club_id、flight_group、ball_id、distance_type='carry'、baseline_carry、distance_unit、source、baseline_id。
- baseline：具有reference_id、来源和观测时间的明确基准天气；必须与profile.baseline_id相符、为静风，且观测时间不得晚于本次估算。carry可以是明确标注的自报初值，GPS起终点总距不能代替它；基准环境不明时先核实，不重复叠加已包含的当天影响。
- 可选weather_scenarios：最多24套完整天气，供方向变化、阵风等敏感性计算；代码只使用提供的数据，不编造未知风向范围。

当前混合近似域为温度-10至45°C、当地气压60至110kPa、风/阵风0—10m/s、目标与候选杆基准carry比0.65—1.35。以上是工程拒绝外推边界，不是准确性认证。若某个情境超域，拒绝整次估算而非悄悄去掉坏情境。API适配要把km/h、mph、hPa等正确转成SI，区分风来向与去向、静风/未知、站点/海平面气压，之后无需重写算法。

## 1. 空气密度：温湿度只联合计算一次

15—27°C、60—110kPa内实现CIPM-2007的湿空气摩尔分数、饱和水汽压、增强因子、压缩因子和密度公式，CO₂明确假设400ppm。超出其推荐温度域时，切换为标记的理想湿空气/NWS近似，不继承计量级精度声明；物理公式与常数来源见 [NIST所载CIPM-2007原文及附录A](https://www.nist.gov/system/files/documents/calibrations/CIPM-2007.pdf)。

没有当地气压时，按本版用户要求使用101325Pa标准气压；provenance标pressure_assumption=true，confidence降为low，并保留假设原因。显式传入的海平面修正气压不能当站点气压，必须拒绝而非误用。

标准气压只是为了有标记的初期估算，不代表海拔为0或本地真实压力，也不证明范围覆盖高原误差。当前/基准任一侧用了假设都提示；当前高度信息未知不做高度修正。以后有实际站点气压直接替换，无需改公式。

## 2. 混合算法：非对称风系数＋密度响应

设D为目标水平距离，B为所选球杆在明确静风基准条件下的carry，rho0/rho为基准/当前空气密度，beta为密度响应指数。

```
delta = wind_from_deg - target_bearing_deg
forward = -wind_speed * cos(delta)   # 正顺风、负逆风
left = wind_speed * sin(delta)       # 正向左漂
H = max(-forward, 0)
T = max(forward, 0)
F_density = (rho0/rho)^beta
F_wind = 1 - k_head*H + k_tail*T
F = F_density * F_wind
当前预计carry = B * F
基准等效需求 = D / F
候选球杆侧偏 = B * F_density * k_cross * left
```

距离与横向分开。侧偏估值指候选杆按基准打法打出的漂移，不自动等于所需瞄准偏移；改变瞄线、弹道或发力会改变条件。模型不描述横风造成的全部纵向效应，不仿真转速、阵风时序、风切变或地面滚动。

阻力受空气密度和相对风速影响是物理依据，参见 [NASA阻力方程](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/modern-drag-equation/)；它不提供本模型的高尔夫系数。逆风影响往往大于同速顺风的例子参见 [TrackMan官方Normalization说明](https://www.trackman.com/ko/blog/golf/normalization-feature-explained)，不能将其职业六铁例子当所有人的统一倍率。

### 初始区间：透明工程先验，不是实测常数

| 参数 | 本版初始范围 | 单位 |
|---|---|---|
| k_head | 0.008—0.018 | 每m/s的carry响应比例 |
| k_tail | 0.003—0.008 | 每m/s的carry响应比例 |
| k_cross | 0.003—0.010 | 每m/s相对B的侧偏比例 |
| beta | 0.3—0.8 | 无量纲密度响应指数 |

这些范围是可配置、待实测校准的保守工程假设，**不是从上述三份资料中拟合出的通用定律，不保证包住真实结果**。代码默认来源标engineering_prior_not_field_calibrated，低置信；不可写成“NASA算法验证”。方向非对称性是结构约束，初期不是精确识别。没有自己的carry时不会偷偷套职业距离。

## 3. 范围与对称归因

对系数区间端点组合，以及名义天气、提供的情境、同方向阵风速度分别计算，合并得到范围。展示端点向外取整至一码/一米，原始浮点值只用于审核。阵风没有新方向观测时明确按同来向处理；缺阵风标记缺失，不把它当零或认为预测完整。有限情境不是全风场模拟，更不是80%/95%置信区间，未输入个人散布与气压假设误差不在包络内。

温度、湿度不分别用固定“每度/每百分比几码”相加。实际算一次联合密度，再对完整模型的压力、温度、湿度、风四因素做精确Shapley对称分解（16个组合值），平均各种进入顺序的边际变化。这样温湿交互不会重复叠加，原始D＋四项归因＝名义模型需求。

Shapley只是解释账本，不是额外修正，也不是独立物理因果效应。归因解释的是中点系数/名义天气模型，不是区间每个端点。输出保留未四舍五入值并校验一致性；UI需单列展示舍入差或统一规则，不用一两码伪精确。side drift不加进纵向距离账本。

## 4. 个人系数：有约束地渐进替换

propose_calibration(training, validation, profile, baseline)已实现；通过入口JSON action='calibrate'也可调用。数据必须同club/ball/flight、相近球位、已确认carry、明确单位及天气，每条包含shot_at并检查天气早于该次击球且在30分钟工程时效门槛内，不收GPS含滚动总距。标定样本须独立确认起终点无高差，当前没有该条件就暂不以这些样本替换参数。

训练/验证样本ID不得重复，球局不得交叉；初始工程覆盖门槛为训练至少24条/3场、验证12条/2场，各有逆风、顺风、静风机会（静风按实际风速小于0.5m/s判断，不能拿纯侧风充数），密度比至少覆盖2%。这些只是防少样本/不可辨识的最低门槛，不保证统计可靠，也不要求用户每杆上报。

算法对beta做有界网格搜索，对顺逆风系数做约束最小二乘，再按n/(n+30)向原系数收缩。候选须在独立场次carry MAE相对原参数改善至少10%，否则保留原先验。侧偏必须另有已确认横向观测与独立验证（至少12条训练、6条验证并有改善）才可变更；没有侧偏数据不能从纵向结果“学出”侧偏。

输出仅为personal_candidate_pending_release提案，不写文件、不自动替换、不发布。提供样本ID、基准关联、误差前后、收缩权重与版本，维护流程可审核/撤销，用户授权的自动统计也不能跳过模型发布验证。训练与持留验证切分、参数收缩强度和通过阈值均为工程政策，不称贝叶斯后验或统计置信认证。换杆、换球、换弹道需分组；一次好球或使用场数本身不触发升级。

## 5. 运行与接入

从技能目录运行：

```sh
python3 scripts/weather_engine.py assets/weather-hybrid-example.json --as-of 2026-11-06T07:00:00Z
python3 -m unittest discover -s tests -p 'test_weather*.py' -v
```

--as-of仅为明确历史回放；实时调用不用它，按当前UTC检查时效。代码接入：

```python
from scripts.weather_engine import calculate
result = calculate(request)  # request.mode='hybrid'
```

也可直接调用weather_hybrid.calculate。旧mode='research'/'atmosphere'仍走旧原型，便于回归；旧原型严格要求站点压力，不继承混合模型的标准气压退化路径。mode必须明确，不能静默从受限模式切到可算模式。

当前版本已完成算法与合成测试，API实际供应商、个人实测数据、后台事件和APP语音/屏幕接线仍未接通。合成样例只证明实现可运行；发布前还需实场carry、侧偏与不同风温域的独立验证，不能把测试通过当成准确率背书。


## v0.1.1测试先行修复

本版修复一码显示误差、纯侧风误计静风覆盖、未来基准天气、未知系数键与非法时钟输入。新增可复现版本包与SHA-256清单，过程与运行结果见 [本版验证报告](validation-weather.md)。
