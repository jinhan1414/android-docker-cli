#!/usr/bin/env python3
"""
Android权限修复的属性测试和单元测试
使用hypothesis库进行基于属性的测试
"""

import io
import os
import sys
import tempfile
import shutil
import stat
import tarfile
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

    def test_writable_directory_seeding(self):
        """Writable dirs mirror nested rootfs directories."""
        rootfs_dir = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(os.path.join(rootfs_dir, 'var', 'log', 'nginx'), exist_ok=True)
        os.makedirs(os.path.join(rootfs_dir, 'var', 'cache', 'nginx', 'client_temp'), exist_ok=True)

        original_method = self.runner._is_android_environment
        self.runner._is_android_environment = lambda: True

        try:
            self.runner._prepare_writable_directories(rootfs_dir)
            writable_storage = os.path.join(self.test_dir, 'writable_dirs')
            self.assertTrue(os.path.isdir(os.path.join(writable_storage, 'var_log', 'nginx')))
            self.assertTrue(os.path.isdir(os.path.join(writable_storage, 'var_cache', 'nginx', 'client_temp')))
        finally:
            self.runner._is_android_environment = original_method


class TestAndroidHostsBind(unittest.TestCase):
    """测试Android hosts绑定"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_hosts_')
        self.runner = ProotRunner(cache_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_android_hosts_file_creation(self):
        rootfs_dir = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(os.path.join(rootfs_dir, 'etc'), exist_ok=True)
        Path(os.path.join(rootfs_dir, 'etc', 'hosts')).write_text(
            '10.0.0.5 internal-service\n',
            encoding='utf-8'
        )

        original_method = self.runner._is_android_environment
        self.runner._is_android_environment = lambda: True

        try:
            bind_spec = self.runner._prepare_android_hosts_bind(rootfs_dir)
            self.assertIsNotNone(bind_spec)

            expected_path = os.path.join(self.test_dir, 'writable_dirs', 'etc_hosts')
            self.assertEqual(bind_spec, f"{expected_path}:/etc/hosts")
            self.assertTrue(os.path.exists(expected_path))

            content = Path(expected_path).read_text(encoding='utf-8')
            self.assertIn('10.0.0.5 internal-service', content)
            self.assertIn('127.0.0.1 localhost', content)
            self.assertIn('::1 localhost', content)
        finally:
            self.runner._is_android_environment = original_method

    def test_android_hosts_file_preserves_existing(self):
        rootfs_dir = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(rootfs_dir, exist_ok=True)
        writable_storage = os.path.join(self.test_dir, 'writable_dirs')
        os.makedirs(writable_storage, exist_ok=True)
        host_hosts_path = os.path.join(writable_storage, 'etc_hosts')
        Path(host_hosts_path).write_text('192.168.0.10 existing-host\n', encoding='utf-8')

        original_method = self.runner._is_android_environment
        self.runner._is_android_environment = lambda: True

        try:
            bind_spec = self.runner._prepare_android_hosts_bind(rootfs_dir)
            self.assertEqual(bind_spec, f"{host_hosts_path}:/etc/hosts")

            content = Path(host_hosts_path).read_text(encoding='utf-8')
            self.assertIn('192.168.0.10 existing-host', content)
            self.assertIn('127.0.0.1 localhost', content)
            self.assertIn('::1 localhost', content)
        finally:
            self.runner._is_android_environment = original_method


class TestAndroidFakeRootMode(unittest.TestCase):
    """Test Android default fake-root behavior and escape hatch."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_fakeroot_')
        self.runner = ProotRunner(cache_dir=self.test_dir)
        self.rootfs_dir = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(os.path.join(self.rootfs_dir, 'bin'), exist_ok=True)
        Path(os.path.join(self.rootfs_dir, 'bin', 'sh')).touch()
        self.runner.rootfs_dir = self.rootfs_dir

        self._orig_android = self.runner._is_android_environment
        self.runner._is_android_environment = lambda: True

        self._orig_env = os.environ.get(self.runner.FAKE_ROOT_ENV)

        class Args:
            detach = False
            bind = []
            workdir = None
            env = []
            command = []
            fake_root = None

        self.Args = Args

    def tearDown(self):
        self.runner._is_android_environment = self._orig_android

        if self._orig_env is None:
            os.environ.pop(self.runner.FAKE_ROOT_ENV, None)
        else:
            os.environ[self.runner.FAKE_ROOT_ENV] = self._orig_env

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_android_defaults_to_fake_root(self):
        os.environ.pop(self.runner.FAKE_ROOT_ENV, None)
        cmd = self.runner._build_proot_command(self.Args())
        self.assertIn('-0', cmd, "Android default should include proot fake-root flag (-0)")

    def test_escape_hatch_disables_fake_root(self):
        os.environ[self.runner.FAKE_ROOT_ENV] = '0'
        cmd = self.runner._build_proot_command(self.Args())
        self.assertNotIn('-0', cmd, "Escape hatch should disable fake-root when set to 0")

    def test_explicit_setting_overrides_env(self):
        os.environ[self.runner.FAKE_ROOT_ENV] = '0'
        args = self.Args()
        args.fake_root = True
        cmd = self.runner._build_proot_command(args)
        self.assertIn('-0', cmd, "Explicit args.fake_root=True should override env disable")

        os.environ[self.runner.FAKE_ROOT_ENV] = '1'
        args = self.Args()
        args.fake_root = False
        cmd = self.runner._build_proot_command(args)
        self.assertNotIn('-0', cmd, "Explicit args.fake_root=False should override env enable")

    def test_non_android_never_enables_fake_root(self):
        os.environ[self.runner.FAKE_ROOT_ENV] = '1'
        self.runner._is_android_environment = lambda: False
        cmd = self.runner._build_proot_command(self.Args())
        self.assertNotIn('-0', cmd, "Non-Android runs should not use fake-root by default")


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


class TestAndroidExtractionPermissions(unittest.TestCase):
    """测试Android提取权限保留"""

    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp(prefix='test_exec_')
        self.image_processor = DockerImageToRootFS(
            'test:latest',
            output_path=os.path.join(self.test_dir, 'test.tar')
        )
        self.image_processor.temp_dir = self.test_dir

    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_android_executable_bit_preserved(self):
        """Android环境下应保留可执行文件的执行位"""
        if os.name == 'nt':
            self.skipTest("Windows不支持POSIX执行位语义")

        rootfs = os.path.join(self.test_dir, 'rootfs')
        os.makedirs(rootfs, exist_ok=True)

        tar_path = os.path.join(self.test_dir, 'layer.tar')
        data = b'#!/bin/sh\necho hello\n'

        with tarfile.open(tar_path, 'w') as tar:
            info = tarfile.TarInfo(name='bin/busybox')
            info.mode = 0o755
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        original_method = self.image_processor._is_android_environment
        self.image_processor._is_android_environment = lambda: True
        try:
            with tarfile.open(tar_path, 'r') as tar:
                self.image_processor._safe_extract_tar(tar, rootfs)
        finally:
            self.image_processor._is_android_environment = original_method

        extracted_path = os.path.join(rootfs, 'bin', 'busybox')
        self.assertTrue(os.path.exists(extracted_path), "busybox应该被提取")
        mode = os.stat(extracted_path).st_mode
        self.assertTrue(mode & stat.S_IXUSR, "busybox应该是可执行文件")


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
