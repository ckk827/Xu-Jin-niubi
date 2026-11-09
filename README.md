# 宿伴 Soulband

课程项目：收集寝室成员需求，由本地大模型或外部 API 生成公约，经成员审核后记录；结合电脑、手机状态判断粗粒度活动，依据生效公约主动提醒。

包含 Python/FastAPI 宿主、Windows Qt 入口与成员客户端、响应式网页、Kotlin 原生 Android 应用。支持需求卡及公开范围、公约版本与全员确认、模型受控记录与查询、设备参与和人工纠正、提醒去重、临时安排审批、反馈协商、值日互换、分账与私密表达。

## 从源码启动（Windows）

已验证 Python 3.11.5（64 位），另需 Git。在 PowerShell 执行：

```powershell
git clone https://github.com/ckk827/Xu-Jin-niubi.git
cd Xu-Jin-niubi
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r soulband-demo/requirements.txt
.\一键启动宿伴.cmd
```

入口先打开界面，首次选择本地大模型或外部 API。本地模式点击保存后才准备 Ollama 和 `qwen2.5:7b`；外部模式填写 API 地址、模型名与密钥，不下载本地模型。已保存的选择会保留，详见 [模型连接](docs/MODELS.md)。模型下载或调用失败会明确报错，不会自动切换为模拟。

桌面服务地址为 `http://127.0.0.1:8765`。首次使用独立验收数据库，带四个样例成员与明确标记的模拟设备输入，重启保留记录。模型模式与设备来源分别标识，真实采集需本人主动开启。

若先体验无需模型的模拟流程，安装依赖后运行 `soulband-demo/启动宿伴Demo.cmd`，它使用单独的演示库。

## Android 和其他 Windows 电脑

Android 构建需要 JDK 17、Android SDK platform 35 / build-tools 35.0.0；项目包含 Gradle wrapper。先生成本机证书，再构建：

```powershell
.\.venv\Scripts\python.exe soulband-demo/prepare_tls.py
.\soulband-android\Build-APK.ps1 -JdkHome '你的JDK17目录' -SdkRoot '你的AndroidSDK目录'
```

脚本把公有 CA 同步到 Android 调试包，私钥只留宿主。APK 生成在 `output/apk/`。直接用 Android Studio 构建前也须先完成证书准备及公有 CA 同步。

Windows 成员端可运行 `soulband-demo/启动成员电脑.cmd`。需要 exe 时：

```powershell
.\.venv\Scripts\python.exe -m pip install -r soulband-demo/requirements-build.txt
.\soulband-demo\Build-Windows.ps1
```

双击根目录 `启动加密双端测试.cmd`，使用输出的局域网地址和本机生成的一次性配对码加入。双端须使用同一宿主 CA 构建。新克隆生成的 CA 与作者本机不同，不应沿用作者的证书指纹或已有客户端。浏览器信任与防火墙步骤见 [HTTPS 说明](docs/HTTPS.md)。

源码仓库不包含 APK、exe、模型、虚拟环境、证书或数据库。交付文档中的 `output/` 和截图链接指向构建或验证后生成的本地产物，不是已发布的仓库附件。

## 测试

```powershell
cd soulband-demo
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用独立数据库。网页检查另需安装 `requirements-dev.txt` 并使用 Microsoft Edge。详细步骤见 [宿主说明](soulband-demo/README.md)、[Android 说明](soulband-android/README.md) 与 [手工测试](开始测试_宿伴_v0.4_2026-11-08.md)。部分原生 UI 检查脚本使用开发机 SDK 路径和指定模拟器，其他电脑需按实际环境调整。

v0.4 的开发机历史验证包括后端 52 项、网页 22 项、Android API 35 模拟器 HTTPS 11 项、真实模型业务 10 项及 Windows 客户端、TLS 检查。新克隆需自行重跑；iQOO 12、OriginOS 省电和多台物理电脑尚未实测。探索评价案例已用于调试，不是独立盲测。

## 文档

- [方案 v1.1](宿伴_Soulband_项目方案_v1.1_2026-10-27.md)
- [原始方案](宿伴_项目方案.md)
- [决策记录](docs/decisions-soulband.md)
- [版本变化](soulband-demo/CHANGELOG.md)

设备状态不证明睡眠、噪声或违规；缺失、失败、过期保留未知。公约和调整须人工审核，成员身份采用局域网设备配对授权，本机身份切换仅用于演示。
