#!/usr/bin/env python3
"""
本地镜像加载器
用于从本地tar文件加载Docker镜像到缓存
"""

import os
import json
import tarfile
import hashlib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalImageLoader:
    """处理从本地tar归档文件加载Docker镜像"""
    
    def __init__(self, cache_dir):
        """
        初始化加载器
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def load_image(self, tar_path):
        """
        从tar文件加载镜像
        
        Args:
            tar_path: Docker镜像tar归档文件的路径
            
        Returns:
            tuple: (success: bool, image_name: str, error_message: str)
        """
        # 验证文件存在
        if not os.path.exists(tar_path):
            return False, None, f"文件不存在: {tar_path}"
        
        # 验证tar结构
        is_valid, error_msg = self._validate_tar_structure(tar_path)
        if not is_valid:
            return False, None, error_msg
        
        try:
            # 提取镜像信息
            with tarfile.open(tar_path, 'r') as tar:
                # 读取manifest.json
                manifest_member = tar.getmember('manifest.json')
                manifest_file = tar.extractfile(manifest_member)
                manifest_data = json.load(manifest_file)
                
                if not manifest_data or len(manifest_data) == 0:
                    return False, None, "manifest.json为空或格式无效"
                
                # 获取第一个镜像的信息
                image_info = manifest_data[0]
                repo_tags = image_info.get('RepoTags', [])
                
                if not repo_tags:
                    # 如果没有RepoTags，使用配置文件的hash作为名称
                    config_file = image_info.get('Config', '')
                    image_name = f"<none>:<none>_{config_file[:12]}"
                else:
                    image_name = repo_tags[0]
                
                # 提取到缓存
                cache_path = self._extract_to_cache(tar_path, image_name, tar)
                
                # 注册镜像
                self._register_image(image_name, cache_path, tar_path)
                
                logger.info(f"✓ 成功加载镜像: {image_name}")
                return True, image_name, None
                
        except tarfile.ReadError as e:
            return False, None, f"损坏的tar归档文件: {tar_path} - {str(e)}"
        except PermissionError as e:
            return False, None, f"权限被拒绝: 无法读取 {tar_path} - {str(e)}"
        except Exception as e:
            return False, None, f"加载镜像失败: {str(e)}"
    
    def _validate_tar_structure(self, tar_path):
        """
        验证tar包含所需的Docker镜像文件
        
        必需文件:
        - manifest.json
        - <layer>.tar 文件
        - <config>.json
        
        Args:
            tar_path: tar文件路径
            
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        try:
            with tarfile.open(tar_path, 'r') as tar:
                members = tar.getnames()
                
                # 检查manifest.json
                if 'manifest.json' not in members:
                    return False, "无效的Docker镜像tar: 缺少manifest.json"
                
                # 读取manifest以验证结构
                manifest_member = tar.getmember('manifest.json')
                manifest_file = tar.extractfile(manifest_member)
                manifest_data = json.load(manifest_file)
                
                if not manifest_data or len(manifest_data) == 0:
                    return False, "无效的Docker镜像tar: manifest.json为空"
                
                image_info = manifest_data[0]
                
                # 检查配置文件
                config_file = image_info.get('Config')
                if not config_file:
                    return False, "无效的Docker镜像tar: manifest中缺少Config字段"
                
                if config_file not in members:
                    return False, f"无效的Docker镜像tar: 缺少配置文件 {config_file}"
                
                # 检查层文件
                layers = image_info.get('Layers', [])
                if not layers:
                    return False, "无效的Docker镜像tar: manifest中缺少Layers字段"
                
                for layer in layers:
                    if layer not in members:
                        return False, f"无效的Docker镜像tar: 缺少层文件 {layer}"
                
                return True, None
                
        except tarfile.ReadError:
            return False, f"损坏的tar归档文件: {tar_path}"
        except json.JSONDecodeError:
            return False, "无效的Docker镜像tar: manifest.json不是有效的JSON"
        except Exception as e:
            return False, f"验证tar结构失败: {str(e)}"
    
    def _extract_to_cache(self, tar_path, image_name, tar):
        """
        提取tar到缓存目录，使用适当的命名
        
        Args:
            tar_path: 原始tar文件路径
            image_name: 镜像名称
            tar: 已打开的tarfile对象
            
        Returns:
            str: 缓存文件路径
        """
        # 生成缓存文件名
        # 使用镜像名称和tar文件内容的hash
        with open(tar_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
        
        # 清理镜像名称用于文件名
        safe_name = image_name.replace(':', '_').replace('/', '_').replace('<', '').replace('>', '')
        cache_filename = f"{safe_name}_{file_hash}.tar.gz"
        cache_path = os.path.join(self.cache_dir, cache_filename)
        
        # 如果已存在，先删除旧的
        if os.path.exists(cache_path):
            logger.info(f"镜像已存在，将更新: {cache_path}")
            os.remove(cache_path)
        
        # 复制tar文件到缓存（保持原格式或转换为.tar.gz）
        # 为了简单起见，直接复制原文件
        shutil.copy2(tar_path, cache_path)
        
        logger.info(f"镜像已提取到缓存: {cache_path}")
        return cache_path
    
    def _register_image(self, image_name, cache_path, original_tar):
        """
        在本地镜像列表中注册加载的镜像
        
        Args:
            image_name: 镜像名称
            cache_path: 缓存文件路径
            original_tar: 原始tar文件路径
        """
        # 创建或更新镜像信息文件
        info_path = cache_path + '.info'
        
        import time
        created_time = int(time.time())
        created_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time))
        
        info_data = {
            'image_url': image_name,
            'cache_path': cache_path,
            'created_time': created_time,
            'created_time_str': created_time_str,
            'source': 'local',
            'original_tar': original_tar
        }
        
        with open(info_path, 'w') as f:
            json.dump(info_data, f, indent=2)
        
        logger.info(f"镜像已注册: {image_name}")
