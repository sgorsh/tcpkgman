"""Tests for ADS SSH key manager."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from tcpkgman.ads_ssh_key_manager import ADSSSHKeyManager
from tcpkgman.ads_dll import AmsAddr


class TestReadSSHDPid(unittest.TestCase):
	"""Test ADSSSHKeyManager._read_sshd_pid method."""

	@patch('tcpkgman.ads_interface.get_ads_dll')
	def setUp(self, mock_get_dll):
		"""Create test instance."""
		# Mock DLL loading
		mock_get_dll.return_value = MagicMock()
		self.manager = ADSSSHKeyManager("192.168.100.117.1.1", "Administrator")

	@patch.object(ADSSSHKeyManager, 'read_file')
	def test_read_sshd_pid_success(self, mock_read_file):
		"""Test reading valid PID file."""
		mock_read_file.return_value = "1234\n"
		pid = self.manager._read_sshd_pid()
		self.assertEqual(pid, 1234)
		mock_read_file.assert_called_once_with(ADSSSHKeyManager.PID_FILE_PATH)

	@patch.object(ADSSSHKeyManager, 'read_file')
	def test_read_sshd_pid_file_not_found(self, mock_read_file):
		"""Test reading non-existent PID file."""
		mock_read_file.side_effect = Exception("File not found")
		pid = self.manager._read_sshd_pid()
		self.assertIsNone(pid)

	@patch.object(ADSSSHKeyManager, 'read_file')
	def test_read_sshd_pid_invalid_content(self, mock_read_file):
		"""Test reading PID file with invalid content."""
		mock_read_file.return_value = "not a number"
		pid = self.manager._read_sshd_pid()
		self.assertIsNone(pid)


class TestRestartOpenSSHServer(unittest.TestCase):
	"""Test ADSSSHKeyManager.restart_openssh_server method."""

	@patch('tcpkgman.ads_interface.get_ads_dll')
	def setUp(self, mock_get_dll):
		"""Create test instance."""
		# Mock DLL loading
		mock_get_dll.return_value = MagicMock()
		self.manager = ADSSSHKeyManager("192.168.100.117.1.1", "Administrator")

	@patch('tcpkgman.ads_ssh_key_manager.time.sleep')
	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_success_first_poll(self, mock_read_pid, mock_sleep):
		"""Test successful restart with PID change on first poll."""
		# Mock DLL methods
		self.manager._dll.port_open = MagicMock(return_value=12345)
		self.manager._dll.port_close = MagicMock()
		self.manager._dll.write = MagicMock()

		# PID changes from 1234 to 5678 on first poll
		mock_read_pid.side_effect = [1234, 5678]

		exit_code = self.manager.restart_openssh_server(timeout_ms=5000)

		# Verify write was called
		self.assertTrue(self.manager._dll.write.called)

		# Verify PID was read twice (before and after first poll)
		self.assertEqual(mock_read_pid.call_count, 2)

		# Verify sleep was called once (polling succeeded on first attempt)
		mock_sleep.assert_called_once_with(1)

		# Verify exit code
		self.assertEqual(exit_code, 0)

	@patch('tcpkgman.ads_ssh_key_manager.time.sleep')
	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_success_after_retries(self, mock_read_pid, mock_sleep):
		"""Test successful restart with PID change after several polls."""
		# Mock DLL methods
		self.manager._dll.port_open = MagicMock(return_value=12345)
		self.manager._dll.port_close = MagicMock()
		self.manager._dll.write = MagicMock()

		# PID stays same for 3 polls, then changes on 4th
		mock_read_pid.side_effect = [1234, 1234, 1234, 1234, 5678]

		exit_code = self.manager.restart_openssh_server(timeout_ms=5000)

		# Verify PID was read 5 times (initial + 4 polls)
		self.assertEqual(mock_read_pid.call_count, 5)

		# Verify sleep was called 4 times
		self.assertEqual(mock_sleep.call_count, 4)

		# Verify success
		self.assertEqual(exit_code, 0)

	@patch('tcpkgman.ads_ssh_key_manager.time.sleep')
	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_failure_pid_unchanged(self, mock_read_pid, mock_sleep):
		"""Test restart failure when PID doesn't change (timeout expires)."""
		# Mock DLL methods
		self.manager._dll.port_open = MagicMock(return_value=12345)
		self.manager._dll.port_close = MagicMock()
		self.manager._dll.write = MagicMock()

		# PID stays the same (1234) throughout polling + final check
		mock_read_pid.return_value = 1234

		with self.assertRaises(RuntimeError) as context:
			self.manager.restart_openssh_server(timeout_ms=3000)

		error_msg = str(context.exception)
		self.assertIn("PID unchanged (1234)", error_msg)
		self.assertIn("after 3s timeout", error_msg)

		# Verify sleep was called 3 times (polling attempts)
		self.assertEqual(mock_sleep.call_count, 3)

	@patch('tcpkgman.ads_ssh_key_manager.time.sleep')
	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_failure_no_pid_after(self, mock_read_pid, mock_sleep):
		"""Test restart failure when PID file missing after restart (timeout expires)."""
		# Mock DLL methods
		self.manager._dll.port_open = MagicMock(return_value=12345)
		self.manager._dll.port_close = MagicMock()
		self.manager._dll.write = MagicMock()

		# PID exists before, missing throughout polling
		mock_read_pid.side_effect = [1234] + [None] * 10  # Initial + polling attempts

		with self.assertRaises(RuntimeError) as context:
			self.manager.restart_openssh_server(timeout_ms=3000)

		error_msg = str(context.exception)
		self.assertIn("PID file not found", error_msg)
		self.assertIn("after 3s timeout", error_msg)

		# Verify sleep was called 3 times
		self.assertEqual(mock_sleep.call_count, 3)

	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_no_pid_before(self, mock_read_pid):
		"""Test restart fails when PID file doesn't exist before restart."""
		# No PID before
		mock_read_pid.return_value = None

		with self.assertRaises(RuntimeError) as context:
			self.manager.restart_openssh_server(timeout_ms=5000)

		error_msg = str(context.exception)
		self.assertIn("PID file not found", error_msg)
		self.assertIn("service may not be running", error_msg)

	@patch('tcpkgman.ads_ssh_key_manager.time.sleep')
	@patch.object(ADSSSHKeyManager, '_read_sshd_pid')
	def test_restart_default_timeouts(self, mock_read_pid, mock_sleep):
		"""Test default timeout values."""
		# Mock DLL methods
		self.manager._dll.port_open = MagicMock(return_value=12345)
		self.manager._dll.port_close = MagicMock()
		self.manager._dll.write = MagicMock()

		# PID changes immediately
		mock_read_pid.side_effect = [1234, 5678]

		# Call without specifying timeouts
		self.manager.restart_openssh_server()

		# Verify write was called (default timeout used internally)
		self.assertTrue(self.manager._dll.write.called)


if __name__ == '__main__':
	unittest.main()
