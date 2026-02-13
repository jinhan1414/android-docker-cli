# Release v1.2.13 - Android DNS Pinning (1.1.1.1)

- Android/Termux 运行时默认将容器 DNS 固定为 `1.1.1.1`，避免容器继承到 `::1` / `127.0.0.1` 本地解析器导致的网络请求失败（如 `lookup ... on [::1]:53: connection refused`）。
- 支持通过环境变量 `ANDROID_DOCKER_DNS` 覆盖默认 DNS（支持逗号或空格分隔多个地址）。
- 修复 bind 解析在带盘符路径场景下的兼容性问题（Windows 路径 `C:` 不再导致 `host:container` 解析错误）。
- 新增回归测试，覆盖 Android resolv.conf 生成与绑定行为。

Install:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/v1.2.13/scripts/install.sh | sh
```

Update:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/update.sh | sh
```

