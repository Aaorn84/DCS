# 电子球童 / Golf Caddie

面向业余球手的电子球童：球场与GPS信息、语音事件归因、可回滚记分，以及用户自愿开启的伙伴与教练服务。

## 项目结构

- `skills/golf-caddie/`：Skill、状态引擎、天气算法与393项核心测试。
- `prototype/`：认证API、移动端原型、合成球场和GPS流程。
- `球场数据接入样本/东莞凤凰山/`：WGS84用户确认、规范化数据、适配器及10项测试。
- `demo-local/`：无前端依赖的本地文字交互演示。
- `versions.json`：各组件独立版本；不是生产上线版本。

## 完整流程演示

```sh
python3 -B demo-local/serve.py
```

打开 http://127.0.0.1:8791。可新建临时测试身份，或用固定测试账号注册/登录后恢复。同一账号从首次认识逐项问答，进入赛前、场中、结束、可选单点教练，最后开始下一场。支持“先打球，稍后了解”和“安静”。详情见技能中的complete-journey.md。

网页使用合成地图和模拟GPS、文字转写；手机App也接入同一个认证旅程API，原生前台语音待真机验收。阶段语义为确定性原型，不是完整自然语言模型；状态、记分与记忆实际持久化，不是静态聊天脚本。

## 测试

```sh
(cd skills/golf-caddie && python3 -B -m unittest discover -s tests -p 'test_*.py')
(cd prototype && python3 -B -m unittest discover -s tests -p 'test_*.py')
(cd prototype && node --experimental-transform-types --test tests/*.test.mjs)
(cd 球场数据接入样本/东莞凤凰山 && python3 -B -m unittest -q test_sample)
```

Node.js使用24；Python建议3.12或以上。基线验证299项通过，CI会在提交及PR时重新运行。

## 版本管理

`main`保存已验证基线；后续改动使用`codex/`分支，经自动测试和PR审查后合入。组件分别递增版本，并更新`versions.json`及`CHANGELOG.md`。版本提交应同时包含代码、协议、测试和相应文档。已发布版本不原地替换。

目前有授权确认资料的跨场档案，但没有生产级ASR、经过统计校准的完整画像或真实GPS实地验收。凤凰山样本坐标系已由用户确认WGS84，但实际精度与边界语义仍待验证。原始设计文档、历史ZIP、个人账号数据和密钥不在本次基线范围内。

文件与目录统一使用稳定名称，不附版本号；版本信息保留在SKILL元数据、versions.json和CHANGELOG。历史构建单独归档，当前交付位于dist。

## 本次同步

- 完整赛前、场中、赛后流程；地图点选模拟位置。
- 多轮语音区分建议、决定与执行；连续球位确认单杆总距离。
- 果岭周边和四向空间查询；短杆策略先查地图。
- 过障碍距离按当前位置与障碍轮廓求交，不复用开球固定顶点。
- 所有测绘来源数据目前只用于演示，不能用于真实击球导航；GPS位移不是Carry。
