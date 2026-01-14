#!/usr/bin/env python3
"""
使用proot运行Docker镜像的一条龙服务脚本
支持直接输入镜像URL，自动拉取、制作根文件系统、启动容器
支持类似Docker的命令行参数和环境变量，包含镜像缓存功能
"""

import os
import sys
import subprocess
import argparse
import json
import tempfile
import shutil
import logging
import hashlib
import shlex
import time
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProotRunner:
    """使用proot运行容器的类，支持一条龙服务"""

    def __init__(self, cache_dir=None):
        self.temp_dir = None
        self.rootfs_dir = None
        self.config_data = None
        self.cache_dir = cache_dir or self._get_default_cache_dir()
        self._ensure_cache_dir()

    def _get_default_cache_dir(self):
        """获取默认缓存目录"""
        # 在用户主目录下创建缓存
        home_dir = os.path.expanduser('~')
        cache_dir = os.path.join(home_dir, '.proot_runner_cache')
        return cache_dir

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.debug(f"缓存目录: {self.cache_dir}")

    def _get_image_cache_path(self, image_url):
        """根据镜像URL生成缓存路径"""
        # 使用镜像URL的hash作为缓存文件名
        url_hash = hashlib.sha256(image_url.encode()).hexdigest()[:16]

        # 提取镜像名称作为可读部分
        image_name = image_url.split('/')[-1].split(':')[0]
        cache_filename = f"{image_name}_{url_hash}.tar.gz"

        return os.path.join(self.cache_dir, cache_filename)

    def _is_image_cached(self, image_url):
        """检查镜像是否已缓存"""
        cache_path = self._get_image_cache_path(image_url)
        return os.path.exists(cache_path)

    def _get_cache_info_path(self, image_url):
        """获取缓存信息文件路径"""
        cache_path = self._get_image_cache_path(image_url)
        return cache_path + '.info'

    def _save_cache_info(self, image_url, cache_path):
        """保存缓存信息"""
        info = {
            'image_url': image_url,
            'cache_path': cache_path,
            'created_time': time.time(),
            'created_time_str': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        info_path = self._get_cache_info_path(image_url)
        with open(info_path, 'w') as f:
            json.dump(info, f, indent=2)

    def _load_cache_info(self, image_url):
        """加载缓存信息"""
        info_path = self._get_cache_info_path(image_url)
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"读取缓存信息失败: {e}")
        return None

    def _download_image(self, image_url, force_download=False, username=None, password=None):
        """下载镜像到缓存"""
        cache_path = self._get_image_cache_path(image_url)

        # 检查缓存
        if not force_download and self._is_image_cached(image_url):
            cache_info = self._load_cache_info(image_url)
            if cache_info:
                logger.info(f"使用缓存的镜像: {cache_path}")
                logger.info(f"缓存创建时间: {cache_info.get('created_time_str', 'Unknown')}")
                return cache_path

        logger.info(f"下载镜像: {image_url}")

        # 调用create_rootfs_tar.py脚本
        cmd = [
            sys.executable,
            '-m', 'android_docker.create_rootfs_tar',
            '-o', cache_path,
        ]
        if username:
            cmd.extend(['--username', username])
        if password:
            cmd.extend(['--password', password])
        
        # 获取并传递代理参数
        proxy = os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY')
        if proxy:
            cmd.extend(['--proxy', proxy])

        cmd.append(image_url)

        try:
            subprocess.run(cmd, check=True)
            logger.info(f"镜像已下载并缓存: {cache_path}")

            # 保存缓存信息
            self._save_cache_info(image_url, cache_path)

            return cache_path

        except subprocess.CalledProcessError as e:
            logger.error(f"下载镜像失败: {e}")
            return None

    def _is_image_url(self, input_str):
        """判断输入是否为镜像URL"""
        # 简单的启发式判断
        url_indicators = [
            '/' in input_str and ':' in input_str,  # 包含registry和tag
            input_str.count('/') >= 1,  # 至少有一个斜杠
            not input_str.endswith('.tar'),  # 不是tar文件
            not input_str.endswith('.tar.gz'),  # 不是tar.gz文件
            not os.path.exists(input_str)  # 不是本地文件/目录
        ]

        return any(url_indicators)

    def _prepare_rootfs(self, input_path, args, provided_rootfs_dir=None):
        """准备根文件系统（下载或使用现有）"""
        
        # 对于重启操作，如果持久化目录已存在且非空，则直接使用
        if provided_rootfs_dir and os.path.exists(provided_rootfs_dir) and os.listdir(provided_rootfs_dir):
            logger.info(f"使用现有的持久化根文件系统: {provided_rootfs_dir}")
            self.rootfs_dir = provided_rootfs_dir
            self.temp_dir = None # We are not managing a temporary directory
            return self.rootfs_dir

        # 否则，执行正常的下载和解压逻辑
        if self._is_image_url(input_path):
            # 这是一个镜像URL，需要下载
            logger.info(f"检测到镜像URL: {input_path}")
            cache_path = self._download_image(
                input_path,
                force_download=getattr(args, 'force_download', False),
                username=getattr(args, 'username', None),
                password=getattr(args, 'password', None)
            )
            if not cache_path:
                return None
            return self._extract_rootfs_if_needed(cache_path, provided_rootfs_dir=provided_rootfs_dir)
        else:
            # 这是本地文件或目录
            logger.info(f"使用本地根文件系统: {input_path}")
            return self._extract_rootfs_if_needed(input_path, provided_rootfs_dir=provided_rootfs_dir)
        
    def _check_dependencies(self):
        """检查必要的依赖是否已安装"""
        # 检查proot
        try:
            subprocess.run(['proot', '--version'],
                         capture_output=True, check=True)
            logger.info("✓ proot 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("✗ proot 未安装")
            logger.info("请安装proot: pkg install proot (Termux) 或 apt install proot")
            return False

        # 检查create_rootfs_tar.py脚本
        # Since we are using `python -m`, we don't need to check for the script path here.
        # The python interpreter will find the module.
        logger.info("✓ create_rootfs_tar.py module is available")

        # 检查curl（create_rootfs_tar.py需要）
        try:
            subprocess.run(['curl', '--version'],
                         capture_output=True, check=True)
            logger.info("✓ curl 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("✗ curl 未安装")
            logger.info("请安装curl: pkg install curl (Termux) 或 apt install curl")
            return False

        # 检查tar
        try:
            subprocess.run(['tar', '--version'],
                         capture_output=True, check=True)
            logger.info("✓ tar 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("✗ tar 未安装")
            logger.info("请安装tar: pkg install tar (Termux) 或 apt install tar")
            return False

        return True
    
    def _extract_rootfs_if_needed(self, rootfs_path, provided_rootfs_dir=None):
        """如果输入是tar文件，则解压到指定目录"""

        # 1. 如果输入不是tar文件，按旧逻辑处理
        if not (rootfs_path.endswith('.tar') or rootfs_path.endswith('.tar.gz')):
            if os.path.isdir(rootfs_path):
                self.rootfs_dir = os.path.abspath(rootfs_path)
                logger.info(f"使用现有根文件系统目录: {self.rootfs_dir}")
                return self.rootfs_dir
            else:
                logger.error(f"无效的根文件系统路径: {rootfs_path}")
                return None

        # 2. 确定解压目标目录
        is_temp = False
        if provided_rootfs_dir:
            target_dir = provided_rootfs_dir
            self.temp_dir = None
        else:
            self.temp_dir = tempfile.mkdtemp(prefix='proot_runner_')
            target_dir = os.path.join(self.temp_dir, 'rootfs')
            is_temp = True
        
        self.rootfs_dir = target_dir
        os.makedirs(self.rootfs_dir, exist_ok=True)

        # 3. 解压tar文件
        logger.info(f"检测到tar文件，正在解压: {rootfs_path} -> {self.rootfs_dir}")
        if rootfs_path.endswith('.tar.gz'):
            cmd = ['tar', '-xzf', rootfs_path, '-C', self.rootfs_dir]
        else:
            cmd = ['tar', '-xf', rootfs_path, '-C', self.rootfs_dir]
        
        try:
            subprocess.run(cmd, check=True)
            logger.info(f"根文件系统已解压到: {self.rootfs_dir}")
            return self.rootfs_dir
        except subprocess.CalledProcessError as e:
            logger.error(f"解压失败: {e}")
            if is_temp:
                self._cleanup()
            return None
    
    def _find_image_config(self):
        """查找镜像配置信息"""
        # 尝试从多个可能的位置查找配置
        config_paths = [
            os.path.join(self.rootfs_dir, '.image_config.json'),
            os.path.join(self.rootfs_dir, 'image_config.json'),
            os.path.join(self.rootfs_dir, 'etc', 'image_config.json')
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        self.config_data = json.load(f)
                    logger.info(f"找到镜像配置: {config_path}")
                    return True
                except Exception as e:
                    logger.warning(f"读取配置文件失败 {config_path}: {e}")
        
        logger.info("未找到镜像配置文件，将使用默认设置")
        return False
    
    def _get_default_command(self):
        """获取默认启动命令"""
        if self.config_data:
            # 从配置中获取CMD或ENTRYPOINT
            config = self.config_data.get('config', {})

            # 优先使用Entrypoint + Cmd
            entrypoint = config.get('Entrypoint', [])
            cmd = config.get('Cmd', [])

            if entrypoint:
                if cmd:
                    return entrypoint + cmd
                else:
                    return entrypoint
            elif cmd:
                return cmd

        # 默认命令 - 查找可用的shell
        default_shells = ['/bin/bash', '/bin/sh', '/bin/ash', '/bin/dash']
        for shell in default_shells:
            shell_path = os.path.join(self.rootfs_dir, shell.lstrip('/'))
            if os.path.exists(shell_path):
                logger.debug(f"找到可用shell: {shell}")
                return [shell]

        # 如果没有找到shell，尝试busybox
        busybox_path = os.path.join(self.rootfs_dir, 'bin/busybox')
        if os.path.exists(busybox_path):
            logger.debug("使用busybox shell")
            return ['/bin/busybox', 'sh']

        logger.warning("未找到可用的shell，使用默认/bin/sh")
        return ['/bin/sh']  # 最后的备选

    def _get_available_shell(self):
        """获取可用的shell路径（用于执行脚本）"""
        # 查找可用的shell
        default_shells = ['/bin/bash', '/bin/sh', '/bin/ash', '/bin/dash']
        for shell in default_shells:
            shell_path = os.path.join(self.rootfs_dir, shell.lstrip('/'))
            if os.path.exists(shell_path):
                logger.debug(f"找到可用shell用于执行脚本: {shell}")
                return shell

        # 如果没有找到shell，尝试busybox
        busybox_path = os.path.join(self.rootfs_dir, 'bin/busybox')
        if os.path.exists(busybox_path):
            logger.debug("使用busybox shell执行脚本")
            return '/bin/busybox'

        logger.warning("未找到可用的shell执行脚本，使用默认/bin/sh")
        return '/bin/sh'  # 最后的备选

    def _get_default_env(self):
        """获取默认环境变量"""
        env_vars = {}
        
        if self.config_data:
            config = self.config_data.get('config', {})
            env_list = config.get('Env', [])
            
            for env_str in env_list:
                if '=' in env_str:
                    key, value = env_str.split('=', 1)
                    env_vars[key] = value
        
        # 添加一些基本的环境变量
        env_vars.setdefault('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
        env_vars.setdefault('HOME', '/root')
        env_vars.setdefault('TERM', 'xterm')
        
        return env_vars
    
    def _get_working_directory(self):
        """获取工作目录"""
        if self.config_data:
            config = self.config_data.get('config', {})
            workdir = config.get('WorkingDir')
            if workdir:
                return workdir
        
        return '/'
    
    def _build_proot_command(self, args):
        """构建proot命令（增强Android支持）"""
        cmd = ['proot']

        # 基本选项
        cmd.extend(['-r', self.rootfs_dir])

        # 如果是后台运行，禁用TTY，并指定PID文件
        if args.detach:
            # This block is now empty as proot doesn't support pid file args
            pass

        # 绑定挂载
        default_binds = [
            '/dev',
            '/proc',
            '/sys'
        ]

        # 在Android/Termux中添加额外的绑定
        if self._is_android_environment():
            default_binds.extend([
                '/sdcard',
                '/system/etc/resolv.conf:/etc/resolv.conf'
            ])

            # 添加可写系统目录绑定
            # 使用rootfs_dir作为container_dir来存储可写目录
            if self.rootfs_dir:
                writable_binds = self._prepare_writable_directories(self.rootfs_dir)
                default_binds.extend(writable_binds)
                logger.info("已启用Android可写目录支持")

        for bind in default_binds:
            if ':' in bind:
                src, dst = bind.split(':', 1)
                if os.path.exists(src):
                    cmd.extend(['-b', bind])
            else:
                if os.path.exists(bind):
                    cmd.extend(['-b', bind])

        # 用户指定的绑定挂载
        for bind in args.bind:
            cmd.extend(['-b', bind])

        # 工作目录
        workdir = args.workdir or self._get_working_directory()
        cmd.extend(['-w', workdir])

        # 环境变量
        env_vars = self._get_default_env()

        # 添加用户指定的环境变量
        for env in args.env:
            if '=' in env:
                key, value = env.split('=', 1)
                env_vars[key] = value

        # 如果是后台运行，强制设置TERM为dumb，避免交互式行为
        if args.detach:
            env_vars['TERM'] = 'dumb'

        # proot不支持-E选项，需要通过其他方式设置环境变量
        # 我们将通过修改启动命令来设置环境变量

        # 构建最终的执行命令
        if args.command:
            final_command = args.command
        else:
            default_cmd = self._get_default_command()
            final_command = default_cmd

        # 创建启动脚本来设置环境变量
        if env_vars or self._is_android_environment():
            # 获取可用的shell来执行启动脚本
            available_shell = self._get_available_shell()
            startup_script = self._create_startup_script(env_vars, final_command)

            # 如果是busybox，需要添加sh参数
            if available_shell == '/bin/busybox':
                cmd.extend([available_shell, 'sh', startup_script])
            else:
                cmd.extend([available_shell, startup_script])
        else:
            cmd.extend(final_command)

        return cmd

    def _create_startup_script(self, env_vars, command):
        """创建启动脚本来设置环境变量和执行命令"""
        # 获取可用的shell来作为脚本的shebang
        available_shell = self._get_available_shell()

        # 如果是busybox，需要特殊处理
        if available_shell == '/bin/busybox':
            script_content = ['#!/bin/busybox sh']
        else:
            script_content = [f'#!{available_shell}']

        # 添加环境变量设置
        for key, value in env_vars.items():
            # 转义特殊字符
            escaped_value = value.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
            script_content.append(f'export {key}="{escaped_value}"')

        # 在Android环境中添加特殊处理
        if self._is_android_environment():
            script_content.extend([
                '# Android Termux 特殊处理',
                'unset LD_PRELOAD'  # 取消termux-exec
            ])

        # 添加执行命令
        if len(command) >= 2 and command[0] == 'sh' and command[1] == '-c':
            # 对于 'sh -c "command string"', 确保命令字符串被正确引用
            quoted_command_str = shlex.quote(command[2])
            script_content.append(f'exec {command[0]} {command[1]} {quoted_command_str}')
        else:
            command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
            script_content.append(f'exec {command_str}')

        # 写入临时脚本文件
        script_path = os.path.join(self.rootfs_dir, 'startup.sh')
        with open(script_path, 'w') as f:
            f.write('\n'.join(script_content) + '\n')

        # 设置执行权限
        os.chmod(script_path, 0o755)

        logger.debug(f"创建启动脚本: {script_path}")
        logger.debug(f"脚本内容:\n{chr(10).join(script_content)}")
        return '/startup.sh'
    
    def _is_android_environment(self):
        """检测是否在Android环境中运行（增强版）"""
        android_indicators = [
            '/data/data/com.termux' in os.getcwd(),
            os.path.exists('/system/build.prop'),
            os.environ.get('ANDROID_DATA') is not None,
            os.environ.get('TERMUX_VERSION') is not None,
            os.path.exists('/data/data/com.termux'),
            'com.termux' in os.environ.get('PREFIX', ''),
        ]
        
        is_android = any(android_indicators)
        
        if is_android:
            logger.debug("检测到Android/Termux环境")
        
        return is_android

    def _prepare_writable_directories(self, rootfs_dir):
        """为Android环境准备可写的系统目录"""
        if not self._is_android_environment():
            return []

        # 需要可写的系统目录列表
        writable_dirs = [
            'var/log',
            'var/cache',
            'var/tmp',
            'tmp',
            'run',
        ]

        # 在rootfs目录的同级创建writable_dirs目录
        # 如果rootfs_dir是临时目录，writable_dirs也会在临时目录中
        # 如果rootfs_dir是持久化目录，writable_dirs也会持久化
        parent_dir = os.path.dirname(rootfs_dir) if os.path.dirname(rootfs_dir) else rootfs_dir
        writable_storage = os.path.join(parent_dir, 'writable_dirs')
        os.makedirs(writable_storage, exist_ok=True)

        bind_mounts = []

        for dir_path in writable_dirs:
            # 创建主机侧的可写目录
            host_dir = os.path.join(writable_storage, dir_path.replace('/', '_'))
            os.makedirs(host_dir, exist_ok=True)

            # 设置权限
            try:
                os.chmod(host_dir, 0o777)  # 完全可写
            except OSError:
                pass

            # 添加到绑定挂载列表
            container_path = f"/{dir_path}"
            bind_mounts.append(f"{host_dir}:{container_path}")

            logger.debug(f"准备可写目录: {host_dir} -> {container_path}")

        logger.info(f"已准备 {len(bind_mounts)} 个可写系统目录")
        return bind_mounts

    def _prepare_environment(self):
        """准备运行环境，处理Android Termux特殊问题"""
        env = os.environ.copy()

        # 在Android Termux中，需要取消LD_PRELOAD以避免termux-exec干扰
        if self._is_android_environment():
            logger.info("检测到Android环境，调整环境变量...")

            # 取消LD_PRELOAD
            if 'LD_PRELOAD' in env:
                logger.debug("取消LD_PRELOAD以避免termux-exec干扰")
                del env['LD_PRELOAD']

            # 设置更安全的PATH
            termux_path = env.get('PATH', '')
            # 移除可能导致问题的termux特定路径
            path_parts = termux_path.split(':')
            safe_paths = []
            for path in path_parts:
                if not path.startswith('/data/data/com.termux/files/usr/libexec'):
                    safe_paths.append(path)

            env['PATH'] = ':'.join(safe_paths)
            logger.debug(f"调整后的PATH: {env['PATH']}")

        return env
    
    def run(self, input_path, args, rootfs_dir=None, pid_file=None):
        """运行容器（一条龙服务）"""
        log_file_handle = None
        try:
            # 检查依赖
            if not self._check_dependencies():
                return False

            # 在Android环境中显示警告
            if self._is_android_environment():
                logger.warning("在Android环境中运行容器。注意：proot提供进程隔离，而非完整的容器化。某些系统调用可能不受支持，性能可能低于原生Docker。")

            # 准备根文件系统（下载或使用现有）
            logger.info("准备根文件系统...")
            rootfs_dir = self._prepare_rootfs(input_path, args, provided_rootfs_dir=rootfs_dir)
            if not rootfs_dir:
                return False

            self.rootfs_dir = rootfs_dir

            # 如果命令以'--'开头，则移除它
            if args.command and args.command[0] == '--':
                args.command = args.command[1:]

            # 查找镜像配置
            self._find_image_config()

            # 如果是后台运行模式，强制设置为非交互式
            if args.detach:
                args.interactive = False

            # 构建proot命令
            proot_cmd = self._build_proot_command(args)

            logger.info(f"启动容器...")
            logger.debug(f"proot命令: {' '.join(proot_cmd)}")

            # 日志文件处理
            log_file_path = getattr(args, 'log_file', None)
            log_file_handle = None
            if log_file_path:
                try:
                    # Append to the log file
                    log_file_handle = open(log_file_path, 'a')
                except IOError as e:
                    logger.error(f"无法打开日志文件 {log_file_path}: {e}")

            # 运行proot
            if args.detach:
                # 手动实现后台化 (fork/exec)
                env = self._prepare_environment()
                pid_file_path = getattr(args, 'pid_file', None)

                try:
                    pid = os.fork()
                    if pid > 0:
                        # 父进程
                        logger.info(f"容器已在后台启动，PID: {pid}")
                        if pid_file_path:
                            try:
                                with open(pid_file_path, 'w') as f:
                                    f.write(str(pid))
                                logger.debug(f"PID {pid} 已写入 {pid_file_path}")
                            except IOError as e:
                                logger.error(f"写入PID文件失败: {e}")
                        # 父进程成功写入PID后退出
                        return True

                    # 子进程
                    os.setsid() # 创建新会话，脱离控制终端
                    
                    # 重定向标准文件描述符
                    sys.stdout.flush()
                    sys.stderr.flush()
                    
                    stdout_dest = log_file_handle or open(os.devnull, 'wb')
                    stderr_dest = log_file_handle or open(os.devnull, 'wb')
                    
                    os.dup2(stdout_dest.fileno(), sys.stdout.fileno())
                    os.dup2(stderr_dest.fileno(), sys.stderr.fileno())
                    
                    # stdin重定向到/dev/null
                    with open(os.devnull, 'rb') as devnull:
                        os.dup2(devnull.fileno(), sys.stdin.fileno())

                    # 执行proot命令
                    os.execvpe(proot_cmd[0], proot_cmd, env)

                except Exception as e:
                    logger.error(f"后台启动失败 (fork/exec): {e}")
                    # 子进程如果exec失败，需要手动退出
                    sys.exit(1)
            else:
                # 前台运行（交互式或非交互式）
                logger.info("进入容器环境...")
                env = self._prepare_environment()
                
                # 根据是否为交互式模式设置stdin/stdout/stderr
                if getattr(args, 'interactive', False):
                    # 交互式模式：连接到终端
                    subprocess.run(proot_cmd, env=env)
                else:
                    # 非交互式模式：重定向到日志文件（如果提供）
                    subprocess.run(proot_cmd, env=env, stdout=log_file_handle, stderr=log_file_handle)
                return True

        except KeyboardInterrupt:
            logger.info("用户中断")
            return True
        except Exception as e:
            logger.error(f"运行失败: {e}")
            return False
        finally:
            # 关闭日志文件句柄
            if log_file_handle:
                log_file_handle.close()

            # 只有在前台运行时，并且我们创建了临时目录时，才进行清理
            if hasattr(args, 'detach') and not args.detach:
                self._cleanup()
    
    def _cleanup(self):
        """清理临时文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            logger.info(f"清理临时目录: {self.temp_dir}")

    def list_cache(self):
        """列出缓存的镜像"""
        if not os.path.exists(self.cache_dir):
            logger.info("缓存目录不存在")
            return

        cache_files = []
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.tar.gz'):
                cache_path = os.path.join(self.cache_dir, filename)
                info_path = cache_path + '.info'

                # 获取文件信息
                stat = os.stat(cache_path)
                size_mb = stat.st_size / 1024 / 1024

                # 尝试读取缓存信息
                image_url = "Unknown"
                created_time = "Unknown"

                if os.path.exists(info_path):
                    try:
                        with open(info_path, 'r') as f:
                            info = json.load(f)
                        image_url = info.get('image_url', 'Unknown')
                        created_time = info.get('created_time_str', 'Unknown')
                    except Exception:
                        pass

                cache_files.append({
                    'filename': filename,
                    'image_url': image_url,
                    'size_mb': size_mb,
                    'created_time': created_time
                })

        if not cache_files:
            logger.info("没有缓存的镜像")
            return

        logger.info(f"缓存目录: {self.cache_dir}")
        logger.info(f"共有 {len(cache_files)} 个缓存镜像:")
        logger.info("-" * 80)

        for cache in cache_files:
            logger.info(f"文件: {cache['filename']}")
            logger.info(f"镜像: {cache['image_url']}")
            logger.info(f"大小: {cache['size_mb']:.2f} MB")
            logger.info(f"创建时间: {cache['created_time']}")
            logger.info("-" * 80)

    def clear_cache(self, image_url=None):
        """清理缓存"""
        if image_url:
            # 清理特定镜像的缓存
            cache_path = self._get_image_cache_path(image_url)
            info_path = self._get_cache_info_path(image_url)

            removed = False
            for path in [cache_path, info_path]:
                if os.path.exists(path):
                    os.remove(path)
                    removed = True

            if removed:
                logger.info(f"已清理镜像缓存: {image_url}")
            else:
                logger.info(f"镜像未缓存: {image_url}")
        else:
            # 清理所有缓存
            if os.path.exists(self.cache_dir):
                shutil.rmtree(self.cache_dir)
                self._ensure_cache_dir()
                logger.info("已清理所有缓存")
            else:
                logger.info("缓存目录不存在")

def main():
    parser = argparse.ArgumentParser(
        description='使用proot运行Docker镜像的一条龙服务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 直接运行镜像URL
  %(prog)s alpine:latest
  %(prog)s swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/snailyp/gemini-balance:latest-linuxarm64

  # 带环境变量运行
  %(prog)s -e "API_KEY=sk-12345" -e "MODE=test" alpine:latest env

  # 使用本地根文件系统
  %(prog)s -b /host/data:/container/data rootfs.tar.gz /bin/bash

  # 后台运行
  %(prog)s -w /app -d nginx:alpine
  
  # 交互式运行
  %(prog)s -it alpine:latest /bin/sh

  # 缓存管理
  %(prog)s --list-cache
  %(prog)s --clear-cache alpine:latest
        """
    )

    parser.add_argument(
        'image_or_rootfs',
        nargs='?',
        help='Docker镜像URL或根文件系统路径（tar文件或目录）'
    )
    
    parser.add_argument(
        'command',
        nargs='*',
        help='要执行的命令（默认使用镜像的默认命令）'
    )
    
    parser.add_argument(
        '-e', '--env',
        action='append',
        default=[],
        help='设置环境变量 (格式: KEY=VALUE)'
    )
    
    parser.add_argument(
        '-b', '--bind',
        action='append', 
        default=[],
        help='绑定挂载 (格式: HOST_PATH:CONTAINER_PATH)'
    )
    
    parser.add_argument(
        '-w', '--workdir',
        help='工作目录'
    )
    
    parser.add_argument(
        '-d', '--detach',
        action='store_true',
        help='后台运行'
    )
    
    parser.add_argument(
        '-it', '--interactive',
        action='store_true',
        help='交互式运行容器 (分配伪TTY并保持stdin打开)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )

    parser.add_argument(
        '--force-download',
        action='store_true',
        help='强制重新下载镜像，忽略缓存'
    )

    parser.add_argument(
        '--cache-dir',
        help='指定缓存目录路径'
    )
    parser.add_argument('--username', help='Registry用户名')
    parser.add_argument('--password', help='Registry密码')

    parser.add_argument(
        '--rootfs-dir',
        help='指定持久化的根文件系统路径 (主要由docker_cli.py在后台模式下使用)'
    )
    parser.add_argument(
        '--pid-file',
        help='在后台模式下保存真实PID的文件路径 (主要由docker_cli.py在后台模式下使用)'
    )

    parser.add_argument(
        '--log-file',
        help='在后台模式下保存容器内部stdout/stderr的文件路径 (主要由docker_cli.py使用)'
    )
    
    parser.add_argument(
        '--list-cache',
        action='store_true',
        help='列出缓存的镜像'
    )

    parser.add_argument(
        '--clear-cache',
        metavar='IMAGE_URL',
        help='清理指定镜像的缓存，或使用"all"清理所有缓存'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 创建runner实例
    runner = ProotRunner(cache_dir=args.cache_dir)

    # 处理缓存管理命令
    if args.list_cache:
        runner.list_cache()
        return

    if args.clear_cache:
        if args.clear_cache.lower() == 'all':
            runner.clear_cache()
        else:
            runner.clear_cache(args.clear_cache)
        return

    # 检查是否提供了镜像或根文件系统
    if not args.image_or_rootfs:
        parser.error("请提供Docker镜像URL或根文件系统路径")

    # Run container
    success = runner.run(args.image_or_rootfs, args, rootfs_dir=args.rootfs_dir, pid_file=args.pid_file)

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
