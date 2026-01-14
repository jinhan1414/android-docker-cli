#!/usr/bin/env python3
"""
使用curl和Python制作根文件系统tar包的脚本
用于在Android Termux中通过proot执行Docker镜像
无需requests库和umoci，只需要curl命令行工具和Python标准库
"""

import os
import sys
import subprocess
import tempfile
import shutil
import argparse
import logging
import json
import hashlib
import tarfile
import gzip
import time
from pathlib import Path
from urllib.parse import urlparse
import platform

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DockerRegistryClient:
    """Docker Registry API客户端，使用curl下载镜像"""

    def __init__(self, registry_url, image_name, tag='latest', username=None, password=None):
        self.registry_url = registry_url
        self.image_name = image_name
        self.tag = tag
        self.auth_token = None
        self.user_agent = 'docker-rootfs-creator/1.0'
        self.username = username
        self.password = password

    def _run_curl_command(self, cmd, print_cmd=True):
        """执行并打印curl命令"""
        if print_cmd:
            # 为了安全，打印命令时隐藏密码
            safe_cmd = []
            i = 0
            while i < len(cmd):
                safe_cmd.append(cmd[i])
                if cmd[i] == '-u' and i + 1 < len(cmd):
                    safe_cmd.append(f"{cmd[i+1].split(':')[0]}:***")
                    i += 1
                i += 1
            logger.info(f"---\n[ 执行命令 ]\n{' '.join(safe_cmd)}\n---")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if not result.stdout and not result.stderr:
                # 记录警告而不是抛出异常，以增加网络弹性
                logger.warning(f"curl命令返回空响应: {' '.join(cmd)}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"!!! curl命令执行失败 (错误码: {e.returncode}) !!!")
            logger.error(f"""---
[ 错误输出 ]
---\n{e.stderr.strip()}""")
            raise

    def _get_auth_token(self, www_authenticate_header):
        """从WWW-Authenticate头获取认证token"""
        if not www_authenticate_header:
            return None

        # 解析Bearer token信息
        if www_authenticate_header.startswith('Bearer '):
            auth_info = {}
            bearer_info = www_authenticate_header[7:]  # 移除'Bearer '

            for item in bearer_info.split(','):
                if '=' in item:
                    key, value = item.split('=', 1)
                    auth_info[key.strip()] = value.strip('"')

            if 'realm' in auth_info:
                # 构建认证URL
                auth_url = auth_info['realm']
                params = []
                if 'service' in auth_info:
                    params.append(f"service={auth_info['service']}")
                if 'scope' in auth_info:
                    params.append(f"scope={auth_info['scope']}")

                if params:
                    auth_url += '?' + '&'.join(params)

                # 使用curl获取token
                try:
                    cmd = ['curl', '-v'] # Token获取不需要-i
                    if self.username and self.password:
                        cmd.extend(['-u', f'{self.username}:{self.password}'])
                    cmd.extend(['-H', f'User-Agent: {self.user_agent}', auth_url])
                    
                    # 为了简单起见，我们直接调用，不再通过_run_curl_command
                    # 因为代理已经通过环境变量设置
                    logger.info("""---
[ 步骤 2/3: 获取认证Token ]
---""")
                    result = self._run_curl_command(cmd)
                    token_data = json.loads(result.stdout)
                    return token_data.get('token')
                except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                    logger.warning(f"获取认证token失败: {e}")
                    # 在失败时打印可手动执行的命令
                    if isinstance(e, subprocess.CalledProcessError):
                        logger.warning(f"您可以手动运行以下命令测试token获取:\n{' '.join(cmd)}")
                    return None

        return None

    def _make_registry_request(self, path, headers=None, output_file=None):
        """向registry发送请求，处理认证"""
        # 步骤1：先发一个请求获取认证头
        if not self.auth_token:
            url = f"{self.registry_url}/v2/{path}"
            cmd = ['curl', '-v', '-i', '--insecure', url]
            logger.info("""---
[ 步骤 1/3: 探测认证服务器 ]
---""")
            result = self._run_curl_command(cmd)
            
            auth_header = None
            for line in result.stdout.split('\n'):
                if line.lower().startswith('www-authenticate:'):
                    auth_header = line.split(':', 1)[1].strip()
                    break
            
            if auth_header:
                # 步骤2：使用认证头获取token
                token = self._get_auth_token(auth_header)
                if token:
                    self.auth_token = token
                    logger.info("✓ 成功获取认证Token")
                else:
                    logger.error("✗ 获取认证Token失败，将尝试匿名访问...")
            else:
                logger.warning("未找到 'Www-Authenticate' 头，尝试匿名请求...")

        # 步骤3：使用token（或匿名）发送最终请求
        url = f"{self.registry_url}/v2/{path}"
        cmd = ['curl', '-v', '-i', '--insecure', '-H', f'User-Agent: {self.user_agent}']

        # Always include comprehensive Accept headers for manifest requests
        # This ensures compatibility with both OCI and Docker v2 registries
        if 'manifests' in path:
            comprehensive_accept = ', '.join([
                'application/vnd.oci.image.manifest.v1+json',
                'application/vnd.oci.image.index.v1+json',
                'application/vnd.docker.distribution.manifest.v2+json',
                'application/vnd.docker.distribution.manifest.list.v2+json'
            ])
            cmd.extend(['-H', f'Accept: {comprehensive_accept}'])

        if headers:
            for key, value in headers.items():
                # Skip Accept header if we already added comprehensive one
                if key.lower() == 'accept' and 'manifests' in path:
                    continue
                cmd.extend(['-H', f'{key}: {value}'])

        if self.auth_token:
            cmd.extend(['-H', f'Authorization: Bearer {self.auth_token}'])

        if output_file:
            cmd.extend(['-o', output_file])

        cmd.append(url)
        logger.info("""---
[ 步骤 3/3: 获取镜像Manifest ]
---""")
        result = self._run_curl_command(cmd)

        # 解析响应，处理可能存在的多个HTTP头（例如重定向）
        response_text = result.stdout
        
        # 找到最后一个HTTP头块
        last_header_block_start = response_text.rfind('HTTP/')
        
        # 分离最后的头和body
        if last_header_block_start != -1:
            response_part = response_text[last_header_block_start:]
            if '\r\n\r\n' in response_part:
                headers_text, body = response_part.split('\r\n\r\n', 1)
            elif '\n\n' in response_part:
                headers_text, body = response_part.split('\n\n', 1)
            else:
                headers_text = response_part
                body = ''
        else:
            # 如果找不到 "HTTP/"，则假定整个响应都是body（不太可能发生）
            headers_text = ''
            body = response_text

        # 解析状态码和headers
        lines = headers_text.split('\n')
        status_line = lines[0] if lines else ''
        if ' ' in status_line:
            try:
                status_code = int(status_line.split()[1])
            except (ValueError, IndexError):
                status_code = 0 # 无法解析状态码
        else:
            status_code = 0

        response_headers = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                response_headers[key.strip().lower()] = value.strip()

        # 如果需要认证且还没有token
        # 由于我们已经预先获取了token，这里不再需要处理401

        if status_code >= 400:
            raise Exception(f"HTTP {status_code}: {body}")

        return {
            'status_code': status_code,
            'headers': response_headers,
            'body': body
        }

    def get_manifest(self):
        """获取镜像manifest"""
        logger.info(f"获取镜像manifest: {self.image_name}:{self.tag}")

        # 支持多种manifest格式
        accept_headers = [
            'application/vnd.docker.distribution.manifest.v2+json',
            'application/vnd.docker.distribution.manifest.list.v2+json',
            'application/vnd.oci.image.manifest.v1+json',
            'application/vnd.oci.image.index.v1+json'
        ]

        headers = {
            'Accept': ', '.join(accept_headers)
        }

        path = f"{self.image_name}/manifests/{self.tag}"
        response = self._make_registry_request(path, headers)

        manifest = json.loads(response['body'])
        content_type = response['headers'].get('content-type', '')

        logger.info(f"Manifest类型: {content_type}")
        return manifest, content_type

    def download_blob(self, digest, output_path):
        """下载blob到指定路径"""
        logger.info(f"下载blob: {digest}")

        path = f"{self.image_name}/blobs/{digest}"

        # 直接下载到文件
        cmd = ['curl', '-v', '-L', '-H', f'User-Agent: {self.user_agent}']

        # 如果有认证token，添加Authorization头
        if self.auth_token:
            cmd.extend(['-H', f'Authorization: Bearer {self.auth_token}'])

        url = f"{self.registry_url}/v2/{path}"
        cmd.extend(['-o', output_path, url])

        self._run_curl_command(cmd)

        logger.debug(f"Blob已保存到: {output_path}")
        return output_path

class DockerImageToRootFS:
    def __init__(self, image_url, output_path=None, username=None, password=None, architecture=None):
        self.image_url = image_url
        self.output_path = output_path or f"{self._get_image_name()}_rootfs.tar"
        self.temp_dir = None
        self.username = username
        self.password = password
        self.architecture = architecture or self._get_current_architecture()
        logger.info(f"目标架构: {self.architecture}")
        
    def _get_current_architecture(self):
        """获取当前系统的架构，并标准化为Docker/OCI格式"""
        machine = platform.machine().lower()
        
        # 架构映射字典
        arch_map = {
            'x86_64': 'amd64',
            'amd64': 'amd64',
            'aarch64': 'arm64',  # 关键标准化：aarch64 → arm64
            'arm64': 'arm64',
            'armv7l': 'arm',
            'armv6l': 'arm',
            'i386': '386',
            'i686': '386',
        }
        
        normalized = arch_map.get(machine)
        if normalized:
            if machine == 'aarch64':
                logger.info(f"架构标准化: {machine} → {normalized}")
            return normalized
        else:
            logger.warning(f"无法识别的架构: {machine}, 将默认使用 amd64")
            return 'amd64'

    def _get_image_name(self):
        """从镜像URL中提取镜像名称"""
        # 从URL中提取镜像名称，去掉域名和标签
        parts = self.image_url.split('/')
        image_name = parts[-1].split(':')[0]
        return image_name
    
    def _check_dependencies(self):
        """检查curl是否已安装"""
        # 检查curl
        try:
            subprocess.run(['curl', '--version'],
                         capture_output=True, check=True)
            logger.info("✓ curl 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("✗ curl 未安装")
            logger.info("请安装curl命令行工具")
            return False

        # 检查tar命令
        try:
            subprocess.run(['tar', '--version'],
                         capture_output=True, check=True)
            logger.info("✓ tar 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("✗ tar 未安装")
            logger.info("请安装tar命令行工具")
            return False

        return True
    
    def _run_command(self, cmd, cwd=None):
        """执行命令并处理错误"""
        logger.info(f"执行命令: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, 
                cwd=cwd,
                capture_output=True, 
                text=True, 
                check=True
            )
            if result.stdout:
                logger.debug(f"输出: {result.stdout}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"命令执行失败: {' '.join(cmd)}")
            logger.error(f"错误码: {e.returncode}")
            logger.error(f"错误输出: {e.stderr}")
            raise
    
    def _create_temp_directory(self):
        """创建临时工作目录"""
        self.temp_dir = tempfile.mkdtemp(prefix='docker_rootfs_')
        logger.info(f"创建临时目录: {self.temp_dir}")
        return self.temp_dir
    
    def _cleanup_temp_directory(self):
        """清理临时目录"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            # shutil.rmtree(self.temp_dir)
            logger.info(f"清理临时目录: {self.temp_dir}")

    def _parse_image_url(self):
        """解析镜像URL，提取registry、镜像名和标签"""
        image_url = self.image_url

        # 默认值
        registry = "registry-1.docker.io"
        image_name = ""
        tag = "latest"

        # 移除docker://前缀（如果存在）
        if image_url.startswith('docker://'):
            image_url = image_url[9:]

        # 分离标签
        # 改进的标签分离逻辑
        if ':' in image_url:
            # 检查冒号是否在最后一个斜杠之后，或者根本没有斜杠
            last_colon = image_url.rfind(':')
            last_slash = image_url.rfind('/')
            if last_colon > last_slash:
                # 适用于 a/b:tag, a:123/b:tag, a:tag
                image_url, tag = image_url.rsplit(':', 1)

        # 分离registry和镜像名
        if '/' in image_url:
            parts = image_url.split('/', 1)
            if '.' in parts[0] or ':' in parts[0]:  # 包含域名
                registry = parts[0]
                image_name = parts[1]
            else:  # Docker Hub的简写形式
                registry = "registry-1.docker.io"
                image_name = image_url
                # Docker Hub的library镜像需要添加library/前缀
                if '/' not in image_name:
                    image_name = f"library/{image_name}"
        else:
            # 只有镜像名，使用Docker Hub
            registry = "registry-1.docker.io"
            image_name = f"library/{image_url}"

        # 确保registry有协议前缀
        if not registry.startswith(('http://', 'https://')):
            registry = f"https://{registry}"

        logger.info(f"解析镜像URL: registry={registry}, image={image_name}, tag={tag}")
        return registry, image_name, tag
    
    def _download_image_with_python(self):
        """使用Python下载Docker镜像到OCI格式"""
        oci_dir = os.path.join(self.temp_dir, 'oci')
        os.makedirs(oci_dir, exist_ok=True)

        # 解析镜像URL
        registry, image_name, tag = self._parse_image_url()

        # 创建registry客户端
        client = DockerRegistryClient(registry, image_name, tag, self.username, self.password)

        # 获取manifest
        manifest, content_type = client.get_manifest()

        # 如果是manifest list，根据架构选择一个具体的manifest
        if 'manifest.list' in content_type or 'image.index' in content_type:
            logger.info("检测到manifest list，正在寻找匹配的架构...")
            
            selected_manifest_descriptor = None
            for manifest_descriptor in manifest.get('manifests', []):
                platform_info = manifest_descriptor.get('platform', {})
                manifest_arch = platform_info.get('architecture')
                
                # 架构等效性检查：aarch64 和 arm64 视为等效
                arch_match = (manifest_arch == self.architecture or 
                             (self.architecture == 'arm64' and manifest_arch == 'aarch64') or
                             (self.architecture == 'aarch64' and manifest_arch == 'arm64'))
                
                if arch_match:
                    # 优先选择与OS匹配的，如果没有os字段则直接匹配
                    if platform_info.get('os') == 'linux' or 'os' not in platform_info:
                        selected_manifest_descriptor = manifest_descriptor
                        break
            
            if selected_manifest_descriptor:
                target_digest = selected_manifest_descriptor['digest']
                logger.info(f"找到匹配架构 '{self.architecture}' 的manifest: {target_digest}")
                
                # 获取子manifest
                logger.info(f"""---
[ 步骤 3/3: 获取镜像Manifest ]
---""")
                response = client._make_registry_request(f"{client.image_name}/manifests/{target_digest}")
                manifest = json.loads(response['body'])
                content_type = response['headers'].get('content-type', '') # 更新content_type
                logger.info(f"已选择子manifest，类型: {content_type}")
            else:
                available_archs = [m.get('platform', {}).get('architecture') for m in manifest.get('manifests', [])]
                raise ValueError(f"在manifest list中找不到适用于架构 '{self.architecture}' 的镜像。可用架构: {', '.join(filter(None, available_archs))}")

        # 创建OCI目录结构
        blobs_dir = os.path.join(oci_dir, 'blobs', 'sha256')
        os.makedirs(blobs_dir, exist_ok=True)

        # 保存manifest
        manifest_digest = self._save_manifest(oci_dir, manifest, content_type)

        # 下载所有层和config
        self._download_layers(client, manifest, blobs_dir)

        # 转换config blob为OCI格式
        if 'config' in manifest:
            self._convert_config_blob(client, manifest['config'], blobs_dir)

        # 创建oci-layout文件
        self._create_oci_layout(oci_dir)

        # 创建index.json
        self._create_oci_index(oci_dir, manifest_digest, content_type)

        logger.info(f"镜像已下载到OCI格式: {oci_dir}")
        return oci_dir

    def _save_manifest(self, oci_dir, manifest, content_type):
        """保存manifest并返回其digest，转换为OCI格式"""
        # 转换Docker格式的manifest为OCI格式
        oci_manifest = self._convert_manifest_to_oci(manifest, content_type)

        manifest_json = json.dumps(oci_manifest, separators=(',', ':'))
        manifest_bytes = manifest_json.encode('utf-8')

        # 计算digest
        digest = hashlib.sha256(manifest_bytes).hexdigest()

        # 保存到blobs目录
        blobs_dir = os.path.join(oci_dir, 'blobs', 'sha256')
        manifest_path = os.path.join(blobs_dir, digest)

        with open(manifest_path, 'wb') as f:
            f.write(manifest_bytes)

        logger.debug(f"OCI Manifest已保存: sha256:{digest}")
        return f"sha256:{digest}"

    def _convert_manifest_to_oci(self, manifest, content_type):
        """将Docker manifest转换为OCI格式"""
        if 'docker' not in content_type:
            # 已经是OCI格式
            return manifest

        oci_manifest = manifest.copy()

        # 转换媒体类型
        if 'layers' in oci_manifest:
            for layer in oci_manifest['layers']:
                if layer.get('mediaType') == 'application/vnd.docker.image.rootfs.diff.tar.gzip':
                    layer['mediaType'] = 'application/vnd.oci.image.layer.v1.tar+gzip'
                elif layer.get('mediaType') == 'application/vnd.docker.image.rootfs.diff.tar':
                    layer['mediaType'] = 'application/vnd.oci.image.layer.v1.tar'

        if 'config' in oci_manifest:
            if oci_manifest['config'].get('mediaType') == 'application/vnd.docker.container.image.v1+json':
                oci_manifest['config']['mediaType'] = 'application/vnd.oci.image.config.v1+json'

        # 设置正确的媒体类型
        oci_manifest['mediaType'] = 'application/vnd.oci.image.manifest.v1+json'

        logger.debug("已将Docker manifest转换为OCI格式")
        return oci_manifest

    def _convert_config_blob(self, client, config_descriptor, blobs_dir):
        """转换config blob为OCI格式"""
        digest = config_descriptor['digest']

        if digest.startswith('sha256:'):
            digest_hash = digest[7:]
        else:
            digest_hash = digest

        config_path = os.path.join(blobs_dir, digest_hash)

        # 读取原始config
        if not os.path.exists(config_path):
            logger.error(f"Config blob不存在: {config_path}")
            return

        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)

            # 转换Docker config为OCI config
            oci_config = self._convert_docker_config_to_oci(config_data)

            # 重新保存转换后的config
            with open(config_path, 'w') as f:
                json.dump(oci_config, f, separators=(',', ':'))

            logger.debug(f"已转换config blob为OCI格式: {digest}")

        except Exception as e:
            logger.warning(f"转换config blob失败: {e}")

    def _convert_docker_config_to_oci(self, docker_config):
        """将Docker config转换为OCI config"""
        oci_config = docker_config.copy()

        # OCI config的基本结构与Docker config类似，但有一些字段差异
        # 主要是确保必要的字段存在

        if 'architecture' not in oci_config:
            oci_config['architecture'] = 'amd64'

        if 'os' not in oci_config:
            oci_config['os'] = 'linux'

        # 确保config字段存在
        if 'config' not in oci_config:
            oci_config['config'] = {}

        # 确保rootfs字段存在
        if 'rootfs' not in oci_config:
            oci_config['rootfs'] = {
                'type': 'layers',
                'diff_ids': []
            }

        # 确保history字段存在
        if 'history' not in oci_config:
            oci_config['history'] = []

        return oci_config

    def _download_layers(self, client, manifest, blobs_dir):
        """下载镜像的所有层"""
        # 处理不同类型的manifest
        layers = []

        if 'layers' in manifest and manifest['layers']:
            # Docker v2 manifest 或 OCI manifest
            layers = manifest['layers'][:]
            if 'config' in manifest:
                layers.append(manifest['config'])
        elif 'fsLayers' in manifest and manifest['fsLayers']:
            # Docker v1 manifest (已废弃，但仍需支持)
            layers = manifest['fsLayers'][:]
            if 'history' in manifest:
                # v1 manifest的config信息在history中
                pass
        # manifest list 的处理已移到调用方
        elif not layers:
            raise ValueError("Manifest中没有找到'layers'或'fsLayers'字段，或者它们为空")

        for layer in layers:
            digest = layer.get('digest') or layer.get('blobSum')
            if digest:
                # 移除sha256:前缀用于文件名
                if digest.startswith('sha256:'):
                    digest_hash = digest[7:]
                else:
                    digest_hash = digest

                blob_path = os.path.join(blobs_dir, digest_hash)
                if not os.path.exists(blob_path):
                    try:
                        client.download_blob(digest, blob_path)
                        logger.debug(f"已下载层: {digest}")
                    except Exception as e:
                        logger.error(f"下载层失败 {digest}: {e}")
                        raise

    def _create_oci_index(self, oci_dir, manifest_digest, content_type):
        """创建OCI index.json文件"""
        # 确保content_type符合OCI规范
        if 'docker' in content_type:
            # 将Docker格式转换为OCI格式
            if 'manifest.v2+json' in content_type:
                oci_content_type = "application/vnd.oci.image.manifest.v1+json"
            elif 'manifest.list.v2+json' in content_type:
                oci_content_type = "application/vnd.oci.image.index.v1+json"
            else:
                oci_content_type = content_type
        else:
            oci_content_type = content_type

        # 获取manifest文件大小
        manifest_file_path = os.path.join(oci_dir, 'blobs', 'sha256', manifest_digest[7:])
        manifest_size = os.path.getsize(manifest_file_path) if os.path.exists(manifest_file_path) else 0

        index = {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": oci_content_type,
                    "digest": manifest_digest,
                    "size": manifest_size,
                    "annotations": {
                        "org.opencontainers.image.ref.name": "latest"
                    }
                }
            ]
        }

        index_path = os.path.join(oci_dir, 'index.json')
        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)

        logger.debug(f"OCI index已创建: {index_path}")
        logger.debug(f"使用content type: {oci_content_type}")

    def _create_oci_layout(self, oci_dir):
        """创建oci-layout文件"""
        layout = {
            "imageLayoutVersion": "1.0.0"
        }

        layout_path = os.path.join(oci_dir, 'oci-layout')
        with open(layout_path, 'w') as f:
            json.dump(layout, f, indent=2)

        logger.debug(f"OCI layout已创建: {layout_path}")

    def _save_image_config(self, oci_dir, rootfs_dir):
        """保存镜像配置到根文件系统中，供proot_runner使用"""
        try:
            # 读取OCI index
            index_path = os.path.join(oci_dir, 'index.json')
            with open(index_path, 'r') as f:
                index = json.load(f)

            # 获取manifest
            manifest_descriptor = index['manifests'][0]
            manifest_digest = manifest_descriptor['digest']
            manifest_path = os.path.join(oci_dir, 'blobs', 'sha256', manifest_digest[7:])

            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            # 获取config
            if 'config' in manifest:
                config_digest = manifest['config']['digest']
                config_path = os.path.join(oci_dir, 'blobs', 'sha256', config_digest[7:])

                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)

                    # 保存配置到根文件系统
                    config_save_path = os.path.join(rootfs_dir, '.image_config.json')
                    with open(config_save_path, 'w') as f:
                        json.dump(config_data, f, indent=2)

                    logger.info(f"镜像配置已保存到: {config_save_path}")

                    # 显示一些有用的信息
                    config = config_data.get('config', {})
                    if 'Cmd' in config:
                        logger.info(f"默认命令: {config['Cmd']}")
                    if 'Entrypoint' in config:
                        logger.info(f"入口点: {config['Entrypoint']}")
                    if 'WorkingDir' in config:
                        logger.info(f"工作目录: {config['WorkingDir']}")
                    if 'Env' in config:
                        logger.info(f"环境变量: {len(config['Env'])} 个")
                else:
                    logger.warning("未找到config blob")
            else:
                logger.warning("manifest中没有config信息")

        except Exception as e:
            logger.warning(f"保存镜像配置失败: {e}")
            # 不影响主要流程，继续执行
    
    def _extract_rootfs_with_python(self, oci_dir):
        """使用Python提取根文件系统"""
        rootfs_dir = os.path.join(self.temp_dir, 'rootfs')
        os.makedirs(rootfs_dir, exist_ok=True)

        # 读取OCI index
        index_path = os.path.join(oci_dir, 'index.json')
        with open(index_path, 'r') as f:
            index = json.load(f)

        # 获取manifest
        manifest_descriptor = index['manifests'][0]
        manifest_digest = manifest_descriptor['digest']
        manifest_path = os.path.join(oci_dir, 'blobs', 'sha256', manifest_digest[7:])

        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        logger.info(f"开始提取 {len(manifest.get('layers', []))} 个层")

        # 提取所有层
        layers = manifest.get('layers', [])
        for i, layer in enumerate(layers, 1):
            layer_digest = layer['digest']
            layer_path = os.path.join(oci_dir, 'blobs', 'sha256', layer_digest[7:])

            logger.info(f"提取层 {i}/{len(layers)}: {layer_digest}")

            # 第一层使用严格模式，后续层使用宽松模式
            is_first_layer = (i == 1)
            self._extract_layer(layer_path, rootfs_dir, is_first_layer)

        logger.info(f"根文件系统已提取到: {rootfs_dir}")
        
        # 验证关键文件是否存在
        missing_files = self._validate_critical_files(rootfs_dir)
        if missing_files:
            error_msg = f"提取后缺少关键文件: {', '.join(missing_files)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        return rootfs_dir

    def _extract_layer(self, layer_path, rootfs_dir, is_first_layer=False):
        """提取单个层到根文件系统目录"""
        # 在Android环境中优先使用tar命令，因为它对硬链接处理更好
        if self._is_android_environment():
            try:
                self._extract_layer_with_tar(layer_path, rootfs_dir, is_first_layer)
                return
            except Exception as e:
                logger.warning(f"tar命令提取失败: {e}")
                logger.info("尝试使用Python tarfile模块...")

        try:
            # 使用Python的tarfile模块
            self._extract_layer_with_python(layer_path, rootfs_dir)
        except Exception as e:
            logger.warning(f"Python tarfile提取失败: {e}")
            # 如果还没试过tar命令，现在试试
            if not self._is_android_environment():
                self._extract_layer_with_tar(layer_path, rootfs_dir, is_first_layer)

    def _extract_layer_with_python(self, layer_path, rootfs_dir):
        """使用Python tarfile模块提取层"""
        import tarfile
        import gzip

        # 检测文件类型
        with open(layer_path, 'rb') as f:
            magic = f.read(2)

        try:
            if magic == b'\x1f\x8b':  # gzip magic number
                # 这是一个gzip压缩的tar文件
                with gzip.open(layer_path, 'rb') as gz_file:
                    with tarfile.open(fileobj=gz_file, mode='r|*') as tar:
                        self._safe_extract_tar(tar, rootfs_dir)
            else:
                # 尝试作为普通tar文件
                with tarfile.open(layer_path, 'r') as tar:
                    self._safe_extract_tar(tar, rootfs_dir)
        except Exception as e:
            # 如果流式读取失败，尝试非流式
            logger.debug(f"流式提取失败，尝试非流式: {e}")
            if magic == b'\x1f\x8b':
                with tarfile.open(layer_path, 'r:gz') as tar:
                    self._safe_extract_tar(tar, rootfs_dir)
            else:
                with tarfile.open(layer_path, 'r') as tar:
                    self._safe_extract_tar(tar, rootfs_dir)

    def _safe_extract_tar(self, tar, rootfs_dir):
        """安全地提取tar文件，处理特殊情况（增强Android支持）"""
        whiteout_count = 0
        
        # 设置提取过滤器以避免警告
        def extract_filter(member, path):
            nonlocal whiteout_count
            
            # 跳过whiteout文件
            if member.name.startswith('.wh.') or '/.wh.' in member.name:
                logger.debug(f"跳过whiteout文件: {member.name}")
                whiteout_count += 1
                return None

            # 跳过设备文件和特殊文件
            if member.isdev() or member.isfifo():
                logger.debug(f"跳过设备/FIFO文件: {member.name}")
                return None

            # 处理路径安全性
            if member.name.startswith('/') or '..' in member.name:
                logger.warning(f"跳过不安全的路径: {member.name}")
                return None

            # 在Android环境中，重置权限以避免问题
            if self._is_android_environment():
                if member.isfile():
                    member.mode = 0o644
                elif member.isdir():
                    member.mode = 0o755
                # 重置所有者信息
                member.uid = 0
                member.gid = 0
                member.uname = 'root'
                member.gname = 'root'

            return member

        # 手动处理每个成员，更好地控制提取过程
        for member in tar:
            try:
                # 应用过滤器
                filtered_member = extract_filter(member, rootfs_dir)
                if not filtered_member:
                    continue

                # 特殊处理硬链接
                if member.islnk():
                    # 将硬链接转换为普通文件或符号链接
                    self._handle_hardlink(tar, member, rootfs_dir)
                    continue

                # 正常提取
                tar.extract(filtered_member, rootfs_dir)

            except (OSError, PermissionError, tarfile.ExtractError) as e:
                logger.debug(f"提取文件失败 {member.name}: {e}")

                # 尝试手动创建文件
                if member.isfile():
                    self._manual_extract_file(tar, member, rootfs_dir)
                elif member.isdir():
                    self._manual_create_dir(member, rootfs_dir)
                elif member.islnk():
                    self._handle_hardlink(tar, member, rootfs_dir)
                elif member.issym():
                    self._manual_create_symlink(member, rootfs_dir)
        
        # 如果跳过了whiteout文件，记录警告
        if whiteout_count > 0:
            if self._is_android_environment():
                logger.warning(f"在Android环境中跳过了 {whiteout_count} 个whiteout文件。层删除语义可能不完全保留。")
            else:
                logger.info(f"跳过了 {whiteout_count} 个whiteout文件")

    def _handle_hardlink(self, tar, member, rootfs_dir):
        """处理硬链接，转换为普通文件"""
        try:
            target_path = os.path.join(rootfs_dir, member.name)
            link_target_path = os.path.join(rootfs_dir, member.linkname)

            # 如果链接目标存在，复制文件内容
            if os.path.exists(link_target_path):
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(link_target_path, target_path)
                logger.debug(f"硬链接转换为文件副本: {member.name} -> {member.linkname}")
            else:
                # 如果目标不存在，尝试从tar中提取原始文件
                logger.debug(f"硬链接目标不存在，跳过: {member.name} -> {member.linkname}")
        except Exception as e:
            logger.debug(f"处理硬链接失败 {member.name}: {e}")

    def _manual_extract_file(self, tar, member, rootfs_dir):
        """手动提取文件"""
        try:
            target_path = os.path.join(rootfs_dir, member.name)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, 'wb') as target_file:
                source_file = tar.extractfile(member)
                if source_file:
                    shutil.copyfileobj(source_file, target_file)

            # 设置基本权限
            try:
                os.chmod(target_path, 0o644 if not (member.mode & 0o111) else 0o755)
            except OSError:
                pass

        except Exception as e:
            logger.debug(f"手动提取文件失败 {member.name}: {e}")

    def _manual_create_dir(self, member, rootfs_dir):
        """手动创建目录"""
        try:
            target_path = os.path.join(rootfs_dir, member.name)
            os.makedirs(target_path, exist_ok=True)
            try:
                os.chmod(target_path, 0o755)
            except OSError:
                pass
        except Exception as e:
            logger.debug(f"手动创建目录失败 {member.name}: {e}")

    def _manual_create_symlink(self, member, rootfs_dir):
        """手动创建符号链接"""
        try:
            target_path = os.path.join(rootfs_dir, member.name)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # 如果目标已存在，先删除
            if os.path.exists(target_path) or os.path.islink(target_path):
                os.remove(target_path)

            os.symlink(member.linkname, target_path)
        except Exception as e:
            logger.debug(f"手动创建符号链接失败 {member.name}: {e}")

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

    def _validate_critical_files(self, rootfs_dir):
        """验证关键文件是否存在"""
        missing_files = []
        
        # 检查shell
        shells = ['/bin/sh', '/bin/bash', '/bin/ash']
        has_shell = False
        for shell in shells:
            shell_path = os.path.join(rootfs_dir, shell.lstrip('/'))
            if os.path.exists(shell_path):
                has_shell = True
                break
        
        if not has_shell:
            missing_files.append('shell (checked: /bin/sh, /bin/bash, /bin/ash)')
        
        # 检查lib目录
        lib_dirs = ['/lib', '/lib64', '/usr/lib']
        has_lib = False
        for lib_dir in lib_dirs:
            lib_path = os.path.join(rootfs_dir, lib_dir.lstrip('/'))
            if os.path.exists(lib_path) and os.path.isdir(lib_path) and os.listdir(lib_path):
                has_lib = True
                break
        
        if not has_lib:
            missing_files.append('library directory (checked: /lib, /lib64, /usr/lib)')
        
        # 检查/usr/bin
        usr_bin_path = os.path.join(rootfs_dir, 'usr/bin')
        if not os.path.exists(usr_bin_path) or not os.path.isdir(usr_bin_path) or not os.listdir(usr_bin_path):
            missing_files.append('/usr/bin directory')
        
        return missing_files

    def _extract_layer_with_tar(self, layer_path, rootfs_dir, is_first_layer=False):
        """使用tar命令提取层（增强Android支持）"""
        # 检测文件类型并使用适当的tar选项
        with open(layer_path, 'rb') as f:
            magic = f.read(2)

        # 构建基础命令
        if magic == b'\x1f\x8b':  # gzip
            base_cmd = ['tar', '-xzf', layer_path, '-C', rootfs_dir]
        else:
            base_cmd = ['tar', '-xf', layer_path, '-C', rootfs_dir]

        # 根据是否为第一层和环境选择不同的选项
        if self._is_android_environment():
            # Android环境使用增强的宽松选项
            tar_options = [
                '--no-same-owner',           # 忽略所有者信息
                '--no-same-permissions',     # 忽略权限信息
                '--warning=no-unknown-keyword',  # 忽略未知关键字警告
                '--exclude=.wh.*',           # 跳过whiteout文件
                '--exclude=.wh.wh.*',        # 跳过whiteout opaque标记
            ]
            
            if not is_first_layer:
                # 后续层允许覆盖
                tar_options.append('--overwrite')
        else:
            # 标准Linux环境选项
            tar_options = [
                '--no-same-owner',
                '--no-same-permissions'
            ]

        cmd = base_cmd + tar_options

        try:
            self._run_command(cmd)
            logger.debug("tar提取成功")
        except subprocess.CalledProcessError as e:
            logger.warning(f"tar命令失败，尝试宽松模式: {e}")
            # 调用fallback方法
            self._extract_with_fallback(base_cmd, rootfs_dir)

    def _extract_with_fallback(self, base_cmd, rootfs_dir):
        """使用最宽松的选项重试tar提取"""
        fallback_cmd = base_cmd + [
            '--no-same-owner',
            '--no-same-permissions',
            '--warning=no-unknown-keyword',
            '--exclude=.wh.*',
            '--exclude=.wh.wh.*',
            '--skip-old-files',          # 跳过已存在的文件
            '--ignore-failed-read',      # 忽略读取失败
        ]

        result = subprocess.run(fallback_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("使用宽松模式提取成功")
        elif result.returncode == 2:
            # tar退出码2表示有警告但部分成功
            logger.info("tar提取完成（有警告，但大部分文件已提取）")
            logger.debug(f"tar警告: {result.stderr[:200]}...")
        else:
            error_msg = f"tar提取失败，退出码: {result.returncode}"
            if self._is_android_environment():
                error_msg += "\n提示：在Android环境中，某些权限操作可能失败。尝试使用 --verbose 查看详细信息。"
            logger.error(error_msg)
            raise subprocess.CalledProcessError(result.returncode, fallback_cmd, result.stderr)


    
    def _create_tar_archive(self, rootfs_dir):
        """创建tar归档文件"""
        output_path = os.path.abspath(self.output_path)
        
        # 使用tar命令创建归档，保持权限和所有者信息
        cmd = [
            'tar', 
            '-czf', output_path,
            '-C', rootfs_dir,
            '.'
        ]
        
        self._run_command(cmd)
        logger.info(f"根文件系统tar包已创建: {output_path}")
        return output_path
    
    def _optimize_for_proot(self, rootfs_dir):
        """为proot优化根文件系统"""
        logger.info("为proot优化根文件系统...")

        # 创建必要的目录
        essential_dirs = [
            'proc', 'sys', 'dev', 'tmp', 'run',
            'var/tmp', 'var/log', 'var/run'
        ]

        for dir_path in essential_dirs:
            full_path = os.path.join(rootfs_dir, dir_path)
            try:
                os.makedirs(full_path, exist_ok=True)
                logger.debug(f"确保目录存在: {dir_path}")
            except OSError as e:
                # 如果目录已存在但是文件，尝试删除后重建
                if os.path.exists(full_path) and not os.path.isdir(full_path):
                    try:
                        os.remove(full_path)
                        os.makedirs(full_path, exist_ok=True)
                        logger.debug(f"替换文件为目录: {dir_path}")
                    except OSError as e2:
                        logger.warning(f"无法创建目录 {dir_path}: {e2}")
                else:
                    logger.debug(f"目录已存在: {dir_path}")
        
        # 创建基本的设备文件（如果不存在）
        dev_dir = os.path.join(rootfs_dir, 'dev')
        if os.path.exists(dev_dir):
            essential_devs = [
                ('null', 'c', 1, 3),
                ('zero', 'c', 1, 5),
                ('random', 'c', 1, 8),
                ('urandom', 'c', 1, 9)
            ]

            for dev_name, dev_type, major, minor in essential_devs:
                dev_path = os.path.join(dev_dir, dev_name)
                if not os.path.exists(dev_path):
                    try:
                        # 注意：在某些环境中可能没有权限创建设备文件
                        # 这里只是尝试，失败了也不影响主要功能
                        if dev_type == 'c' and hasattr(os, 'mknod'):
                            os.mknod(dev_path, 0o666 | os.stat.S_IFCHR,
                                    os.makedev(major, minor))
                            logger.debug(f"创建字符设备: {dev_name}")
                        else:
                            # 如果无法创建设备文件，创建普通文件作为占位符
                            with open(dev_path, 'w') as f:
                                f.write('')
                            logger.debug(f"创建设备文件占位符: {dev_name}")
                    except (OSError, AttributeError) as e:
                        logger.debug(f"无法创建设备文件 {dev_name}: {e} (这通常是正常的)")
    
    def create_rootfs_tar(self):
        """主要的处理流程"""
        try:
            # 检查依赖
            if not self._check_dependencies():
                return False
            
            # 创建临时目录
            self._create_temp_directory()
            
            # 使用Python下载镜像
            logger.info("步骤 1/4: 使用Python下载Docker镜像...")
            oci_dir = self._download_image_with_python()
            
            # 使用Python提取根文件系统
            logger.info("步骤 2/4: 使用Python提取根文件系统...")
            rootfs_dir = self._extract_rootfs_with_python(oci_dir)
            
                # 保存镜像配置
            logger.info("步骤 3/5: 保存镜像配置...")
            self._save_image_config(oci_dir, rootfs_dir)

            # 为proot优化
            logger.info("步骤 4/5: 为proot优化根文件系统...")
            self._optimize_for_proot(rootfs_dir)

            # 创建tar归档
            logger.info("步骤 5/5: 创建tar归档...")
            output_file = self._create_tar_archive(rootfs_dir)
            
            logger.info(f"✓ 成功创建根文件系统tar包: {output_file}")
            logger.info(f"文件大小: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
            
            # 提供使用说明
            self._print_usage_instructions(output_file)
            
            return True
            
        except Exception as e:
            logger.error(f"处理失败: {str(e)}")
            return False
        finally:
            # 清理临时目录
            self._cleanup_temp_directory()
    
    def _print_usage_instructions(self, tar_file):
        """打印使用说明"""
        logger.info("\n" + "="*50)
        logger.info("在Android Termux中使用proot的说明:")
        logger.info("="*50)
        logger.info("1. 将tar文件传输到Android设备")
        logger.info("2. 在Termux中安装proot:")
        logger.info("   pkg install proot")
        logger.info("3. 解压根文件系统:")
        logger.info(f"   mkdir rootfs && tar -xzf {os.path.basename(tar_file)} -C rootfs")
        logger.info("4. 使用proot进入容器:")
        logger.info("   proot -r rootfs -b /dev -b /proc -b /sys /bin/sh")
        logger.info("或者使用更完整的绑定:")
        logger.info("   proot -r rootfs -b /dev -b /proc -b /sys -b /sdcard -w / /bin/sh")
        logger.info("="*50)
        logger.info("注意: 此脚本仅需要curl和tar命令行工具，无需skopeo、umoci和requests库")
        logger.info("使用Python标准库实现镜像解包，适合在各种环境中运行")

def main():
    parser = argparse.ArgumentParser(
        description='使用curl和Python制作Docker镜像的根文件系统tar包'
    )
    parser.add_argument(
        'image_url',
        nargs='?',
        default='swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/jeessy/ddns-go:v6.9.1-linuxarm64',
        help='Docker镜像URL (默认: ddns-go镜像)'
    )
    parser.add_argument(
        '-o', '--output',
        help='输出tar文件路径 (默认: 基于镜像名称自动生成)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    parser.add_argument(
        '--username',
        help='Docker Registry用户名'
    )
    parser.add_argument(
        '--password',
        help='Docker Registry密码或token'
    )
    parser.add_argument(
        '--proxy',
        help='指定用于curl的网络代理 (例如: "http://user:pass@host:port" 或 "socks5://host:port")'
    )
    
    parser.add_argument(
        '--arch',
        help='指定目标架构 (例如: amd64, arm64)。默认为自动检测。'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"开始处理Docker镜像: {args.image_url}")
    
    # 将代理参数传递给处理器
    processor = DockerImageToRootFS(args.image_url, args.output, args.username, args.password, args.arch)
    # 在客户端中也需要设置代理
    if args.proxy:
        # 这是个简化处理，理想情况下应该在DockerRegistryClient中处理
        # 但为了快速解决问题，我们通过环境变量设置
        os.environ['https_proxy'] = args.proxy
        os.environ['http_proxy'] = args.proxy
        logger.info(f"已设置网络代理: {args.proxy}")
    success = processor.create_rootfs_tar()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
