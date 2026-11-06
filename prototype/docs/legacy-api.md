# 开发API契约

所有接口返回JSON。服务默认监听127.0.0.1:8787。非公网生产服务。

| 方法 | 路径 | 输入/输出 |
|---|---|---|
| GET | /health | 无需鉴权；返回stage、provider、mapReady=false |
| POST | /auth/register | email、password（10—128字符）；返回token、user |
| POST | /auth/login | 同上；失败统一错误，避免区分账号不存在与密码错误 |
| POST | /auth/logout | Bearer令牌、空对象；撤销当前令牌 |
| GET | /records | Bearer令牌；仅返回当前用户全部记录及删除标记 |
| POST | /sync | Bearer令牌；单条变更操作，返回确认记录 |
| POST | /chat | Bearer令牌、message；返回text、provider、label |

同步输入：operationId、kind（profile/club/memory/round）、id、baseVersion、deleted、data。用户身份仅从Bearer令牌确定，不接受客户端指定用户覆盖权限。服务端数据按用户＋kind＋id唯一。

新记录baseVersion=0，每次接受变更版本加1。同一个operationId及内容重传返回原结果，不重复写入；ID复用但内容变化返回409。版本不匹配返回409及current，客户端暂停上传，让用户决定用云端还是本地；保留本地时清理同一记录的旧待办，并以云端版本重新排队。

删除写入空内容的永久删除标记，不能以普通更新恢复；重新创建需新ID。历史操作回执中该记录的结果同步替换为删除标记，避免旧操作重试再返回已删除文本。冲突current为删除标记时只能采用云端。

比分每洞可为null，表示尚未记录。有效比分为total/penalty/putts，total为整数，penalty/putts可为null（未知）或整数，total已经包含penalty，且已知penalty+putts≤total；当前开发版每洞总杆1—30。球局状态active/finished，结束允许不完整记录并明确标注。当前不根据par计算相对成绩。

服务只允许本地Web预览Origin访问CORS；原生App不受浏览器CORS机制影响。Authorization令牌有效30天，服务端只存其哈希。生产上线前需加入TLS、速率限制、身份恢复、账号注销、审计与数据库迁移。

/chat支持可选history（最多8项，仅user/assistant及text），以及当前设备context（校验后的profile、clubs与确认memories）。context是当前用户提供的资料，不是特权指令，也不能指定其他用户。无需先完成记分同步再聊天。
