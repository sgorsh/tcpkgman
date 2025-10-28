"""Tests for Tcpkgman class."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tcpkgman.tcpkgman import Tcpkgman
from tcpkgman.tcpkg import Tcpkg


class BaseTestCase(unittest.TestCase):
	"""Base test case with common helper methods."""

	def setUp(self):
		"""Set up test fixtures."""
		self.cli = Tcpkgman()

	def run_with_argv(self, argv):
		"""Helper to run CLI with given argv."""
		with patch.object(sys, "argv", ["tcpkgman"] + argv):
			return self.cli.run()


class TestCLICommands(BaseTestCase):
	"""Test CLI command execution."""

	def setUp(self):
		"""Set up test fixtures with mock Tcpkg static methods."""
		super().setUp()
		self.check_installed_patcher = patch.object(Tcpkg, 'check_tcpkg_installed')
		self.check_exists_patcher = patch.object(Tcpkg, 'check_remote_exists', return_value=True)
		self.run_with_remote_patcher = patch.object(Tcpkg, 'run_with_remote')

		self.mock_check_installed = self.check_installed_patcher.start()
		self.mock_check_exists = self.check_exists_patcher.start()
		self.mock_run_with_remote = self.run_with_remote_patcher.start()

	def tearDown(self):
		"""Clean up patches."""
		self.check_installed_patcher.stop()
		self.check_exists_patcher.stop()
		self.run_with_remote_patcher.stop()

	def assert_command_passes_through(self, argv, expected_args):
		"""Helper to test that a command passes args to tcpkg correctly."""
		self.run_with_argv(argv)
		self.mock_run_with_remote.assert_called_once_with("myplc", expected_args)

	def test_install_command(self):
		"""Test install command passes args correctly to tcpkg."""
		self.run_with_argv(["--remote", "myplc", "install", "pkg1"])
		self.mock_run_with_remote.assert_called_once_with("myplc", ["install", "pkg1"])

	def test_list_command(self):
		"""Test list command."""
		self.assert_command_passes_through(
			["--remote", "myplc", "list", "pkg1"],
			["list", "pkg1"]
		)

	def test_upgrade_command(self):
		"""Test upgrade command."""
		self.assert_command_passes_through(
			["--remote", "myplc", "upgrade", "pkg1"],
			["upgrade", "pkg1"]
		)

	def test_uninstall_command(self):
		"""Test uninstall command."""
		self.assert_command_passes_through(
			["--remote", "myplc", "uninstall", "pkg1"],
			["uninstall", "pkg1"]
		)

	def test_show_command(self):
		"""Test show command."""
		self.assert_command_passes_through(
			["--remote", "myplc", "show", "pkg1"],
			["show", "pkg1"]
		)

	def test_command_with_multiple_packages(self):
		"""Test command with multiple packages."""
		self.assert_command_passes_through(
			["--remote", "myplc", "install", "pkg1", "pkg2", "pkg3"],
			["install", "pkg1", "pkg2", "pkg3"]
		)

	def test_command_with_flags(self):
		"""Test command with tcpkg flags passed through."""
		self.assert_command_passes_through(
			["--remote", "myplc", "install", "pkg1", "--version", "1.0.0"],
			["install", "pkg1", "--version", "1.0.0"]
		)


class TestRemoteManagement(BaseTestCase):
	"""Test remote add/remove functionality."""

	def setUp(self):
		"""Set up test fixtures with mock Tcpkg static methods."""
		super().setUp()
		self.check_installed_patcher = patch.object(Tcpkg, 'check_tcpkg_installed')
		self.check_exists_patcher = patch.object(Tcpkg, 'check_remote_exists')
		self.remove_remote_patcher = patch.object(Tcpkg, 'remove_remote')
		self.list_remotes_patcher = patch.object(Tcpkg, 'list_remotes')

		self.mock_check_installed = self.check_installed_patcher.start()
		self.mock_check_exists = self.check_exists_patcher.start()
		self.mock_remove_remote = self.remove_remote_patcher.start()
		self.mock_list_remotes = self.list_remotes_patcher.start()

		# Mock admin check and interactive methods
		self.mock_admin_patcher = patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=True)
		self.mock_admin_patcher.start()
		self.mock_add_remote_patcher = patch.object(Tcpkgman, "_add_remote_interactive")
		self.mock_add_remote = self.mock_add_remote_patcher.start()

	def tearDown(self):
		"""Clean up patches."""
		self.check_installed_patcher.stop()
		self.check_exists_patcher.stop()
		self.remove_remote_patcher.stop()
		self.list_remotes_patcher.stop()
		self.mock_admin_patcher.stop()
		self.mock_add_remote_patcher.stop()

	def test_remote_add_new(self):
		"""Test adding a new remote."""
		self.mock_check_exists.return_value = False
		self.run_with_argv(["--remote-add", "myplc"])

		self.mock_check_installed.assert_called_once()
		self.mock_check_exists.assert_called_once_with("myplc")
		self.mock_add_remote.assert_called_once()

	@patch("builtins.print")
	def test_remote_add_existing(self, mock_print):
		"""Test adding an existing remote."""
		self.mock_check_exists.return_value = True
		self.run_with_argv(["--remote-add", "myplc"])

		mock_print.assert_called_with("Remote 'myplc' already exists")
		self.mock_add_remote.assert_not_called()

	def test_remote_remove(self):
		"""Test removing a remote."""
		self.run_with_argv(["--remote-remove", "myplc"])

		self.mock_check_installed.assert_called_once()
		self.mock_remove_remote.assert_called_once_with("myplc")

	def test_remote_list(self):
		"""Test listing all remotes."""
		self.run_with_argv(["--remote-list"])

		self.mock_check_installed.assert_called_once()
		self.mock_list_remotes.assert_called_once()


class TestErrorCases(BaseTestCase):
	"""Test error handling."""

	def setUp(self):
		"""Set up test fixtures."""
		super().setUp()

	def tearDown(self):
		"""Clean up patches."""
		pass

	def assert_exits_with_code(self, argv, expected_code):
		"""Helper to assert that CLI exits with specific code."""
		with self.assertRaises(SystemExit) as cm:
			self.run_with_argv(argv)
		self.assertEqual(cm.exception.code, expected_code)

	def test_missing_remote_flag(self):
		"""Test error when --remote is missing."""
		self.assert_exits_with_code(["install", "pkg1"], 1)

	def test_missing_command(self):
		"""Test that help is printed when no command is specified."""
		self.assert_exits_with_code(["--remote", "myplc"], 0)

	def test_keyboard_interrupt(self):
		"""Test handling of keyboard interrupt."""
		with patch.object(Tcpkg, 'check_tcpkg_installed'):
			with patch.object(Tcpkg, 'check_remote_exists', side_effect=KeyboardInterrupt()):
				self.assert_exits_with_code(["--remote", "myplc", "install", "pkg"], 130)


class TestRemoteCreation(BaseTestCase):
	"""Test automatic remote creation."""

	def setUp(self):
		"""Set up test fixtures with mock Tcpkg static methods."""
		super().setUp()
		self.check_installed_patcher = patch.object(Tcpkg, 'check_tcpkg_installed')
		self.check_exists_patcher = patch.object(Tcpkg, 'check_remote_exists', return_value=False)
		self.run_with_remote_patcher = patch.object(Tcpkg, 'run_with_remote')

		self.mock_check_installed = self.check_installed_patcher.start()
		self.mock_check_exists = self.check_exists_patcher.start()
		self.mock_run_with_remote = self.run_with_remote_patcher.start()

		# Mock interactive method
		self.mock_add_remote_patcher = patch.object(Tcpkgman, "_add_remote_interactive")
		self.mock_add_remote = self.mock_add_remote_patcher.start()

	def tearDown(self):
		"""Clean up patches."""
		self.check_installed_patcher.stop()
		self.check_exists_patcher.stop()
		self.run_with_remote_patcher.stop()
		self.mock_add_remote_patcher.stop()

	def test_auto_add_remote_when_missing(self):
		"""Test that remote is automatically added if it doesn't exist."""
		self.run_with_argv(["--remote", "myplc", "install", "pkg"])

		# Should add the remote before running the command
		self.mock_add_remote.assert_called_once()
		self.mock_run_with_remote.assert_called_once_with("myplc", ["install", "pkg"])


class TestEnvironmentVariable(BaseTestCase):
	"""Test TCPKG_REMOTE environment variable."""

	def setUp(self):
		"""Set up test fixtures with mock Tcpkg static methods."""
		super().setUp()
		self.check_installed_patcher = patch.object(Tcpkg, 'check_tcpkg_installed')
		self.check_exists_patcher = patch.object(Tcpkg, 'check_remote_exists', return_value=True)
		self.run_with_remote_patcher = patch.object(Tcpkg, 'run_with_remote')

		self.mock_check_installed = self.check_installed_patcher.start()
		self.mock_check_exists = self.check_exists_patcher.start()
		self.mock_run_with_remote = self.run_with_remote_patcher.start()

	def tearDown(self):
		"""Clean up patches."""
		self.check_installed_patcher.stop()
		self.check_exists_patcher.stop()
		self.run_with_remote_patcher.stop()

	@patch.dict('os.environ', {'TCPKG_REMOTE': 'envplc'})
	def test_env_var_used_when_no_flag(self):
		"""Test that TCPKG_REMOTE is used when --remote is not provided."""
		self.run_with_argv(["install", "pkg"])

		self.mock_run_with_remote.assert_called_once_with("envplc", ["install", "pkg"])

	@patch.dict('os.environ', {'TCPKG_REMOTE': 'envplc'})
	def test_flag_overrides_env_var(self):
		"""Test that --remote flag takes precedence over TCPKG_REMOTE."""
		self.run_with_argv(["--remote", "flagplc", "install", "pkg"])

		self.mock_run_with_remote.assert_called_once_with("flagplc", ["install", "pkg"])

	@patch.dict('os.environ', {}, clear=True)
	def test_error_when_no_remote_specified(self):
		"""Test error when neither --remote nor TCPKG_REMOTE is set."""
		with self.assertRaises(SystemExit) as cm:
			self.run_with_argv(["install", "pkg"])
		self.assertEqual(cm.exception.code, 1)


class TestSSHKeyManagement(unittest.TestCase):
	"""Test SSH key detection and generation functionality."""

	@patch("pathlib.Path.home")
	def test_get_ssh_dir(self, mock_home):
		"""Test getting SSH directory path."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")
		ssh_dir = ADSSSHKeyManager.get_ssh_dir()
		self.assertEqual(ssh_dir, Path("C:/Users/TestUser/.ssh"))

	@patch("pathlib.Path.home")
	def test_find_default_ssh_key_ed25519(self, mock_home):
		"""Test finding ed25519 key (preferred)."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")

		# Mock exists to return True for ed25519
		def mock_exists(self):
			return str(self).endswith("id_ed25519")

		with patch.object(Path, "exists", mock_exists):
			key = ADSSSHKeyManager.find_default_key()
			self.assertTrue(key.endswith("id_ed25519"))

	@patch("pathlib.Path.home")
	def test_find_default_ssh_key_rsa(self, mock_home):
		"""Test finding rsa key when ed25519 doesn't exist."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")

		# Mock exists to return True only for rsa
		def mock_exists(self):
			return str(self).endswith("id_rsa")

		with patch.object(Path, "exists", mock_exists):
			key = ADSSSHKeyManager.find_default_key()
			self.assertTrue(key.endswith("id_rsa"))

	@patch("pathlib.Path.home")
	def test_find_default_ssh_key_none(self, mock_home):
		"""Test when no default SSH keys exist."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")

		with patch("pathlib.Path.exists", return_value=False):
			key = ADSSSHKeyManager.find_default_key()
			self.assertIsNone(key)

	@patch("pathlib.Path.home")
	@patch("subprocess.run")
	@patch("builtins.print")
	def test_generate_ssh_key_success(self, mock_print, mock_run, mock_home):
		"""Test successful SSH key generation."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")
		mock_run.return_value = Mock(returncode=0)

		with patch("pathlib.Path.mkdir"):
			key_path = ADSSSHKeyManager.generate_key("ed25519")
			self.assertTrue(key_path.endswith("id_ed25519"))

			# Verify ssh-keygen was called with correct args
			args = mock_run.call_args[0][0]
			self.assertEqual(args[0], "ssh-keygen")
			self.assertEqual(args[1], "-t")
			self.assertEqual(args[2], "ed25519")

	@patch("pathlib.Path.home")
	@patch("subprocess.run")
	def test_generate_ssh_key_failure(self, mock_run, mock_home):
		"""Test SSH key generation failure handling."""
		from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
		mock_home.return_value = Path("C:/Users/TestUser")
		mock_run.return_value = Mock(returncode=1, stderr="Error message")

		with patch("pathlib.Path.mkdir"):
			with self.assertRaises(RuntimeError) as cm:
				ADSSSHKeyManager.generate_key("ed25519")
			self.assertIn("Failed to generate SSH key", str(cm.exception))


class TestSSHConnectionCheck(BaseTestCase):
	"""Test SSH connection checking in remote add."""

	@patch("pathlib.Path.exists")
	def test_check_ssh_setup_key_missing(self, mock_exists):
		"""Test SSH check when key file doesn't exist."""
		mock_exists.return_value = False

		result = self.cli._check_ssh_setup("192.168.1.100", "Administrator", "22", "C:/Users/test/.ssh/id_ed25519")

		self.assertFalse(result)

	@patch("tcpkgman.ads_ssh_key_manager.ADSSSHKeyManager.test_ssh_connection")
	@patch("pathlib.Path.exists")
	def test_check_ssh_setup_connection_success(self, mock_exists, mock_test_ssh):
		"""Test SSH check when connection succeeds."""
		mock_exists.return_value = True
		mock_test_ssh.return_value = True

		result = self.cli._check_ssh_setup("192.168.1.100", "Administrator", "22", "C:/Users/test/.ssh/id_ed25519")

		self.assertTrue(result)
		mock_test_ssh.assert_called_once_with("192.168.1.100", "Administrator", "22", "C:/Users/test/.ssh/id_ed25519")

	@patch("tcpkgman.ads_ssh_key_manager.ADSSSHKeyManager.test_ssh_connection")
	@patch("pathlib.Path.exists")
	def test_check_ssh_setup_connection_failed(self, mock_exists, mock_test_ssh):
		"""Test SSH check when connection fails."""
		mock_exists.return_value = True
		mock_test_ssh.return_value = False

		result = self.cli._check_ssh_setup("192.168.1.100", "Administrator", "22", "C:/Users/test/.ssh/id_ed25519")

		self.assertFalse(result)

	@patch("builtins.input")
	def test_offer_ssh_init_via_ads_accepted(self, mock_input):
		"""Test offering SSH init via ADS when user accepts."""
		mock_input.return_value = "y"

		result = self.cli._offer_ssh_init_via_ads()

		self.assertTrue(result)

	@patch("builtins.input")
	def test_offer_ssh_init_via_ads_declined(self, mock_input):
		"""Test offering SSH init via ADS when user declines."""
		mock_input.return_value = "n"

		result = self.cli._offer_ssh_init_via_ads()

		self.assertFalse(result)


if __name__ == "__main__":
	unittest.main()
