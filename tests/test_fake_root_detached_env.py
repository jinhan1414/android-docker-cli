import os
import tempfile
import shutil
import unittest
from unittest import mock

from android_docker.docker_cli import DockerCLI


class TestDetachedFakeRootEnv(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_detached_fakeroot_")
        self.cli = DockerCLI(cache_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _base_container(self, container_id):
        containers = {
            container_id: {
                "id": container_id,
                "status": "created",
                "pid": None,
                "run_args": {},
            }
        }
        self.cli._save_containers(containers)

    def test_run_detached_sets_env_when_enabled(self):
        container_id = "c1"
        container_dir = self.cli._get_container_dir(container_id)
        os.makedirs(container_dir, exist_ok=True)

        pid_file = self.cli._get_pid_file(container_dir)
        with open(pid_file, "w") as handle:
            handle.write("1234")

        self._base_container(container_id)

        class Args:
            detach = True
            force_download = False
            workdir = None
            interactive = False
            env = []
            bind = []
            command = []
            username = None
            password = None
            fake_root = True

        with mock.patch("subprocess.Popen") as popen_mock, mock.patch("time.sleep", lambda *_: None):
            popen_mock.return_value = object()
            ok = self.cli._run_detached("alpine:latest", Args(), container_id, container_dir)
            self.assertTrue(ok)

            _, kwargs = popen_mock.call_args
            child_env = kwargs.get("env", {})
            self.assertEqual(child_env.get(self.cli.runner.FAKE_ROOT_ENV), "1")

    def test_run_detached_sets_env_when_disabled(self):
        container_id = "c2"
        container_dir = self.cli._get_container_dir(container_id)
        os.makedirs(container_dir, exist_ok=True)

        pid_file = self.cli._get_pid_file(container_dir)
        with open(pid_file, "w") as handle:
            handle.write("1234")

        self._base_container(container_id)

        class Args:
            detach = True
            force_download = False
            workdir = None
            interactive = False
            env = []
            bind = []
            command = []
            username = None
            password = None
            fake_root = False

        with mock.patch("subprocess.Popen") as popen_mock, mock.patch("time.sleep", lambda *_: None):
            popen_mock.return_value = object()
            ok = self.cli._run_detached("alpine:latest", Args(), container_id, container_dir)
            self.assertTrue(ok)

            _, kwargs = popen_mock.call_args
            child_env = kwargs.get("env", {})
            self.assertEqual(child_env.get(self.cli.runner.FAKE_ROOT_ENV), "0")


if __name__ == "__main__":
    unittest.main()

