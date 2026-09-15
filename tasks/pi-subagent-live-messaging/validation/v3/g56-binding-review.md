# G56 公开接口适配审查

对象：独立解题最终补丁 `19220b33e22663cdd2fdf8f122171b12b61d00939dae64e03e43c647b844af1f`。模型正常结束后冻结补丁，再按公开 README 和工具 schema 编写适配器，首次评分前冻结。

启用方式仍为 `communication: true`，任务可用 `id` 指定身份。适配只处理：

- `team_members` 调用映射成 `team_list`；返回的 self 对象和 teammates 列表映射成 self ID 和完整成员列表。
- 私信调用把 `to` 改为 `recipient`；成功布尔值和 recipient 映射成 accepted 列表，失败 error 映射成 reason。
- 广播调用使用单独的 `team_broadcast`，失败条目的 recipient/error 映射成 id/reason。
- 无效输入检查缺少地址、地址类型错误、空文本、文本类型错误；不强制拒绝旧接口的广播参数组合。

适配不读取内部队列、不替实现通信、不改写模型上下文、不改变并发度。原始模型请求和返回值均保留。18 项测试的四个源文件与 G6 正式运行逐字节相同。
