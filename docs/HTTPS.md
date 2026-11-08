# 宿伴 v0.4 局域网 HTTPS 测试

日期：2026-11-08。这里是局域网部署，不是公网证书或云推送。

## 开启服务

关闭已经运行的 HTTP 联调宿主，双击根目录 `启动加密双端测试.cmd`，保持控制台开启。它沿用独立验收数据库，检查真实模型、生成或续期服务器证书，以 HTTPS 监听 8766。不要同时运行同一数据库的多个宿主，以免重复模型调用。

使用控制台列出的实际 `https://电脑IP:8766` 地址；本机用 `https://127.0.0.1:8766`。IP 变更后重启此入口，服务器证书会补充当前地址，项目 CA 保持不变。

本轮准备的 APK 与 `output/windows-v0.4.0-tls/Soulband-Windows/` 成员客户端已包含此项目的公有 CA，正常校验证书链、有效期与地址，不需要先安装系统根证书。Android 的项目 CA 只在调试包启用。不要勾选 HTTP 测试；证书失败不会自动改用 HTTP。

## 浏览器首次信任

宿主浏览器需要先信任本项目 CA，否则会显示证书错误。不要跳过错误或关闭校验。

1. 从宿主本机取得 `soulband-demo/data/tls/soulband-ca.crt`，只能分发这个公有证书，不能分发 `.key` 文件。
2. 本项目 CA 的 SHA256 证书指纹：`AE9A75332CAD57838AB405D36EB4EF7126285E364B4421AA5C40F9EE04F3BA32`。这是 DER 证书指纹，不是 PEM 文件的文件哈希。可在 Windows 证书查看器查看；PowerShell 可使用 `Get-PfxCertificate` 与 `GetCertHashString('SHA256')` 核对。
3. 确认来源和指纹后，在 Windows 双击证书 → 安装证书 → 当前用户 → 将证书放入“受信任的根证书颁发机构”，确认系统提示。此操作由你明确完成，启动器不会改动系统信任库。
4. 重新打开浏览器访问 HTTPS 本机地址。在本机生成成员配对码，再让手机或其他电脑加入。

手机原生 APK 已包含项目 CA，不需要安装手机系统 CA。手机浏览器如需使用 HTTPS，应按手机系统实际提供的 CA 安装入口信任同一证书；OriginOS 菜单名称尚未实机确认，不编造路径。只装 APK 不受这一步影响。

## Windows 防火墙与连接

局域网联调仅对可信专用网络开放，不关闭防火墙。Windows 提示允许 Python 入站时，仅勾选专用网络；若学校网络禁止互访，可使用自己的路由器或电脑热点。

需要手工规则时，以管理员 PowerShell 按需执行以下命令。启动器没有替你添加防火墙规则：

```powershell
New-NetFirewallRule -DisplayName 'Soulband HTTPS LAN 8766' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766 -Profile Private -RemoteAddress LocalSubnet
```

不再使用时删除这条明确命名的规则即可。该命令可能需要管理员权限，校园网络策略仍可能阻止互访。

## 私钥与重建

- `data/tls/ca.key` 和 `server.key` 只留宿主。加密启动器将这两个文件 ACL 限制为当前 Windows 用户和 SYSTEM；不自动备份或上传私钥。
- CA 默认五年、服务器证书默认九十天，七天内到期续签；均为实现参数。CA 不静默轮换，过期或文件缺失不匹配会停止启动。
- 若主动换 CA，必须重新构建 APK 和成员 Windows 客户端、分发新公有证书、更新浏览器信任；旧客户端不会接受新 CA。
- 构建只打包公有 CA，不打包任何私钥。HTTP 8765 保留为明确选择的演示联调入口，不用于传输真实私密诉求。
- 当前使用 HTTPS 轮询，没有 WSS 通道，所有现有 API 与静态页面都通过同一 TLS 监听服务提供。

## 依据

- [Android 网络安全配置](https://developer.android.com/privacy-and-security/security-config)：应用信任锚与仅调试信任配置。
- [Python SSL](https://docs.python.org/3/library/ssl.html)：证书链和服务器名称校验。
- [Qt WebEngine profile builder](https://doc.qt.io/qt-6/qwebengineprofilebuilder.html)：profile 附加可信 CA；客户端使用内存 profile，不绕过证书错误。
