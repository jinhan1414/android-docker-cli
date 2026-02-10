# Android Docker CLI 兼容性测试计划

## 1. 测试目标

验证 `android-docker-cli` 工具是否能够与非 Docker Hub 的镜像仓库（具体为 `swr.cn-north-4.myhuaweicloud.com`）完全兼容，包括镜像的拉取、运行和管理。

## 2. 测试环境

*   **工具**: `android-docker-cli` (当前项目中的版本)
*   **操作系统**: 任何支持 `proot` 和 `curl` 的 Linux 环境，优先考虑 Termux on Android。
*   **依赖**: `python`, `proot`, `curl`, `tar`
*   **测试镜像**: `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest`

## 3. 测试用例

### 3.1. 用例 1: 镜像拉取 (`docker pull`)

*   **步骤**:
    1.  执行命令: `python docker_cli.py pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest`
    2.  (可选) 为了验证强制刷新功能，再次执行: `python docker_cli.py pull --force swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest`
*   **预期结果**:
    1.  命令成功执行，没有错误输出。
    2.  日志显示 "✓ 镜像拉取成功"。
    3.  在 `~/.docker_proot_cache/` 目录下，可以看到一个代表该镜像的 `.tar.gz` 文件和一个 `.info` 文件。
    4.  执行 `docker images` 命令，可以看到缓存的镜像信息。

### 3.2. 用例 2: 容器运行 (前台模式, `docker run`)

*   **步骤**:
    1.  执行命令: `python docker_cli.py run swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest echo "Hello from Huawei Cloud image"`
*   **预期结果**:
    1.  命令成功执行。
    2.  终端输出 "Hello from Huawei Cloud image"。
    3.  日志显示 "容器 ... 运行完成"。
    4.  由于是前台非持久化运行，执行后 `docker ps -a` 不应看到此容器的记录。

### 3.3. 用例 3: 容器运行 (交互式模式, `docker run -it`)

*   **步骤**:
    1.  执行命令: `python docker_cli.py run -it swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest /bin/sh`
*   **预期结果**:
    1.  成功进入容器的 shell 环境，提示符变为 `#` 或 `$`。
    2.  在 shell 中可以执行基本命令，如 `ls -l`, `pwd`, `cat /etc/os-release`。
    3.  输入 `exit` 后，可以正常退出容器。

### 3.4. 用例 4: 容器运行 (后台模式, `docker run -d`)

*   **步骤**:
    1.  执行命令: `python docker_cli.py run -d swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest sleep 60`
*   **预期结果**:
    1.  命令立即返回，并输出一个容器 ID。
    2.  日志显示 "容器 ... 已在后台启动"。
    3.  执行 `python docker_cli.py ps`，可以看到一个状态为 `running` 的新容器。
    4.  等待约 1 分钟后，再次执行 `python docker_cli.py ps -a`，该容器的状态应变为 `exited`。

### 3.5. 用例 5: 容器生命周期管理 (`ps`, `stop`, `start`, `rm`)

*   **步骤**:
    1.  基于用例 3.4 启动一个后台容器: `python docker_cli.py run -d --name test-huawei swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest sleep 120`
    2.  查看容器状态: `python docker_cli.py ps`
    3.  停止容器: `python docker_cli.py stop test-huawei`
    4.  再次查看状态: `python docker_cli.py ps -a`
    5.  启动容器: `python docker_cli.py start test-huawei`
    6.  再次查看状态: `python docker_cli.py ps`
    7.  删除容器: `python docker_cli.py rm test-huawei`
    8.  最后查看状态: `python docker_cli.py ps -a`
*   **预期结果**:
    1.  `ps` 命令能正确显示容器的运行状态 (`running`, `exited`)。
    2.  `stop` 命令能成功停止容器，状态变为 `exited`。
    3.  `start` 命令能成功启动已停止的容器，状态变回 `running`。
    4.  `rm` 命令能成功删除容器，之后 `ps -a` 不再显示该容器。

### 3.6. 用例 6: 查看容器日志 (`docker logs`)

*   **步骤**:
    1.  启动一个后台容器，让它产生一些输出: `python docker_cli.py run -d --name log-test swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest sh -c 'echo "line 1"; sleep 1; echo "line 2"; sleep 1; echo "line 3"'`
    2.  等待几秒钟，然后查看日志: `python docker_cli.py logs log-test`
    3.  (可选) 测试日志跟踪功能: `python docker_cli.py logs -f log-test` (这个命令会持续运行，需要手动 `Ctrl+C` 退出)
*   **预期结果**:
    1.  `docker logs log-test` 命令应该能输出容器已经产生的日志 (例如 "line 1", "line 2")。
    2.  `docker logs -f log-test` 命令会先输出已有日志，然后阻塞，并实时打印后续的输出 (例如 "line 3")。
    3.  `Ctrl+C` 可以正常退出日志跟踪。
### 3.7. 用例 7: 镜像清理 (`docker rmi`)

*   **步骤**:
    1.  确保没有基于该镜像的容器在运行。
    2.  执行命令: `python docker_cli.py rmi swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest`
*   **预期结果**:
    1.  命令成功执行。
    2.  `~/.docker_proot_cache/` 目录下对应的 `.tar.gz` 和 `.info` 文件被删除。
    3.  执行 `docker images` 不再显示该镜像。

### 3.8. 用例 8: 镜像启动兼容性 (需要 root 启动再降权的镜像)

*   **目的**: 覆盖“入口脚本会 `chown` 卷挂载路径并由 supervisor/s6 等进程降权运行”的镜像启动路径。
*   **步骤**:
    1.  执行命令: `docker run --name hass-panel -v ./data2:/config/hass-panel registry.cn-hangzhou.aliyuncs.com/hass-panel/hass-panel:latest`
    2.  如果容器以后台方式运行，执行 `docker logs hass-panel` 观察启动日志。
*   **预期结果**:
    1.  不再出现 `Can't drop privilege as nonroot user` 导致的启动失败。
    2.  若存在 `chown` 行为，不应因“非 root”而直接失败（仍可能因镜像自身原因失败，需结合日志判断）。

## 4. 风险与缓解

*   **风险**: 网络问题导致镜像拉取失败。
    *   **缓解**: 确保测试环境网络通畅，可以访问 `swr.cn-north-4.myhuaweicloud.com`。
*   **风险**: 华为云镜像仓库的认证机制与预期的 Docker Registry API V2 不完全兼容。
    *   **缓解**: 如果出现认证失败，需要抓取 `curl` 的详细输出来分析认证流程，并可能需要修改 `create_rootfs_tar.py` 中的认证逻辑。
## 5. Docker Compose 测试

### 5.1. 用例 8: `docker-compose up -d`

*   **步骤**:
    1.  创建一个名为 `docker-compose.yml` 的文件，内容如下:
        ```yaml
        version: '1.0'
        services:
          app:
            image: "swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest"
            container_name: "compose-test-app"
            command: "sh -c 'echo App started && sleep 300'"
          db:
            image: "swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/alpine:latest"
            container_name: "compose-test-db"
            command: "sh -c 'echo DB started && sleep 300'"
        ```
    2.  执行命令: `python docker_compose_cli.py up -d`
*   **预期结果**:
    1.  命令成功执行，没有错误。
    2.  日志显示正在启动 `app` 和 `db` 两个服务。
    3.  执行 `python docker_cli.py ps`，可以看到 `compose-test-app` 和 `compose-test-db` 两个容器正在运行。

### 5.2. 用例 9: `docker-compose down`

*   **步骤**:
    1.  确保用例 5.1 中的容器正在运行。
    2.  在包含 `docker-compose.yml` 的目录中，执行命令: `python docker_compose_cli.py down`
*   **预期结果**:
    1.  命令成功执行。
    2.  日志显示正在停止和移除 `compose-test-app` 和 `compose-test-db` 容器。
    3.  执行 `python docker_cli.py ps -a`，不再显示这两个容器。
