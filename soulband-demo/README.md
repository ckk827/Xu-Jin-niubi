# 宿伴 Soulband

> v0.5.0 · 2026-11-08。Windows、Android 原生与手机网页共用业务服务。

2026-11-09 功能修复与当前启动方法见 [启动说明](../启动说明_2026-11-09.md)：Windows 依赖更新为 PySide6 6.10.3，公约支持星期、成员、日期范围和仅文字例外，临时安排到期后会重新安排判断。Android 源码已同步，本轮未重建 APK。

内嵌窗口白屏已定位为虚拟环境 Python/Qt 运行文件的 Windows Low 完整性标记错误。桌面启动脚本会恢复运行文件的正常 Medium 标记，保持 Chromium 沙箱开启；完整原生窗口加载与截图检查为 `tests/check_native_desktop.py`（独立数据库）。

入口 `../一键启动宿伴.cmd` 使用独立验收库，首次在界面选择本地 Ollama + Qwen 或外部 OpenAI 兼容 API，不再于启动前下载模型。外部模式支持 API 地址、模型名、密钥和连接测试；详见 [模型连接](../docs/MODELS.md)。`../启动四座位演示.cmd` 使用模拟结果，不需要 Ollama。多端使用 `../启动加密双端测试.cmd`；证书和防火墙见 [HTTPS 说明](../docs/HTTPS.md)。

## 已接入的功能

需求卡整理与本人修正、公开范围、公约生成和版本审核、模型受控记录与查询、参与设备选择、Windows/Android 粗粒度感知、模型活动推断与主动提醒、人工纠正、通知偏好与接收回执、临时安排审批和到期恢复、共同撤销公约、反馈及再次协商、值日排班与互换审批、参与人分账和本人结清、私密表达、自然语言受控查询与任务更新确认。

Android 入口为原生 Kotlin 页面；Windows 成员客户端有可分发的 exe 文件夹。业务能力已接入不代表所有设备和真实使用场景都已验证，具体本轮证据见 [交付报告](../output/release-2026-11-08/REPORT.md)。

## 身份、设备与模型边界

- 宿主本机保留演示身份切换；局域网成员须配对，以凭据固定身份，不能用 X-Member-Id 冒充别人。原生手机与网页/电脑分别使用一次性码。
- 配对授权是本版局域网身份方案；已提供项目 CA 的 HTTPS 校验，没有另建密码账户、找回系统或公网域名。HTTP 联调入口仅用于明确选择的样例测试。
- Windows 宿主采样仅代表宿主会话；其他电脑须运行成员客户端，主动开启采样。一名成员本版有一个电脑、一个手机摘要槽。
- 设备信号不证明睡眠、噪声或违规；缺失、失败、暂停和过期保留未知。模拟输入明确标记，不冒充实测。
- 模型模式和采样来源独立。本地与外部 API 模式均在失败时报错，无模拟回退；外部调用按任务需要发送数据给服务商。生成的公约和建议必须人工审核。
- Android 通知为前台服务轮询，Windows 使用系统托盘消息。接收、系统展示、成员已读是不同事实；不保证厂商省电环境下即时通知。
- 模型工具限公约/任务/账单读取、审核后公约记录、本人确认的任务完成，不执行任意脚本或 SQL。

## 启动入口与数据

| 入口 | 用途 |
| --- | --- |
| 根目录 一键启动宿伴.cmd | 打开独立验收环境，首次选择本地模型或外部 API |
| 根目录 启动宿伴_浏览器.cmd | 跳过 Qt，用默认浏览器打开同一验收环境；保留控制台 |
| 根目录 启动双端联调.cmd | 同一验收库，监听局域网并输出实际地址 |
| 根目录 启动加密双端测试.cmd | 局域网 HTTPS 8766，项目 CA 与正常证书校验 |
| 根目录 启动四座位演示.cmd | 宿主机同开四个成员窗口（独立会话），不需要 Ollama |
| 本目录 启动宿伴Demo.cmd | 原演示入口，保留原数据库和原有模式设置 |
| 本目录 启动成员电脑.cmd | 源码方式运行成员 Windows 客户端 |
| output/windows-v0.4.0-tls/Soulband-Windows/Soulband-Windows.exe | 含项目公有 CA，复制整个文件夹到其他 Windows 电脑 |
| output/apk/Soulband-v0.4.0-debug.apk | Android 原生调试包 |

`SOULBAND_DB` 指定 SQLite 路径。原数据 `data/soulband.sqlite3` 不清空；验收库 `data/acceptance-v0.4.sqlite3` 重启保留记录；四座位入口使用独立的 `data/seats-v0.5.sqlite3`。测试使用 `tests/.data/` 内独立文件，不能拿正常数据跑测试。启动和手动备份写入 `data/backups/`（VACUUM INTO + JSON）。

到期公约由存储层统一视为 `expired` 并清空生效指针，不会出现「已过期却挡着加成员」的状态；提醒由宿主机定时器在静音时段起点触发一次，迟到超过 15 分钟只记录「已错过」，不补发过期文案。同机四个窗口通过 `/api/demo/seat` 领取 7 天座席会话，权限与配对设备一致，不能执行加成员、改模型或设备授权等管理操作。

`prepare_model.py` 下载并校验官方 Ollama 运行包，模型位于根目录 `output/runtime/ollama/models`。运行时只监听 127.0.0.1:11434，不注册系统服务或修改 PATH。宿主业务服务通过 `OLLAMA_BASE_URL` 连接模型。模型候选名称可在设置修改，`GET /api/models` 检查实际已安装名称。

下载 Ollama 时保留系统默认可信 CA，并补充 `certifi` 公共证书库，以兼容 Anaconda 环境；GitHub 跳转和运行包下载均校验证书和主机名。证书校验错误不会触发关闭校验或切换模拟模式。

## 代码导航

| 文件 | 职责 |
| --- | --- |
| app.py | 核心公约、判断、提醒与调度 |
| scheduling.py | 静音时段定时触发、迟到与错过、启动重建 |
| engine.py | 真实模型、结构化约束、两阶段判断、显式模拟 |
| access.py | 局域网成员设备授权、凭据与来源校验 |
| business.py | 需求卡、审批、排班互换、受控工具、协商 |
| mobile_api.py / pc_api.py | 手机与成员电脑采样、凭据、设备参与、回执 |
| sensing.py / policy.py / members.py | Windows API、有效性与公共参数/成员查找 |
| storage.py | SQLite 持久化，不依赖模型聊天记忆 |
| desktop.py / peer_desktop.py | 宿主 Qt 入口、配对成员客户端与系统通知 |
| static/ | 响应式网页与完整业务操作入口 |
| tests/ / evaluate.py | 回归、真实模型/设备检查、探索性对比 |

## 检查命令

在本目录运行，正常库与测试库隔离：

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe tests/check_ui.py
..\.venv\Scripts\python.exe tests/check_mobile_ui.py
..\.venv\Scripts\python.exe tests/check_release_ui.py
..\.venv\Scripts\python.exe tests/check_sensing_live.py
..\.venv\Scripts\python.exe tests/check_windows_client.py
..\.venv\Scripts\python.exe tests/check_tls.py
..\.venv\Scripts\python.exe tests/check_model_live.py
..\.venv\Scripts\python.exe evaluate.py
```

浏览器检查需要 `requirements-dev.txt` 与本机 Edge。Android 模拟器 UI 检查为 `tests/check_android_ui.py`，仅操作明确命名的 emulator-5556，需先启动本项目 API 35 模拟器；构建步骤见 [Android 说明](../soulband-android/README.md)。

对最终 Windows 包执行 HTTPS 检查时设 `SOULBAND_WINDOWS_EXE` 为实际 exe 路径、`SOULBAND_WINDOWS_TLS=1`；Android 加密检查设 `SOULBAND_ANDROID_TLS=1`。`tests/check_ready_environment.py` 只检查已经启动的本机验收环境，不启动或重置服务。

探索性评价固定模型与底层案例，比较精简单步提示和优化流程，保留原始输出与错误。案例已参与开发调试，不能替代团队独立标签复核与盲测。

[变更记录](CHANGELOG.md)与[历史验证](TEST_REPORT.md)不自动等于本轮重跑结果。
