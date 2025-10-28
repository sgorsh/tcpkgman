"""ADS SSH key management for TwinCAT targets.

Manages SSH keys and authentication to Windows TwinCAT targets via ADS System Service.
Requires manual ADS route configuration in TwinCAT Router.
"""

import os
import subprocess
import time
from pathlib import Path
from .ads_interface import ADSInterface

class ADSSSHKeyManager(ADSInterface):
	"""Manage SSH keys and authentication for Windows TwinCAT targets via ADS."""

	# Windows SSH paths
	AUTHORIZED_KEYS_PATH = "C:/ProgramData/ssh/administrators_authorized_keys"
	PID_FILE_PATH = "C:/ProgramData/ssh/sshd.pid"

	# SSH key types and names (in order of preference)
	SSH_KEY_TYPES = [
		("ed25519", "id_ed25519"),
		("rsa", "id_rsa")
	]

	def __init__(self, ams_net_id: str, username: str = "Administrator"):
		"""
		Initialize ADS SSH key manager.

		Args:
			ams_net_id: Target AMS NetID (e.g., "192.168.1.100.1.1")
			username: Username on target (default: Administrator)

		Note:
			ADS route must be configured manually in TwinCAT Router first.
		"""
		super().__init__(ams_net_id)
		self.username = username
		self.ssh_dir = self.get_ssh_dir()

	@property
	def ip_address(self) -> str:
		"""Extract IP address from AMS NetID (e.g., "192.168.1.100.1.1" -> "192.168.1.100")."""
		return '.'.join(self.ams_net_id.split('.')[:4])

	@staticmethod
	def get_ssh_dir() -> Path:
		"""Get the .ssh directory path."""
		return Path.home() / ".ssh"

	@staticmethod
	def find_default_key() -> str | None:
		"""
		Find the default SSH private key, preferring ed25519 over rsa.

		Returns:
			Path to private key file, or None if not found
		"""
		ssh_dir = ADSSSHKeyManager.get_ssh_dir()
		for _, key_name in ADSSSHKeyManager.SSH_KEY_TYPES:
			key_path = ssh_dir / key_name
			if key_path.exists():
				return str(key_path)
		return None

	@staticmethod
	def find_default_public_key() -> str | None:
		"""
		Find the default SSH public key, preferring ed25519 over rsa.

		Returns:
			Path to public key file, or None if not found
		"""
		ssh_dir = ADSSSHKeyManager.get_ssh_dir()
		for _, key_name in ADSSSHKeyManager.SSH_KEY_TYPES:
			pub_key_path = ssh_dir / f"{key_name}.pub"
			if pub_key_path.exists():
				return str(pub_key_path)
		return None

	@staticmethod
	def generate_key(key_type: str = "ed25519") -> str:
		"""
		Generate SSH key pair and return the private key path.

		Args:
			key_type: SSH key type (default: ed25519)

		Returns:
			Path to generated private key file

		Raises:
			RuntimeError: If key generation fails
		"""
		ssh_dir = ADSSSHKeyManager.get_ssh_dir()
		ssh_dir.mkdir(mode=0o700, exist_ok=True)

		key_name = f"id_{key_type}"
		key_path = ssh_dir / key_name
		pub_key_path = Path(str(key_path) + ".pub")

		# Check if both keys exist
		if key_path.exists() and pub_key_path.exists():
			return str(key_path)

		# If private key exists but public key doesn't, fail
		if key_path.exists() and not pub_key_path.exists():
			raise RuntimeError(
				f"Private key exists at {key_path} but public key is missing.\n"
				f"Delete the private key or regenerate the public key manually:\n"
				f"  ssh-keygen -y -f {key_path} > {pub_key_path}"
			)

		cmd = [
			"ssh-keygen",
			"-t", key_type,
			"-f", str(key_path),
			"-N", "",  # No passphrase
			"-C", f"tcpkgman@{os.environ.get('COMPUTERNAME', 'windows')}"
		]

		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			raise RuntimeError(f"Failed to generate SSH key: {result.stderr}")

		return str(key_path)

	@staticmethod
	def test_ssh_connection(host: str, user: str, port: str = "22", key_file: str | None = None, max_retries: int = 1) -> bool:
		"""
		Test SSH connection to a host with given parameters.

		Args:
			host: Target hostname or IP address
			user: SSH username
			port: SSH port (default: "22")
			key_file: Path to SSH private key (optional)
			max_retries: Maximum number of connection attempts (default: 1)

		Returns:
			True if SSH connection successful, False otherwise

		Raises:
			FileNotFoundError: If SSH client is not installed
		"""
		for attempt in range(1, max_retries + 1):
			try:
				cmd = [
					'ssh',
					'-o', 'BatchMode=yes',
					'-o', 'ConnectTimeout=5',
					'-o', 'StrictHostKeyChecking=accept-new',
					'-p', port,
				]

				if key_file:
					cmd.extend(['-i', key_file])

				cmd.extend([f'{user}@{host}', 'exit 0'])

				result = subprocess.run(
					cmd,
					capture_output=True,
					timeout=10,
					text=True
				)

				if result.returncode == 0:
					return True

			except FileNotFoundError:
				raise FileNotFoundError("SSH client not found. Install OpenSSH client on this machine.")

			except (subprocess.TimeoutExpired, Exception):
				pass

			if attempt < max_retries:
				time.sleep(1)

		return False

	def copy_ssh_key(self, key_path: str | None = None):
		"""
		Copy SSH public key to Windows admin authorized_keys if not already present.

		Args:
			key_path: Local SSH public key path (auto-detects if None)

		Raises:
			FileNotFoundError: If local SSH key not found
		"""
		# Auto-detect SSH key
		if not key_path:
			for keyname in ["id_ed25519.pub", "id_rsa.pub"]:
				candidate = self.ssh_dir / keyname
				if candidate.exists():
					key_path = str(candidate)
					break

		if not key_path:
			raise FileNotFoundError(
				f"No SSH key found in {self.ssh_dir}. Create {self.ssh_dir / 'id_ed25519.pub'} or specify key_path"
			)

		# Read local key
		with open(key_path, 'r') as f:
			key_content = f.read().strip()

		# Check if key already exists
		try:
			existing_content = self.read_file(self.AUTHORIZED_KEYS_PATH)
			if self._is_key_present(existing_content, key_content):
				return
		except Exception:
			# File doesn't exist or can't be read - will create it
			pass

		# Copy key
		self.write_file(self.AUTHORIZED_KEYS_PATH, key_content + "\n")

	def restart_openssh_server(self, timeout_ms: int = 10000) -> int:
		"""
		Restart OpenSSH server with PID-based verification.

		Args:
			timeout_ms: Timeout in milliseconds (default: 10000)

		Returns:
			Exit code (0 on success)

		Raises:
			RuntimeError: If PID file not found or PID doesn't change within timeout
		"""
		old_pid = self._read_sshd_pid()
		if old_pid is None:
			raise RuntimeError("SSH server PID file not found - service may not be running")

		cmd = 'powershell.exe -Command "Restart-Service sshd"'
		self.run_command(cmd, timeout_ms=timeout_ms, hide_window=True)

		# Poll PID file until it changes or timeout expires
		timeout_s = timeout_ms // 1000
		self._poll_pid_change(old_pid, timeout_s)

		return 0

	def check_ssh_connection(self, max_retries: int = 3) -> bool:
		"""
		Test SSH connection to target using the configured key.

		Args:
			max_retries: Maximum number of connection attempts (default: 3)

		Returns:
			True if SSH connection successful, False otherwise

		Raises:
			FileNotFoundError: If SSH client is not installed
		"""

		for attempt in range(1, max_retries + 1):
			try:
				result = subprocess.run(
					[
						'ssh',
						'-o', 'BatchMode=yes',
						'-o', 'ConnectTimeout=10',
						'-o', 'StrictHostKeyChecking=no',
						'-o', 'UserKnownHostsFile=NUL',
						'-o', 'GlobalKnownHostsFile=NUL',
						f'{self.username}@{self.ip_address}',
						'exit 0'
					],
					capture_output=True,
					timeout=3,
					text=True
				)

				if result.returncode == 0:
					return True

			except FileNotFoundError:
				raise FileNotFoundError("SSH client not found. Install OpenSSH client on this machine.")

			except (subprocess.TimeoutExpired, Exception):
				pass

			if attempt < max_retries:
				time.sleep(1)

		return False

	def _check_openssh_service_exists(self) -> bool:
		"""
		Check if OpenSSH service exists on target by checking for sshd_config.

		Returns:
			True if sshd service exists, False otherwise
		"""
		# Check if sshd_config exists - indicates OpenSSH is installed
		return self.file_exists("C:/ProgramData/ssh/sshd_config")

	def _is_key_present(self, authorized_keys_content: str, key_content: str) -> bool:
		"""
		Check if SSH public key is already in authorized_keys.

		Args:
			authorized_keys_content: Current content of authorized_keys file
			key_content: SSH public key to check

		Returns:
			True if key is already present
		"""
		# Normalize both contents (strip whitespace, compare key parts)
		key_content = key_content.strip()

		# Check each line in authorized_keys
		for line in authorized_keys_content.splitlines():
			if line.strip() == key_content:
				return True

		return False

	def _read_sshd_pid(self) -> int | None:
		"""
		Read sshd PID from PID file.

		Returns:
			PID as integer, or None if file doesn't exist or is invalid

		Note:
			PID file location defined in PID_FILE_PATH constant
		"""
		try:
			content = self.read_file(self.PID_FILE_PATH).strip()
			return int(content)
		except Exception:
			return None

	def _poll_pid_change(self, old_pid: int, timeout_s: int) -> int:
		"""
		Poll PID file until it changes from old_pid.

		Args:
			old_pid: Previous PID to compare against
			timeout_s: Timeout in seconds

		Returns:
			New PID value

		Raises:
			RuntimeError: If PID doesn't change or file not found within timeout
		"""
		for _ in range(timeout_s):
			time.sleep(1)
			new_pid = self._read_sshd_pid()

			if new_pid is not None and new_pid != old_pid:
				return new_pid

		# Timeout expired, check final state
		new_pid = self._read_sshd_pid()

		if new_pid is None:
			raise RuntimeError(
				f"SSH server restart failed: PID file not found after {timeout_s}s timeout"
			)

		if new_pid == old_pid:
			raise RuntimeError(
				f"SSH server restart failed: PID unchanged ({old_pid}) after {timeout_s}s timeout"
			)

		return new_pid
