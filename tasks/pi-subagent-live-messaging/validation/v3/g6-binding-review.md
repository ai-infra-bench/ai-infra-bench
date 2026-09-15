# G6 公开接口接入审查

对象：一次 v0.0.3 解题的最终补丁 `f9f34e0ecbe89779d258785db64e4f811d9b7d15b33263b8bcf7f6dc37a62f1c`。G6 正常结束后才读取其文档/schema 并编写适配，未给模型测试反馈。

文档 `packages/coding-agent/examples/extensions/subagent/README.md` 的 Parallel Team Communication 描述启用 `communication: true`、`tasks[].id`（也支持自动生成身份）、`team_members({})`、`team_send({to, text})`，广播地址为 `*`。

适配仅做以下操作：

- 把行为驱动中的 message 参数改名为 text。
- 把广播操作编码为 to: "*"。
- 无效输入采用该接口可表达的缺少地址、地址类型错误、空文本、文本类型错误。不会要求这个实现拒绝旧协议的 to/broadcast 参数组合。
- 接受明确 kind: error 的拒绝结果，或 Pi 自身的工具参数错误。成员身份、发送回执和发送者无需重写。

没有改写模型输入，没有调用 broker/IPC 内部接口，没有代替实现发送或接收。模型输入的完整性、顺序、私信隔离、下一轮时机，以及真实 API probe 的断言均复用预先建立的行为检查。

该 adapter 在首次评分前冻结。G6 使用内存 broker + Node IPC，与参考解的收件箱文件传输不同；测试通过与否由实际执行决定。
