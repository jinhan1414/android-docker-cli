# Android Docker CLI

[English](README.md) | 中文

一个使用 `proot` 在 Android 上运行 Docker 镜像的工具，无需 Docker 引擎。本项目旨在 [Termux](https://github.com/termux/termux-app) 应用内部使用，为 Android 提供一个类似 Docker 的命令行界面，用于管理持久化容器。

## 核心功能

- **模块化代码**: 所有核心逻辑都被组织在 `android_docker` 包中。
- **主命令行界面**: 主要入口点是 `android_docker/docker_cli.py`，提供一个用于完整容器生命周期管理的 Docker 风格 CLI。
- **持久化容器**: 容器拥有持久化的文件系统，可以被启动、停止和重启。
- **底层引擎**: 使用 `android_docker/proot_runner.py` 来执行容器，使用 `android_docker/create_rootfs_tar.py` 来下载和准备容器镜像。

## 安装

您可以使用一行命令来安装此工具：

```bash
# 安装最新版本（main分支）
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/install.sh | sh

# 安装特定版本（例如 v1.1.0）
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/v1.1.0/scripts/install.sh | sh

# 或使用环境变量指定版本
INSTALL_VERSION=v1.2.0 curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/install.sh | sh
```

这将会创建一个名为 `docker` 的可执行命令到您的系统路径中。安装后，您只需输入 `docker` 即可运行此工具。

## 安装依赖

```bash
# Android Termux
pkg update && pkg install python proot curl tar

# Ubuntu/Debian
sudo apt install python3 proot curl tar
```

## 快速使用

安装后，您可以像使用标准 Docker 命令行一样使用此工具。

```bash
# 登录到 Docker Registry (例如 Docker Hub)
docker login

# 登录后从私有仓库拉取镜像
docker login your-private-registry.com
docker pull your-private-registry.com/my-image

# 拉取一个公开镜像
docker pull alpine:latest

# 在前台运行一个容器
docker run alpine:latest echo "Hello from container"

# 在后台（分离模式）运行一个容器
docker run -d -e "API_KEY=sk-12345" --volume /sdcard:/data nginx:alpine

# 交互式运行容器
docker run -it alpine:latest /bin/sh

# 使用项目中的自定义配置文件运行 Nginx 容器
# 此示例使用 `examples/nginx.conf` 文件, 它将监听 8777 端口。
docker run -d --name my-nginx -v $(pwd)/examples/nginx.conf:/etc/nginx/nginx.conf nginx:alpine

# 列出正在运行的容器
docker ps

# 列出所有容器（包括已停止的）
docker ps -a

# 查看容器日志
docker logs <container_id>
docker logs -f <container_id>  # 持续跟踪日志

# 停止一个容器
docker stop <container_id>

# 启动一个已停止的容器
docker start <container_id>

# 重启一个容器
docker restart <container_id>

# 删除一个容器
docker rm <container_id>

# 附加到运行中的容器
docker attach <container_id>

# 在运行中的容器中执行命令
docker exec <container_id> ls -l
docker exec -it <container_id> /bin/sh

# 列出缓存的镜像
docker images

# 从本地tar文件加载镜像
docker load -i alpine.tar
docker load -i /path/to/my-image.tar

# 删除一个缓存的镜像
docker rmi alpine:latest

# 登录到镜像仓库
docker login your-private-registry.com
```

## 加载本地镜像

您可以从本地tar归档文件加载Docker镜像，而无需从镜像仓库拉取。这在以下情况下很有用：
- 使用预先下载的镜像
- 加载在其他系统上构建的镜像
- 离线工作

### 要求

tar文件必须是有效的Docker镜像归档文件，包含：
- `manifest.json` - 镜像清单
- 层tar文件（例如 `<hash>/layer.tar`）
- 配置JSON文件（例如 `<hash>.json`）

### 使用方法

```bash
# 从tar文件加载镜像
docker load -i alpine.tar

# 从指定路径加载镜像
docker load -i /sdcard/Download/my-image.tar

# 加载后，镜像将出现在您的镜像列表中
docker images
```

### 创建Docker镜像Tar文件

您可以使用标准Docker创建兼容的tar文件：

```bash
# 在安装了Docker的系统上
docker save alpine:latest -o alpine.tar

# 将tar文件传输到您的Android设备
# 然后加载它
docker load -i alpine.tar
```

## Docker Compose 支持

此工具包含一个 `docker-compose` 命令，用于管理多容器应用。

```bash
# 启动 docker-compose.yml 中定义的服务
docker-compose up

# 在后台运行
docker-compose up -d

# 停止并移除服务
docker-compose down
```

### `docker-compose.yml` 示例

```yaml
version: '3'
services:
  web:
    image: nginx:alpine
    container_name: my-web-server
  db:
    image: redis:alpine
    container_name: my-redis-db
```

## 主要特性

- ✅ **完整的容器生命周期**: `run`, `ps`, `stop`, `start`, `restart`, `logs`, `rm`, `attach`, `exec`。
- ✅ **镜像仓库认证**: 使用 `login` 命令登录私有或公共镜像仓库。
- ✅ **本地镜像加载**: 使用 `docker load` 从本地tar文件加载Docker镜像。
- ✅ **OCI镜像仓库支持**: 从符合OCI标准的镜像仓库（如GitHub Container Registry (ghcr.io)）拉取镜像。
- ✅ **Docker Compose 支持**: 使用 `docker-compose up` 和 `down` 管理多容器配置。
- ✅ **Docker风格CLI**: 熟悉且直观的命令行界面。
- ✅ **持久化存储**: 容器在重启后能保持其状态和文件系统，存储于 `~/.docker_proot_cache/`。
- ✅ **Android优化**: 针对 Termux 环境进行了特别优化。

## 故障排除

```bash
# 检查依赖
curl --version && tar --version && proot --version

# 使用详细日志获取更多信息
docker --verbose run alpine:latest
```

### Android常见问题

#### 权限拒绝错误

如果遇到权限错误，例如：
```
nginx: [alert] could not open error log file: open() "/var/log/nginx/error.log" failed (13: Permission denied)
```

**解决方案**：工具会在Android上自动创建可写的系统目录。请确保使用最新版本。

#### Whiteout文件警告

如果看到关于 `.wh.auxfiles` 或类似whiteout文件的警告：
```
tar: ./var/lib/apt/lists/.wh.auxfiles: Cannot open: Permission denied
```

**解决方案**：这些文件在Android上会被自动跳过。层删除语义可能不完全保留，但容器可以正常运行。

#### 提取失败

如果镜像提取失败：
- 使用 `--verbose` 标志查看详细错误信息
- 检查Termux中的可用磁盘空间
- 先尝试拉取较小的镜像（例如 `alpine:latest`）
- 确保所有依赖已安装：`pkg install python proot curl tar`

#### 容器启动问题

如果容器启动失败：
- 使用 `docker logs <container_id>` 查看日志
- 验证镜像是否与您的架构兼容
- 某些镜像可能需要proot中不可用的特定功能
- 尝试使用 `--verbose` 运行以获取详细调试信息

如果在 Android/Termux 下看到类似 `chown ... Operation not permitted` 或 `Can't drop privilege as nonroot user` 的错误：
- 请更新到较新的版本。Android 运行会启用额外的兼容行为，使一些“启动时需要 root、随后再降权”的镜像无需额外参数即可运行。

## 限制说明

- 基于 `proot`，并非完整的容器化（无内核级的进程或网络隔离）。
- 某些系统调用可能不被支持。
- 性能相较于原生 Docker 会有所下降。
- 网络隔离有限。

### Android特定限制

- **Whiteout文件**：由于Android权限限制，Docker层删除语义（whiteout文件）会被跳过。这意味着从前一层删除的文件可能仍然存在于最终容器文件系统中。
- **系统目录**：可写系统目录（`/var/log`、`/var/cache`、`/tmp` 等）会自动从主机存储绑定挂载，以解决Android权限限制。
- **文件权限**：某些文件权限和所有权操作在Android文件系统上可能无法按预期工作。
- **进程隔离**：proot提供进程隔离但不是完整的容器化。容器共享相同的内核，资源隔离有限。

## 许可证

MIT License
