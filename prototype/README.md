# 电子球童三路输入联调原型 v0.1.7

这是独立联调构建：已把球场快照、GPS样本、语音转写接入带身份认证的球局状态机。预填数据均为合成样本。真实GPS供应商、地图服务、锁屏/耳机与生产部署尚未完成；不调用付费模型。

## 启动

```sh
python3 -B services/api/server.py --db /tmp/caddie-session-v016.sqlite
```

另开终端，使用Node.js 22.13以上（本次验证为24）：

```sh
cd apps/mobile
npm ci
npm run web
```

网页只提交转写，不请求麦克风。原生开发构建可接前台ASR，尚未真机验证。API默认127.0.0.1:8787；网页开发Origin支持localhost/127.0.0.1:8081。Android模拟器填写http://10.0.2.2:8787。仅用测试账号；不要暴露到公网。

## 一次闭环

1. 注册测试账号，创建或恢复同一球局ID。
2. 提交页面预填的合成球场，再提交合成GPS。
3. 输入“还有多少米”，返回设备到果岭中心距离。
4. 输入“这洞六杆”→“两推”→“没有罚杆”→“确认”。确认前无正式分数。
5. 查看状态；输入“撤销上一条记分”查看补偿结果。
6. 重启API后，同账号同球局ID恢复；/round-state的replay与snapshot一致。

当前联调APP不自动重试网络失败；丢失回执时先读取状态。开发者重试需复用同一operation_id和完整事件，不能生成新ID重复提交。账号令牌仅存在页面内存，刷新后需登录。旧/sync与voiceFlow保留作回归，不参与新页面记分，不重复写入。

## 测试

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
node --experimental-transform-types --test tests/domain.test.mjs tests/voice.test.mjs
cd apps/mobile
npm run typecheck
```

HTTP测试会在本机随机端口运行并自动关闭。本次API15项、旧客户端回归10项、TypeScript检查及Web资源导出通过；技能包另有136项内核/算法/会话测试。Web导出不等于原生安装或真机验证。

完整协议见docs/round-session-protocol.md。主技能包使用同一round_state.py、round_session.py、shot_evidence.py，发布时按字节比对。测试只使用合成地图、测试账号与临时SQLite文件。

GPS换洞现要求连续轨迹与下一洞发球区稳定停留；输入可选tee_bbox、green_bbox，见主技能GPS换洞协议。没有发球区几何时不自动换洞。
