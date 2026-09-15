# Pi 实时通信题：评分隔离修复验收（0.0.7）

已堵住这次复现的刷分漏洞：同一份“直接写满分后退出”的代码，旧版是 **0/18 通过、reward=1**，新版是 **0/18 通过、reward=0**。本轮只修改这道题的评分边界，没有改题面、参考功能实现或八份模型提交。

## 改了什么

- Pi 和它的子进程在加载任何候选源码、依赖或扩展之前，降为 UID/GID 60000，清空附加组并设置 `no_new_privs`。评分器单独以 root 运行。
- 评分 Python 使用 `-I`、固定解释器和受控环境，只从可信测试目录导入适配器。候选运行目录与评分文件分开。
- 候选不能写测试、中间报告或成绩；也不能通过杀评分进程、读写父进程内存或提权来绕过。上报的 PID 要核对 OS 身份，按候选 PID 清理进程时也先降权。
- 成绩先写 0；只有可信评分器完成全部 18 项且逐项通过，才写 1。奖励文件使用原子替换，同时处理 `reward.txt` 和 Harbor 优先读取的 `reward.json`。
- 评分期间保护中间结果。完成后将生成的结果设为 root 拥有的只读文件，让 Harbor 正常收集，不授予候选写权限。

## 实际验收结果

全部来自最终版本的真实 Docker / Harbor 入口；没有新增模型解题调用。

| 提交/反例 | 通过项 | reward |
|---|---:|---:|
| oracle | 18/18 | 1 |
| renamed | 18/18 | 1 |
| base | 3/18 | 0 |
| g6-1 | 18/18 | 1 |
| g6-2 | 18/18 | 1 |
| g6-3 | 18/18 | 1 |
| g6-4 | 18/18 | 1 |
| g56-1 | 17/18 | 0 |
| g56-2 | 17/18 | 0 |
| g56-3 | 18/18 | 1 |
| g56-4 | 18/18 | 1 |
| drop_accepted | 4/18 | 0 |
| duplicate_delivery | 4/18 | 0 |
| reverse_fifo | 17/18 | 0 |
| early_exit | 0/18 | 0 |
| forge_reward | 0/18 | 0 |
| tamper_boundary | 0/18 | 0 |
| delayed_forge | 0/18 | 0 |

G6 仍是 4/4，G56 仍是 2/4。G56 的两份失败提交仍只失败于 `ordered`：已经接受的两条消息没有一同进入下一次模型输入。提交 patch 和接口 binding 的哈希、得分均与 v0.0.6 逐项核对一致。

另外实际运行了保存在本目录的 `run_security_controls.py`：Oracle 通过，四种攻击全部被拒绝，5/5 回归检查通过。最终矩阵 18 次加回归脚本 5 次，共 23 次正式试验，均无 Harbor 基础设施异常。

权限探针记录：写成绩、改报告、改测试/适配器/fixture、读核心测试、替换成绩链接、打开评分进程内存均为 `EACCES`；杀评分进程和 `setuid(0)` 为 `EPERM`。实际 UID/GID=60000，NoNewPrivs=1。见 [原始探针](permission-probe.json)。

## 证据与复现

- [最终矩阵、精确 trial ID 与原始报告路径](hardening-results.json)
- [独立回归脚本的实际结果](security-regression-results.json)
- [冻结的执行文件哈希](artifact-hashes.json)
- [可重复运行的安全回归入口](run_security_controls.py) 和 [攻击补丁目录](security-controls/)
- 完整日志：`artifacts/pi-messaging-hardening-20260915/remote/`；旧漏洞日志保留在 `artifacts/pi-messaging-review-20260915/remote/`。

镜像未变：`sha256:95b13c4082432f20c58dda2919767637393dc0cb2374890c1e235ed71a036a87`。Pi Base：`71dca871bc80b6bc97be37f0ca3189399d651fff`。运行：CPU、4 核/8 GiB、离线，真实 Pi 进程和通信实现，脚本模型仅提供确定性输入；没有远程 LLM 调用。

第一轮试运行把导出的日志也设成了私有权限，导致 Harbor 收集时报 PermissionError。这 3 次不计入最终验收；原始结果单独保存在 `grades-before-export` / `grade-jobs-before-export`。修复只读导出后重新运行，最终结果没有沿用第一次的成绩。

## 范围与交付状态

这次验收针对已复现的评分文件篡改及相关同权限攻击链。保留原来 18 项行为契约，不以此宣称所有恶意程序或所有通信边界都已穷尽。完整发布审查仍保持 pending；本轮不是重做全部题面和轨迹审查。

仓库正式校验 `task_ci.py validate pi-subagent-live-messaging`、Python 语法和冻结哈希检查通过。通用 `audit_task_artifacts.py --strict-evidence` 仍未通过：它要求本题原先没有的 image/lock manifests、`solution/oracle.patch`、`validation/e2e-evidence.json` 等固定发布布局；这些既有发布材料问题未在本次评分权限修复中扩展处理。

工作区修改尚未提交或推送。其他题目未修改。文档/验收材料的补写不改变已冻结的执行输入。
