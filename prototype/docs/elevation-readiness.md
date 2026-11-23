# 高差数据预接入

本次为1.7开发中核心增加地形接口，策略政策版本4；不启用未经校准的弹道或滚动修正。冻结1.4/1.5/1.6不变。缺失数据沿用原水平几何、选杆与排序，不把未知海拔当成0米。

## 地图契约

Point可带elevation：value数值、unit固定m、datum海拔基准标识、source来源、accuracy_m垂直误差、verified确认标识。有效海拔范围-500至9000米；真实0米有效。手机GPS海拔不能未经核对混入其他基准。水平accuracy_m与垂直elevation.accuracy_m独立。

每洞可带terrain：schema=1、非空revision、samples数组。每个sample含point、elevation、support_radius_m（0至25米的实测有效覆盖半径）。最多2048点，超限不截断取部分，整组不参与；生产稠密DEM需后续采用空间索引适配。仅查当前洞，不扫描历史球局或完整球场。覆盖范围外不做最近点外推、不推断果岭坡度。示例：

```json
{"terrain":{"schema":1,"revision":"survey-2026-11","samples":[{"point":{"latitude":23,"longitude":113,"accuracy_m":0},"elevation":{"value":100,"unit":"m","datum":"local-survey-A","source":"survey","accuracy_m":0.5,"verified":true},"support_radius_m":2}]}}
```

可独立附带slope：gradient_percent坡度百分比、aspect_degrees下坡朝向（正北0、顺时针）、source、accuracy_percent、verified。当前仅定义及校验，不用于推杆、站位或滚动估计；起终点高差不能替代坡面数据。

## 统一接口

assessDistance返回horizontal_yards、elevation_change_m（目标减起点）、elevation_uncertainty_m（两端误差保守相加）、playing_distance_yards=null、correction_enabled=false。状态为missing、datum_mismatch或unvalidated。仅同基准且已核对的两端数据可计算高差；不套固定“每米加一码”公式。

全部开球、球道过渡、攻果岭、沙坑短打候选共用courseCandidates：distance_assessment对应实际Carry落点；remaining_distance_assessment对应落点至果岭参考点；obstacle_distance_assessments依次对应crossings的障碍远沿。总体方案distance_assessment对应旗位区域估算点，不能从果岭中心外推区域海拔。障碍高差不等于弹道净空；不能只凭远沿海拔宣布可以飞越。

已知高差的候选会提示升降及当前尚未校准，保持原水平距离建议。无高差数据不增加播报。推杆坡线、深草脱困、原位球位判断不使用端点高差推断。

## 离线与版本

现有地图打包深拷贝保留新增字段，包摘要覆盖整个地图；高差更新需发布新地图包及revision，不能原位修改已冻结球局地图。手机与网页共用接口；不增加网络请求。建议缓存按包摘要/球局/状态修订隔离，政策4使旧开发版建议失效；旧冻结核心不变。实际用杆记录仍按原水平几何计算，海拔字段不改变水平距离统计。

后续启用前须增加分杆型/弹道的校准模型、误差传播、坡面与滚动模型、空间索引及实际地图验收；通过新核心版本发布，不能直接修改既有球局的策略。当前没有制作假海拔或迁移测试地图。

## 性能验证

宿主darwin arm64、Node24.22.3，同一凤凰山四/五杆洞、资料齐全档案，每版本60次请求。接入前1.7冷输入p50/p95为3.467/4.312ms，接入后为3.585/4.850ms；热几何为0.928/2.106→0.921/1.983ms。冷输入含JSON解码和模型创建，热输入复用地图；非同进程交错采样，微小差异不能作为严格提速或退化结论，未见毫秒级明显退化。实机ASR、网络和TTS端到端未测。高差图数据补齐后须重新测量有数据路径，当前实测地图没有海拔数据。

最终回归：业务142、API111、客户端151项通过，共404项；真实Redis1项未配置跳过。新增测试覆盖缺失/零海拔、升降、基准不一致、无效数据、覆盖范围，以及修正关闭时选杆/落点/记录不变。冻结核心校验、严格TypeScript及语法检查通过。
