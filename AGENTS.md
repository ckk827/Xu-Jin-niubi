# 宿伴 Soulband 项目导航

## 用户约束

1. 禁止未经用户审核确认的脚本批量删除文件。本轮整理不删除文件。
2. 每次任务结束，用简短直白的语言总结本次工作。
3. 用户要求生成图片时，优先使用 image2；不可用时如实说明。
4. 数据和步骤须有依据；猜测必须明确标注，不能编造测试结果。
5. 提出大改建议时说明可能产生的问题。
6. 对明显不妥的决定说明原因，由用户决定是否继续。

## 项目与落点

- `soulband-demo/`：Python 宿主服务、Windows Qt 入口和手机适配网页。
- `soulband-android/`：Kotlin 原生业务、采集、配对与提醒；v0.4 已补齐业务入口，iQOO 真机待测。
- `开始测试_宿伴_v0.4_2026-11-08.md`：新交付启动与手工验收入口；`output/release-2026-11-08/REPORT.md` 为本轮证据索引。
- `output/windows-v0.4.0-tls/Soulband-Windows/`：成员客户端 exe 与依赖，分发须复制整个文件夹；源码仓库不包含构建产物。
- `docs/decisions-soulband.md`：按编号保留的决策、历史场景及当前待定事项。
- `soulband-demo/README.md`：当前启动入口与检查命令。
- `soulband-android/README.md`：Android 构建、安装和 iQOO 12 待测清单。
- `soulband-demo/CHANGELOG.md`：版本变化。
- `soulband-demo/TEST_REPORT.md`：历史验证记录，不自动等于当前测试结果。
- `output/apk/`：v0.3 与 v0.4 调试安装包均保留；新版本另存，不覆盖历史包。

## 业务约束

- 公约须经相关成员确认；草案修订不继承旧确认。
- 活动判断与提醒决策属于模型职责，默认模拟模式不得冒充真实模型。
- 设备活动不是睡眠、噪声或违规证据；缺数据或过期时保留未知。
- 原生采集与模型模式独立；手机接口契约测试不能冒充真机测试。
- 宿主本机可切换演示身份；局域网成员通过配对凭据固定身份，不能信任调用者传入的成员编号。尚未配置密码账号、找回和公网 TLS。
- Windows 宿主只采集所在会话；成员电脑须运行已配对客户端。每人一个电脑摘要槽，不能声称已做多台物理电脑实测。
- 模型优化为活动与提醒两阶段；探索集已见过，不是独立盲测。程序拦截不能算成模型原始输出正确。

## 维护入口

- 服务端成员查找：`soulband-demo/members.py`；保留各接口原有错误提示。
- 授权入口：`soulband-demo/access.py`；业务补全：`business.py`；Windows 成员设备：`pc_api.py`、`peer_desktop.py`。
- 服务端默认策略参数：`soulband-demo/policy.py`。Windows 与 Android 过期时间不同；不要将窗口配置合并成同一个运行值。
- Android 端采样节奏与服务端配对返回值需一起检查；v0.4 已重建 APK，未更改协议采样数值。
- HTTPS：`docs/HTTPS.md`、`soulband-demo/prepare_tls.py`；私钥只留宿主，双端仅打包公有 CA。更换 CA 必须重建两个客户端，不能关闭证书校验。
- SQLite：`soulband-demo/data/soulband.sqlite3`。测试必须使用独立数据库，不重置正常数据。
- 新一键入口使用 `soulband-demo/data/acceptance-v0.4.sqlite3`，是真实模型模式的持久化验收库，不覆盖原库。
- 原始项目方案和 v1.1 方案均保留；用户要求另存新版本时不得覆盖原文件。
- `.venv/`、构建缓存、数据库和截图是环境或验证产物，不默认通读，也不擅自删除。

## 验证

在 `soulband-demo/` 执行：

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

网页相关改动另运行 `tests/check_ui.py`，手机配对相关改动运行 `tests/check_mobile_ui.py`；真实 Windows 采样检查为 `tests/check_sensing_live.py`。

用户已授权推送 GitHub，项目已初始化 Git；数据库、凭据、私钥、模型、缓存与构建产物禁止提交。未安装提交钩子或拆超大文件；不要把历史整理任务的可选建议视为已授权配置。Windows 打包需防止 PATH 中 Poppler 的 ICU 被误带入，实际 exe 必须重跑配对和 Qt 加载检查。

写新函数或规则前，先搜索已有实现；保留可运行行为，避免把样例通过当作完整产品验收。
