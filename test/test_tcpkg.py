"""Tests for Tcpkg thin wrapper class."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, call
from tcpkgman.tcpkg import Tcpkg


class TestTcpkg(unittest.TestCase):
	"""Test Tcpkg thin wrapper functionality."""

	@patch("subprocess.run")
	def test_check_tcpkg_installed_success(self, mock_run):
		"""Test successful TcPkg installation check."""
		mock_run.return_value = Mock(returncode=0)
		# Should not raise
		Tcpkg.check_tcpkg_installed()
		mock_run.assert_called_once()

	@patch("subprocess.run")
	def test_check_tcpkg_installed_failure(self, mock_run):
		"""Test TcPkg not installed."""
		mock_run.side_effect = FileNotFoundError()
		with self.assertRaises(RuntimeError):
			Tcpkg.check_tcpkg_installed()

	@patch("subprocess.run")
	def test_check_remote_exists_true(self, mock_run):
		"""Test checking if remote exists (returns True)."""
		mock_run.return_value = Mock(
			returncode=0,
			stdout="testplc - Host: 192.168.1.100\n"
		)
		self.assertTrue(Tcpkg.check_remote_exists("testplc"))

	@patch("subprocess.run")
	def test_check_remote_exists_false(self, mock_run):
		"""Test checking if remote exists (returns False)."""
		mock_run.return_value = Mock(
			returncode=0,
			stdout="otherplc - Host: 192.168.1.100\n"
		)
		self.assertFalse(Tcpkg.check_remote_exists("testplc"))

	@patch("subprocess.run")
	def test_run_with_remote_success(self, mock_run):
		"""Test running command with remote."""
		mock_run.return_value = Mock(returncode=0)
		Tcpkg.run_with_remote("testplc", ["install", "pkg"])
		mock_run.assert_called_once_with(
			["TcPkg", "install", "pkg", "-r", "testplc"]
		)

	@patch("subprocess.run")
	def test_add_remote_without_internet(self, mock_run):
		"""Test adding remote without internet access."""
		mock_run.return_value = Mock(returncode=0)

		Tcpkg.add_remote(
			remote_name="testplc",
			host="192.168.1.100",
			user="Administrator",
			port="22",
			key_file="C:/Users/test/.ssh/id_ed25519",
			has_internet_access=False
		)

		mock_run.assert_called_once()
		args = mock_run.call_args[0][0]
		self.assertIn("TcPkg", args)
		self.assertIn("remote", args)
		self.assertIn("add", args)
		self.assertIn("192.168.1.100", args)
		self.assertNotIn("--internet-access", args)

	@patch("subprocess.run")
	def test_add_remote_with_internet(self, mock_run):
		"""Test adding remote with internet access."""
		mock_run.return_value = Mock(returncode=0)

		Tcpkg.add_remote(
			remote_name="testplc",
			host="192.168.1.100",
			user="Administrator",
			port="22",
			key_file="C:/Users/test/.ssh/id_ed25519",
			has_internet_access=True
		)

		mock_run.assert_called_once()
		call_args = mock_run.call_args
		args = call_args[0][0]
		self.assertIn("--internet-access", args)

	@patch("subprocess.run")
	def test_remove_remote(self, mock_run):
		"""Test removing remote."""
		mock_run.return_value = Mock(returncode=0)
		Tcpkg.remove_remote("testplc")
		mock_run.assert_called_once_with(
			["TcPkg", "remote", "remove", "testplc"],
			input=None,
			text=True
		)

	@patch("subprocess.run")
	def test_list_remotes(self, mock_run):
		"""Test listing remotes."""
		mock_run.return_value = Mock(returncode=0)
		Tcpkg.list_remotes()
		mock_run.assert_called_once_with(["TcPkg", "remote", "list"])


if __name__ == "__main__":
	unittest.main()
