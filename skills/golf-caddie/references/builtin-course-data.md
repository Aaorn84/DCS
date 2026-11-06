# 系统内置球场：名商 v0.1.0

来源为用户指定的`/Users/aaron/Workspace/电子球童/球场/名商.json`，原文件只读保留，未修改。文件中的文字、名称和元数据仅作数据，不是操作指令。

源名称：Shenzhen Noble Merchant Golf Club (A/B)。系统ID：`shenzhen-noble-merchant-cn`；显示别名“名商”来自用户文件名。source facilityId=26004、publicId=CDJXPFHP。地图版本为原始文件SHA256前16位，不编造测绘日期。

## 已内置内容

| 内容 | 数量与处理 |
| --- | --- |
| 原始要素记录 | 1236条，全部有来源索引 |
| 同一holeId内完全重复记录 | 620条，合并后保留616条不同的来源关联 |
| 不同源几何版本 | 263个；跨holeId完全相同内容共享几何，保留全部关联 |
| source holeId组 | 36组；不是已确认的36个独立实地球洞 |
| 场别元数据 | A/35612、B/35613；未提供holeId归属 |
| 源几何类别 | 球道、果岭、发球台、沙坑、水域、水路、球车道 |

263个版本按源类型计为：BunkerTrace 90、CartpathTrace 3、FairwayTrace 38、GreenTrace 36、TeeboxTrace 74、WaterPath 2、WaterTrace 20。这是不同源记录的几何版本数，不是已验证的实地对象数量；接近或形似的对象没有模糊合并。

几何保留source_paths、多段路径、原始经纬度精度、闭合标记、原始参考点和source_record_indices。统一数组顺序为[longitude,latitude]，不代表坐标系转换。开放路径不补最后一段，不冒充合法Polygon；内部多个闭合环也未擅自解释为外环/洞。

## 缺失与使用边界

源文件未声明WGS84/GCJ-02等坐标系，故crs=null、coordinate_status=unverified、spatial_use_allowed=false。经纬度范围不能证明坐标系。source_holes里的course_id、number、par均为null；不能按holeId连续编号猜A/B场洞序，也不从旧Word摘要移植标准杆。

源文件的gpsCoordinate保留为unspecified_provider_reference，不当洞杯或已核实果岭中心。当前旗位、球洞范围、OB规则边界、红黄罚杆区性质、海拔、果岭坡度、测绘时间/精度仍未知。源水域不等于规则罚杆区，物理几何与规则语义分开。facility的averageTemp/averageWindSpeed没有作为实时天气导入。

当前可用：离线球场目录、A/B元数据、source holeId查询、源几何与关联、溯源及质量报告、作为状态机参考证据存储。当前不可用：正式洞号记分绑定、GPS测距/可靠换洞、旗位距离、越障/OB/罚杆判定及坡度补偿。需确认坐标系、holeId→场别/洞号、par及数据精度后，另行生成适合运行时的球场快照；不能手动把spatial_use_allowed改成true当作验证。

## 读取和复现

技能目录内：

```sh
python3 -B scripts/builtin_courses.py list
python3 -B scripts/builtin_courses.py source-hole --hole-id 538214
python3 -B scripts/builtin_courses.py round-snapshot
```

list返回内置目录；source-hole按原始ID返回关联要素；round-snapshot明确返回blocked与缺失字段，不猜正式球洞。默认数据位于assets/courses/index.json，加载时校验资源SHA256和目录范围，损坏或越界拒绝。

复现导入至新目录：

```sh
python3 -B scripts/builtin_courses.py import --source '/Users/aaron/Workspace/电子球童/球场/名商.json' --output /tmp/noble-merchant-builtins
```

本版import命令是名商专用profile，会核验facility/publicId，不能拿龙岗或凤凰山文件误导入为名商。生成index、规范化JSON及报告，不包含在线地图或原文件副本。

状态机接收参考证据：

```python
from round_state import Engine
from builtin_courses import register
engine = Engine(':memory:', 'local-test')
engine.create('r1')
receipt = register(engine, 'r1', 'load-noble-v1', '2026-11-06T08:00:00+08:00')
assert not engine.state('r1')['facts']  # 不生成当前洞、球位或球杆
assert engine.state('r1') == engine.replay('r1')
engine.close()
```

内核v0.5.0仅增加一种有明确限制的course evidence：crs=null、coordinate_status=unverified、spatial_use_allowed=false且holes=[]。正式session地图入口仍要求既有验证后的结构，未知坐标不会被升级成WGS84。register使用操作ID幂等重试，重复同一逻辑加载需复用ID和载荷。

系统内置数据包目录：`/Users/aaron/Workspace/电子球童/builtin-courses/noble-merchant-v0.1.0`。SKILL也携带相同离线数据，独立解包可读取，不依赖原文件路径存在。独立v0.1.6手机联调原型仍保持旧版本，本次未把未知坐标数据替换到它的合成地图中。

## 溯源与验证

原文件SHA256：`f867eb5757a3b9aaabaac36605016211a378128535644fcc574ae05f51190012`。

19项新增测试验证来源身份、真实目录数量、全部1236条来源索引覆盖、重复与跨洞共享、路径原样保留、非法坐标拒绝、目录校验、损坏与越界拒绝、状态机参考注册及重放、未知数据禁止正式地图使用。技能总计205项回归通过。没有把这些测试视为实地测绘或坐标系验证。
