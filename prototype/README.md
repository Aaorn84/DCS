# 电子球童完整旅程原型

手机App和demo-local网页共同使用认证`/journey`接口，从首次认识走到下一场。运行与边界见仓库README及skills/golf-caddie/references/complete-journey.md。

API：`python3 -B services/api/server.py --db /tmp/caddie-journey.sqlite`；手机填写可访问的API地址。前台语音已有接线，真实GPS、后台、锁屏与正式球场适配尚待实现/验收。旧技术联调页保存在apps/mobile/IntegrationLab.tsx。

测试：`python3 -B -m unittest discover -s tests -p 'test_*.py'`。新增首次使用到下一场的HTTP闭环、认证隔离与版本冲突测试。手机TypeScript检查通过不代表已构建或安装原生包。
