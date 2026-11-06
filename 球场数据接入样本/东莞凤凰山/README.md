# 东莞凤凰山｜球场数据接入样本 v0.1.1

本包提供可复现的来源适配器、规范化目录、18洞路线配置示例、质量报告及自动测试。原始球场文件不作修改。本包是数据接入参考，未对GPS App正式接口或现有球局引擎作修改。

## 使用

需要 Python 3，无第三方依赖。在本目录运行：

```sh
python3 -m unittest -v test_sample
python3 import_course.py '/Users/aaron/Workspace/电子球童/course/东莞凤凰山.json' --output regenerated
```

第二条命令从原文件重建三个JSON。不同来源文件请新增适配器，当前适配器只接受凤凰山 publicId。包内测试不依赖原始文件。

## 文件

| 文件 | 用途 |
| --- | --- |
| data/course.normalized.json | 三个9洞场别、球洞身份、发球台逐洞事实及原始路径 |
| data/route-ab-blue.example.json | A蓝台＋B蓝台的18洞组合示例：72杆、公布长度6388码 |
| data/quality-report.json | 来源哈希、统计与未解决项 |
| import_course.py | 标准库实现的来源检查、关联转换和质量检查 |
| test_sample.py | 关联、顺序、缺失证据、拒绝错误输入和文件完整性测试 |
| manifest.json | 包内交付文件的SHA-256校验值；不包含自身 |

## 字段映射与身份协议

| 原字段 | 规范化字段 | 处理规则 |
| --- | --- | --- |
| publicId / facility | source.public_id / facility_raw | 保留来源身份和设施元数据；设施平均天气不是实时天气 |
| courses[].courseId / name | courses[].course_id / name | 保留A/B/C独立场别 |
| tees[].teeId / teeName / teeColorType | tees[].tee_id / name / color | 以tee_id识别，C场两套Blue不合并 |
| tees[].holes[].holeId | holes[].hole_id及逐台holes[].hole_id | 用ID关联根球洞、逐台记录、地理记录 |
| tees[].holes[].holeNumber | source_hole_number | 按源洞序排序，不能按holeId排序；B8=475531 |
| tees[].holes[].par | 逐台par及球洞par | 跨台一致才提交；根par=null不能覆盖有效值 |
| tees[].holes[].yardage | published_yardage | 来源字段名表示码，未独立核验单位；公布长度不等于GPS距离或carry |
| allocation | allocation_raw | 保留原始场别语义，不拼成18洞差点分配 |
| teeGPSCoordinate等 | reference_coordinates | 来源参考点，非实际球位、动态旗位或各色实际发球位置 |
| data[].gpsType / shapes | geometry_records[].source_type / source_paths | 保留171条关联记录、394段路径，不合并共享几何、不自动闭环 |
| updateOn / updatedOn / holeDataStats | *_raw / data_stats_raw | 分层保留时间，timezone=null；无时区的时间不能擅加Z |

规范化事实的 `source_path` 为原始JSON中的JSON Pointer。球洞par来自所属场别各台的对应逐洞记录，`par_basis`说明一致性规则；根记录路径只定位根事实。`source.sha256`绑定具体输入版本。单台总杆与总长度必须与逐洞合计一致；孤立引用、重复洞序、身份/标准杆冲突均拒绝导入。

## 样本结果

- 3个场别、27个物理球洞、13套发球台、117条逐台逐洞记录。
- A场36杆、B场36杆、C场35杆。C蓝台有Blue (A)、Blue (B)两种。
- 171条地理记录、394段路径、23,640个顶点。记录包括球道27、HoleBoundry27、水体27、发球区27、沙坑26、果岭27、植被1、车道9。
- 路线示例显式选择teeId 650688和650692，round_hole_number与来源场别洞序分开保存。它是接入配置示例，不代表官方组合、用户已选路线或实际打过的球局。

## 接入边界与下一步

**当前可接入：** 球场目录、场别和发球台选择、标准杆记分、公布长度展示、原始证据查询。运营方确认路线后才能作为真实开局配置。

**坐标系确认：** 用户于2026-11-06明确确认本文件使用WGS84。`coordinate-confirmation.json`记录确认来源、日期和原文件SHA-256；导入时必须匹配文件版本。原文件未改写，也未进行坐标转换。无匹配确认时，转换函数仍保留未知坐标系。

**可开始验证：** `crs=WGS84`、`coordinate_status=user_confirmed`，`reference_point_distance_enabled=true`，可在同为WGS84且定位精度满足要求的条件下进行参考点距离计算与联调。距离只表示到来源参考点的距离，不等于到当天旗杆的距离。本包尚未实现或接通正式App测距接口。

**尚未开放：** `coordinate_accuracy_status=not_field_validated`；`spatial_use_allowed=false`保留为整体生产空间功能开关，`polygon_operations_enabled=false`。障碍避让、围栏换洞及正式上线仍需路径语义和现场精度验证。坐标系确认不等于位置精度或拓扑验证通过。本包不是现有round_session空间地图协议的直接输入。

上线空间功能前，需进一步确认路径闭环/内环约定、彩色发球台实际点位、动态旗位来源和更新机制，并用现场已知点校验。所有路径保留原样，不标作已验证GeoJSON Polygon。HoleBoundry不是已确认OB；水体不是已确认红/黄罚杆区。B8缺少沙坑记录只能记为未提供，不能断言无沙坑。

目前无球道高差或果岭坡度；tee层slope是球场难度评级字段，不是果岭坡度。球场参考点不能补成用户真实击球起落点，也不能推断球杆或carry。用户语音、设备GPS和测绘数据应分别保留来源并由球局状态引擎处理冲突。

测试仅验证数据适配和包内一致性，不代表测绘精度、正式API接通或实地验证通过。

## v0.1.1变更

根据用户确认补充WGS84坐标系及版本绑定证据，移除“坐标系未知”阻塞原因；保持原始坐标、几何路径及旧版交付包不变。新增确认版本错配拒绝测试。
