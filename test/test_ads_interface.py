"""Tests for ADS interface."""

import unittest
from unittest.mock import patch, MagicMock
import struct
from tcpkgman.ads_interface import ADSInterface, SYSTEMSERVICE_STARTPROCESS

class TestADSInterfaceRunCommand(unittest.TestCase):
	"""Test ADSInterface.run_command method."""

	@patch('tcpkgman.ads_interface.get_ads_dll')
	def setUp(self, mock_get_dll):
		"""Create test instance."""
		# Mock DLL loading
		mock_get_dll.return_value = MagicMock()
		self.ads = ADSInterface("192.168.100.117.1.1")

	def test_run_command_returns_immediately(self):
		"""Test run_command returns immediately (ADS call doesn't block)."""
		# Mock the DLL methods on self.ads._dll
		self.ads._dll.port_open = MagicMock(return_value=12345)
		self.ads._dll.port_close = MagicMock()
		self.ads._dll.write = MagicMock()

		# Execute command
		exit_code = self.ads.run_command(
			"cmd.exe /c exit 123",
			timeout_ms=5000,
			hide_window=True
		)

		# Verify write was called
		self.assertTrue(self.ads._dll.write.called,
			"Expected write() to be called")

		# Verify exit code is always 0 (not available via ADS)
		self.assertEqual(exit_code, 0,
			"Expected 0 (exit code not available via ADS)")

	def test_run_command_with_default_timeout(self):
		"""Test run_command uses default 5000ms timeout."""
		# Mock the DLL methods on self.ads._dll
		self.ads._dll.port_open = MagicMock(return_value=12345)
		self.ads._dll.port_close = MagicMock()
		self.ads._dll.write = MagicMock()

		# Execute command without specifying timeout (should use default)
		exit_code = self.ads.run_command("cmd.exe /c dir")

		# Verify write was called
		self.assertTrue(self.ads._dll.write.called,
			"Expected write() to be called with default timeout")

		# Verify exit code is 0
		self.assertEqual(exit_code, 0)

	def test_run_command_builds_correct_structure(self):
		"""Test run_command builds correct STARTPROCESS structure."""
		# Mock the DLL methods on self.ads._dll
		mock_port = 12345
		self.ads._dll.port_open = MagicMock(return_value=mock_port)
		self.ads._dll.port_close = MagicMock()
		self.ads._dll.write = MagicMock()

		# Execute command
		self.ads.run_command(
			"powershell.exe -Command Get-Service",
			working_dir="C:/temp",
			timeout_ms=10000,
			hide_window=True
		)

		# Get the write call arguments
		self.assertTrue(self.ads._dll.write.called, "Expected write() to be called")
		call_args = self.ads._dll.write.call_args[0]

		# Verify arguments (port, addr, index_group, index_offset, data)
		self.assertEqual(call_args[0], mock_port)
		self.assertEqual(call_args[2], SYSTEMSERVICE_STARTPROCESS)

		# Verify index_offset has timeout and SW_HIDE flag
		expected_offset = 10000 | 0x10000  # timeout | SW_HIDE
		self.assertEqual(call_args[3], expected_offset)

		# Verify data structure
		data = call_args[4]

		# Parse sizes
		process_len, dir_len, cmdline_len = struct.unpack('<III', data[:12])
		self.assertEqual(process_len, len("powershell.exe".encode('utf-8')))
		self.assertEqual(dir_len, len("C:/temp".encode('utf-8')))
		self.assertEqual(cmdline_len, len("-Command Get-Service".encode('utf-8')))

		# Parse strings
		offset = 12
		process = data[offset:offset+process_len].decode('utf-8')
		offset += process_len + 1  # +1 for null terminator
		dir_path = data[offset:offset+dir_len].decode('utf-8')
		offset += dir_len + 1
		cmdline = data[offset:offset+cmdline_len].decode('utf-8')

		self.assertEqual(process, "powershell.exe")
		self.assertEqual(dir_path, "C:/temp")
		self.assertEqual(cmdline, "-Command Get-Service")

	def test_run_command_without_hide_window(self):
		"""Test run_command without SW_HIDE flag."""
		# Mock the DLL methods on self.ads._dll
		self.ads._dll.port_open = MagicMock(return_value=12345)
		self.ads._dll.port_close = MagicMock()
		self.ads._dll.write = MagicMock()

		# Execute command with hide_window=False
		self.ads.run_command(
			"cmd.exe /c dir",
			timeout_ms=1000,
			hide_window=False
		)

		# Get the write call arguments
		self.assertTrue(self.ads._dll.write.called, "Expected write() to be called")
		call_args = self.ads._dll.write.call_args[0]

		# Verify index_offset does NOT have SW_HIDE flag
		expected_offset = 1000  # timeout only, no SW_HIDE
		self.assertEqual(call_args[3], expected_offset)


class TestGetTwincatTargets(unittest.TestCase):
	"""Test ADSInterface.get_twincat_targets method."""

	@patch.dict('os.environ', {}, clear=True)
	def test_no_twincat3dir_env_var(self):
		"""Test returns empty dict when TWINCAT3DIR not set."""
		targets = ADSInterface.get_twincat_targets()
		self.assertEqual(targets, {})

	@patch.dict('os.environ', {'TWINCAT3DIR': 'C:/NonExistent'})
	def test_twincat3dir_file_not_found(self):
		"""Test returns empty dict when StaticRoutes.xml doesn't exist."""
		targets = ADSInterface.get_twincat_targets()
		self.assertEqual(targets, {})

	@patch.dict('os.environ', {'TWINCAT3DIR': 'C:/TwinCAT/3.1'})
	@patch('pathlib.Path.exists')
	@patch('xml.etree.ElementTree.parse')
	def test_parses_valid_routes(self, mock_parse, mock_exists):
		"""Test parses valid StaticRoutes.xml correctly."""
		mock_exists.return_value = True

		# Create mock XML structure
		mock_tree = MagicMock()
		mock_root = MagicMock()
		mock_tree.getroot.return_value = mock_root

		# Create mock routes
		route1 = MagicMock()
		route1.findtext.side_effect = lambda x: {
			"Name": "PLC1",
			"NetId": "192.168.1.10.1.1",
			"Address": "192.168.1.10"
		}.get(x)

		route2 = MagicMock()
		route2.findtext.side_effect = lambda x: {
			"Name": "PLC2",
			"NetId": "192.168.1.20.1.1",
			"Address": "192.168.1.20"
		}.get(x)

		mock_root.findall.return_value = [route1, route2]
		mock_parse.return_value = mock_tree

		targets = ADSInterface.get_twincat_targets()

		self.assertEqual(len(targets), 2)
		self.assertEqual(targets["PLC1"], ("192.168.1.10.1.1", "192.168.1.10"))
		self.assertEqual(targets["PLC2"], ("192.168.1.20.1.1", "192.168.1.20"))

	@patch.dict('os.environ', {'TWINCAT3DIR': 'C:/TwinCAT/3.1'})
	@patch('pathlib.Path.exists')
	@patch('xml.etree.ElementTree.parse')
	def test_handles_malformed_xml(self, mock_parse, mock_exists):
		"""Test handles malformed XML gracefully."""
		mock_exists.return_value = True
		mock_parse.side_effect = Exception("Parse error")

		targets = ADSInterface.get_twincat_targets()
		self.assertEqual(targets, {})

	@patch.dict('os.environ', {'TWINCAT3DIR': 'C:/TwinCAT/3.1'})
	@patch('pathlib.Path.exists')
	@patch('xml.etree.ElementTree.parse')
	def test_skips_routes_missing_fields(self, mock_parse, mock_exists):
		"""Test skips routes with missing Name, NetId, or Address."""
		mock_exists.return_value = True

		# Create mock XML structure
		mock_tree = MagicMock()
		mock_root = MagicMock()
		mock_tree.getroot.return_value = mock_root

		# Route with missing NetId
		route1 = MagicMock()
		route1.findtext.side_effect = lambda x: {
			"Name": "PLC1",
			"NetId": None,
			"Address": "192.168.1.10"
		}.get(x)

		# Route with missing Name
		route2 = MagicMock()
		route2.findtext.side_effect = lambda x: {
			"Name": None,
			"NetId": "192.168.1.20.1.1",
			"Address": "192.168.1.20"
		}.get(x)

		# Route with missing Address
		route3 = MagicMock()
		route3.findtext.side_effect = lambda x: {
			"Name": "PLC3",
			"NetId": "192.168.1.30.1.1",
			"Address": None
		}.get(x)

		# Valid route
		route4 = MagicMock()
		route4.findtext.side_effect = lambda x: {
			"Name": "PLC4",
			"NetId": "192.168.1.40.1.1",
			"Address": "192.168.1.40"
		}.get(x)

		mock_root.findall.return_value = [route1, route2, route3, route4]
		mock_parse.return_value = mock_tree

		targets = ADSInterface.get_twincat_targets()

		self.assertEqual(len(targets), 1)
		self.assertEqual(targets["PLC4"], ("192.168.1.40.1.1", "192.168.1.40"))


class TestCheckConnection(unittest.TestCase):
	"""Test ADSInterface.check_connection method."""

	@patch('tcpkgman.ads_interface.get_ads_dll')
	def test_connection_success(self, mock_get_dll):
		"""Test successful connection check."""
		# Mock DLL
		mock_dll = MagicMock()
		mock_dll.port_open = MagicMock(return_value=12345)
		mock_dll.port_close = MagicMock()
		mock_dll.read_state = MagicMock(return_value=0)  # ADSERR_NOERR
		mock_get_dll.return_value = mock_dll

		# Create interface and check connection
		ads = ADSInterface("192.168.100.117.1.1")
		result = ads.check_connection()

		# Verify
		self.assertTrue(result)
		mock_dll.port_open.assert_called_once()
		mock_dll.read_state.assert_called_once()
		mock_dll.port_close.assert_called_once_with(12345)

	@patch('tcpkgman.ads_interface.get_ads_dll')
	def test_connection_failure(self, mock_get_dll):
		"""Test connection check with ADS error."""
		from tcpkgman.ads_dll import ADSError

		# Mock DLL
		mock_dll = MagicMock()
		mock_dll.port_open = MagicMock(return_value=12345)
		mock_dll.port_close = MagicMock()
		mock_dll.read_state = MagicMock(return_value=0x6)  # Target not found
		mock_get_dll.return_value = mock_dll

		# Create interface and check connection
		ads = ADSInterface("192.168.100.117.1.1")

		with self.assertRaises(ADSError) as ctx:
			ads.check_connection()

		# Verify error code
		self.assertEqual(ctx.exception.code, 0x6)

		# Verify port was closed even after error
		mock_dll.port_close.assert_called_once_with(12345)


if __name__ == '__main__':
	unittest.main()
