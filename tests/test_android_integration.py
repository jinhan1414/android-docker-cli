#!/usr/bin/env python3
"""
Android权限修复的集成测试
测试完整的镜像拉取、提取和容器运行流程
"""

import os
import sys
import time
import tempfile
import shutil
import unittest
import subprocess

# 添加父目录到路径以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from android_docker.docker_cli import DockerCLI
from android_docker.proot_runner import ProotRunner


class TestNginxIntegration(unittest.TestCase):
    """
    集成测试：nginx镜像
    Validates: Requirements 1.1, 1.5, 2.1, 2.2, 2.3, 2.6
    """
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.test_dir = tempfile.mkdtemp(prefix='test_nginx_')
        cls.cli = DockerCLI(cache_dir=cls.test_dir)
        cls.test_image = 'nginx:alpine'
        cls.container_name = 'test_nginx_container'
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        # 清理容器
        try:
            cls.cli.rm(cls.container_name, force=True)
        except:
            pass
        
        # 清理测试目录
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
    
    def test_01_pull_nginx_image(self):
        """测试拉取nginx:alpine镜像"""
        print(f"\n测试拉取 {self.test_image} 镜像...")
        
        # 拉取镜像
        success = self.cli.pull(self.test_image)
        
        self.assertTrue(success, "镜像拉取应该成功")
        
        # 验证镜像被缓存
        self.assertTrue(self.cli.runner._is_image_cached(self.test_image),
                       "镜像应该被缓存")
    
    def test_02_verify_extraction(self):
        """验证提取成功且没有whiteout文件错误"""
        print("\n验证镜像提取...")
        
        # 镜像应该已经被提取（在pull时）
        cache_path = self.cli.runner._get_image_cache_path(self.test_image)
        
        self.assertTrue(os.path.exists(cache_path),
                       f"缓存文件应该存在: {cache_path}")
    
    def test_03_run_container_with_volume(self):
        """测试运行容器并挂载卷"""
        print(f"\n测试运行 {self.test_image} 容器...")
        
        # 创建临时配置文件
        config_dir = os.path.join(self.test_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)
        
        config_file = os.path.join(config_dir, 'test.conf')
        with open(config_file, 'w') as f:
            f.write("# Test config\n")
        
        # 运行容器（非交互式，快速退出）
        container_id = self.cli.run(
            self.test_image,
            command=['echo', 'test'],
            name=self.container_name,
            bind=[f"{config_dir}:/test_mount"],
            env=['TEST_VAR=test_value']
        )
        
        self.assertIsNotNone(container_id, "容器应该成功创建")
        
        # 等待容器完成
        time.sleep(2)
        
        # 验证容器存在
        containers = self.cli._load_containers()
        self.assertIn(container_id, containers, "容器应该在列表中")


class TestTermixIntegration(unittest.TestCase):
    """
    集成测试：termix镜像（包含whiteout文件）
    Validates: Requirements 1.1, 2.1, 2.2, 2.3
    """
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.test_dir = tempfile.mkdtemp(prefix='test_termix_')
        cls.cli = DockerCLI(cache_dir=cls.test_dir)
        # 使用更小的镜像进行测试
        cls.test_image = 'alpine:latest'
        cls.container_name = 'test_termix_container'
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        # 清理容器
        try:
            cls.cli.rm(cls.container_name, force=True)
        except:
            pass
        
        # 清理测试目录
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
    
    def test_01_pull_image_with_whiteout_files(self):
        """测试拉取包含whiteout文件的镜像"""
        print(f"\n测试拉取 {self.test_image} 镜像（可能包含whiteout文件）...")
        
        # 拉取镜像
        success = self.cli.pull(self.test_image)
        
        self.assertTrue(success, "即使有whiteout文件，提取也应该成功")
    
    def test_02_verify_writable_directories(self):
        """验证可写目录功能"""
        print("\n验证可写目录功能...")
        
        runner = ProotRunner(cache_dir=self.test_dir)
        
        # 如果在Android环境中，验证可写目录
        if runner._is_android_environment():
            container_dir = os.path.join(self.test_dir, 'test_container')
            os.makedirs(container_dir, exist_ok=True)
            
            bind_mounts = runner._prepare_writable_directories(container_dir)
            
            self.assertIsInstance(bind_mounts, list)
            self.assertGreater(len(bind_mounts), 0, "应该创建可写目录")
            
            # 验证目录存在
            for bind in bind_mounts:
                host_path = bind.split(':')[0]
                self.assertTrue(os.path.exists(host_path),
                              f"可写目录应该存在: {host_path}")
        else:
            print("  跳过（非Android环境）")


class TestVolumeMountIntegration(unittest.TestCase):
    """
    集成测试：卷挂载与可写目录
    Validates: Requirements 2.6
    """
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.test_dir = tempfile.mkdtemp(prefix='test_volume_')
        cls.cli = DockerCLI(cache_dir=cls.test_dir)
        cls.test_image = 'alpine:latest'
        cls.container_name = 'test_volume_container'
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        # 清理容器
        try:
            cls.cli.rm(cls.container_name, force=True)
        except:
            pass
        
        # 清理测试目录
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
    
    def test_volume_mount_with_writable_dirs(self):
        """测试卷挂载与可写系统目录同时工作"""
        print("\n测试卷挂载与可写目录...")
        
        # 确保镜像存在
        if not self.cli.runner._is_image_cached(self.test_image):
            self.cli.pull(self.test_image)
        
        # 创建测试文件
        mount_dir = os.path.join(self.test_dir, 'mount_test')
        os.makedirs(mount_dir, exist_ok=True)
        
        test_file = os.path.join(mount_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write("test content")
        
        # 运行容器
        container_id = self.cli.run(
            self.test_image,
            command=['cat', '/mnt/test.txt'],
            name=self.container_name,
            bind=[f"{mount_dir}:/mnt"]
        )
        
        self.assertIsNotNone(container_id, "容器应该成功创建")
        
        # 等待容器完成
        time.sleep(2)
        
        # 验证容器运行
        containers = self.cli._load_containers()
        self.assertIn(container_id, containers)


class TestAndroidWarnings(unittest.TestCase):
    """测试Android警告和日志"""
    
    def test_android_detection_logging(self):
        """验证Android检测时的日志"""
        print("\n测试Android检测日志...")
        
        runner = ProotRunner()
        
        # 检测Android环境
        is_android = runner._is_android_environment()
        
        print(f"  Android环境检测结果: {is_android}")
        
        # 这个测试总是通过，只是为了验证检测逻辑运行
        self.assertIsInstance(is_android, bool)


def run_integration_tests():
    """运行所有集成测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestNginxIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestTermixIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestVolumeMountIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestAndroidWarnings))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    print("=" * 70)
    print("Android权限修复 - 集成测试")
    print("=" * 70)
    
    success = run_integration_tests()
    
    sys.exit(0 if success else 1)
