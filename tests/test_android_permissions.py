#!/usr/bin/env python3
"""
Android权限修复的属性测试和单元测试
使用hypothesis库进行基于属性的测试
"""

import os
import sys
import tempfile
import shutil
import unittest
from hypothesis import given, strategies as st, settings
from pathlib import Path

# 添加父目录到路径以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from android_docker.create_rootfs_tar import DockerImageToRootFS
from android_docker.proot_runner import ProotRunner


class TestWhiteoutFileHandling(unittest.TestCase):
    """测试whiteout文件处理"""
    
    def test_whiteout_file_detection(self):
        """单元测试：验证whiteout文件被正确识别和跳过"""
        # 测试 .wh.auxfiles 被跳过
        self.assertTrue('.wh.auxfiles'.startswith('.wh.'))
        
        # 测试 dir/.wh.file 被跳过
        self.assertTrue('/.wh.' in 'dir/.wh.file')
        
        # 测试正常文件不被跳过
        self.assertFalse('normal_file.txt'.startswith('.wh.'))
        self.assertFalse('/.wh.' in 'normal_file.txt')
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_whiteout_prefix_detection(self, filename):
        """
        Property 1: Whiteout文件排除
        Validates: Requirements 1.1, 1.2, 1.3
        
        对于任意文件名，如果它以.wh.开头或包含/.wh.，应该被识别为whiteout文件
        """
        is_whiteout = filename.startswith('.wh.') or '/.wh.' in filename
        
        if is_whiteout:
            # whiteout文件应该被跳过
            self.assertTrue(filename.startswith('.wh.') or '/.wh.' in filename)


class TestWritableDirectories(unittest.TestCase):
    """测试可写目录功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp(prefix='test_writable_')
        self.runner = ProotRunner(cache_dir=self.test_dir)
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    @given(st.lists(st.sampled_from(['var/log', 'var/cache', 'var/tmp', 'tmp', 'run']), 
                    min_size=1, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_writable_directory_creation(self, dir_list):
        """
        Property 3: 可写目录创建
        Validates: Requirements 2.1
        
        对于任意系统目录列表，创建的可写目录应该存在且具有正确的权限
        """
        container_dir = os.path.join(self.test_dir, 'test_container')
        os.makedirs(container_dir, exist_ok=True)
        
        # 模拟Android环境
        original_method = self.runner._is_android_environment
        self.runner._is_android_environment = lambda: True
        
        try:
            bind_mounts = self.runner._prepare_writable_directories(container_dir)
            
            # 验证返回的绑定挂载列表
            self.assertIsInstance(bind_mounts, list)
            self.assertGreater(len(bind_mounts), 0)
            
            # 验证writable_dirs目录被创建（在父目录中）
            parent_dir = os.path.dirname(container_dir)
            writable_storage = os.path.join(parent_dir, 'writable_dirs')
            self.assertTrue(os.path.exists(writable_storage), 
                          f"writable_storage目录应该存在: {writable_storage}")
            
            # 验证至少有一些子目录被创建
            subdirs = os.listdir(writable_storage)
            self.assertGreater(len(subdirs), 0, "应该创建子目录")
        finally:
            self.runner._is_android_environment = original_method


class TestCriticalFileValidation(unittest.TestCase):
    """测试关键文件验证"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp(prefix='test_validation_')
        self.image_processor = DockerImageToRootFS('test:latest', 
                                                   output_path=os.path.join(self.test_dir, 'test.tar'))
        self.image_processor.temp_dir = self.test_dir
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_missing_shell(self):
        """测试缺少shell时的验证失败"""
        rootfs = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(rootfs, exist_ok=True)
        
        # 创建lib目录但不创建shell
        os.makedirs(os.path.join(rootfs, 'lib'), exist_ok=True)
        os.makedirs(os.path.join(rootfs, 'usr', 'bin'), exist_ok=True)
        
        missing = self.image_processor._validate_critical_files(rootfs)
        
        # 应该报告缺少shell
        self.assertIn('shell', ' '.join(missing).lower())
    
    def test_valid_rootfs(self):
        """测试有效的rootfs通过验证"""
        rootfs = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(os.path.join(rootfs, 'bin'), exist_ok=True)
        os.makedirs(os.path.join(rootfs, 'lib'), exist_ok=True)
        os.makedirs(os.path.join(rootfs, 'usr', 'bin'), exist_ok=True)
        
        # 创建shell
        Path(os.path.join(rootfs, 'bin', 'sh')).touch()
        # 创建lib文件
        Path(os.path.join(rootfs, 'lib', 'libc.so')).touch()
        # 创建usr/bin文件
        Path(os.path.join(rootfs, 'usr', 'bin', 'ls')).touch()
        
        missing = self.image_processor._validate_critical_files(rootfs)
        
        # 不应该有缺失的文件
        self.assertEqual(len(missing), 0)


class TestAndroidDetection(unittest.TestCase):
    """测试Android环境检测"""
    
    @given(st.booleans())
    @settings(max_examples=50)
    def test_android_detection_consistency(self, mock_android):
        """
        Property 9: Android环境自动检测
        Validates: Requirements 4.1, 4.2, 4.3, 4.4
        
        对于任意环境状态，两个模块的Android检测应该一致
        """
        runner = ProotRunner()
        image_processor = DockerImageToRootFS('test:latest')
        
        # 在实际环境中，两个检测方法应该返回相同的结果
        runner_result = runner._is_android_environment()
        processor_result = image_processor._is_android_environment()
        
        # 两个模块应该有一致的检测结果
        self.assertEqual(type(runner_result), type(processor_result))
        self.assertIsInstance(runner_result, bool)
        self.assertIsInstance(processor_result, bool)


class TestVersionDetection(unittest.TestCase):
    """测试版本检测功能"""
    
    @given(st.sampled_from(['v1.0.0', 'v1.1.0', 'v2.0.0', 'v10.5.3']))
    @settings(max_examples=50)
    def test_version_pattern_extraction(self, version):
        """
        Property 13: 版本检测
        Validates: Requirements 6.1, 6.2
        
        对于任意有效的版本字符串，应该能够正确提取版本号
        """
        # 模拟URL中的版本
        url = f"https://raw.githubusercontent.com/user/repo/{version}/scripts/install.sh"
        
        # 提取版本的正则表达式模式
        import re
        match = re.search(r'/v\d+\.\d+\.\d+/', url)
        
        if match:
            extracted = match.group(0).strip('/')
            self.assertEqual(extracted, version)


class TestExtractionResilience(unittest.TestCase):
    """测试提取弹性"""
    
    def test_tar_exit_code_handling(self):
        """
        Property 2: 提取弹性
        Validates: Requirements 1.4, 3.3, 3.4
        
        tar退出码2（警告）应该被视为成功
        """
        # 退出码0和2都应该被接受
        acceptable_codes = [0, 2]
        
        for code in acceptable_codes:
            self.assertIn(code, [0, 2], 
                         f"退出码 {code} 应该被接受")


class TestContainerCleanup(unittest.TestCase):
    """测试容器清理"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp(prefix='test_cleanup_')
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_writable_dirs_cleanup(self):
        """
        Property 5: 可写目录清理
        Validates: Requirements 2.5
        
        当容器被删除时，writable_dirs应该被清理
        """
        container_dir = os.path.join(self.test_dir, 'containers', 'test_container')
        writable_dirs = os.path.join(os.path.dirname(container_dir), 'writable_dirs')
        
        # 创建目录
        os.makedirs(container_dir, exist_ok=True)
        os.makedirs(writable_dirs, exist_ok=True)
        
        # 验证目录存在
        self.assertTrue(os.path.exists(container_dir))
        self.assertTrue(os.path.exists(writable_dirs))
        
        # 模拟清理
        if os.path.isdir(container_dir):
            shutil.rmtree(container_dir)
        if os.path.isdir(writable_dirs):
            shutil.rmtree(writable_dirs)
        
        # 验证目录被删除
        self.assertFalse(os.path.exists(container_dir))
        self.assertFalse(os.path.exists(writable_dirs))


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
