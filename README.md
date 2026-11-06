# 电子球童 / Golf Caddie

面向业余球手的电子球童：球场与GPS信息、语音事件归因、可回滚记分，以及用户自愿开启的伙伴与教练服务。

## 项目结构

- `skills/golf-caddie/`：Skill v0.1.9、状态引擎、天气算法与205项测试。
- `prototype-v0.1.6/`：认证API、移动端原型、合成球场和GPS流程。
- `球场数据接入样本/东莞凤凰山-v0.1.1/`：WGS84用户确认、规范化数据、适配器及10项测试。
- `demo-local/`：无前端依赖的本地文字交互演示。
- `versions.json`：各组件独立版本；不是生产上线版本。

## 本地演示

需要Python 3，在仓库根目录运行：

```sh
python3 -B demo-local/serve.py
```

浏览器打开 http://127.0.0.1:8789，点击“自动演示一洞”。仅监听本机；模拟GPS、文字转写，不调用麦克风或真实定位。测试账号存入系统临时目录，不纳入Git。

## 测试

```sh
(cd skills/golf-caddie && python3 -B -m unittest discover -s tests -p 'test_*.py')
(cd prototype-v0.1.6 && python3 -B -m unittest discover -s tests -p 'test_*.py')
(cd prototype-v0.1.6 && node --experimental-transform-types --test tests/domain.test.mjs tests/voice.test.mjs)
(cd 球场数据接入样本/东莞凤凰山-v0.1.1 && python3 -B -m unittest -q test_sample)
```

Node.js使用24；Python建议3.12或以上。基线验证240项通过，CI会在提交及PR时重新运行。

## 版本管理

`main`保存已验证基线；后续改动使用`codex/`分支，经自动测试和PR审查后合入。组件分别递增版本，并更新`versions.json`及`CHANGELOG.md`。版本提交应同时包含代码、协议、测试和相应文档。已发布版本不原地替换。

目前没有生产级ASR、完整跨场用户画像或真实GPS实地验收。凤凰山样本坐标系已由用户确认WGS84，但实际精度与边界语义仍待验证。原始设计文档、历史ZIP、个人账号数据和密钥不在本次基线范围内。
