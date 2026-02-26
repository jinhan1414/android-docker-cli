# Release v1.2.14 - Issue #5 Rootfs Recovery on Start/Restart

- 修复 Android/Termux 场景下容器状态脏数据导致的启动失败：当容器记录为 `running` 但无有效进程时，`docker start/restart` 会自动纠正状态并继续启动。
- 修复容器目录存在但 `rootfs` 目录缺失时的启动失败：启动路径会自动重建缺失目录，并继续走镜像缓存解压流程，避免直接报“找不到根文件系统”。
- 修复 `docker ps -a` 对“`running` 但无 `pid`”的僵尸状态处理：会自动回收为 `exited`，避免后续生命周期命令误判。
- 新增针对 Issue #5 的回归测试，覆盖“脏状态 + 缺失 rootfs 目录”启动恢复链路。

Install:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/v1.2.14/scripts/install.sh | sh
```

Update:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/update.sh | sh
```

