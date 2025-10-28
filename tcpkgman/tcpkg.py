import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Minimum required TcPkg version
MIN_TCPKG_VERSION = "2.3.65"


class Tcpkg:
	"""Thin wrapper for TcPkg CLI operations - all static methods"""

	@staticmethod
	def _run_command(cmd: List[str], error_msg: str, input_text: Optional[str] = None) -> None:
		"""Execute command and raise RuntimeError if it fails."""
		result = subprocess.run(cmd, input=input_text, text=True)
		if result.returncode != 0:
			raise RuntimeError(error_msg)

	@staticmethod
	def check_tcpkg_installed() -> None:
		"""Verify TcPkg is in PATH."""
		try:
			subprocess.run(["where", "TcPkg"], check=True, capture_output=True)
		except (subprocess.CalledProcessError, FileNotFoundError):
			raise RuntimeError("TcPkg not found. Install TcPkg and add to PATH.")

	@staticmethod
	def check_remote_exists(remote_name: str) -> bool:
		"""Check if remote target exists by parsing remote list output."""
		try:
			result = subprocess.run(["TcPkg", "remote", "list"], capture_output=True, text=True)
			return any(line.strip().startswith(f"{remote_name} - Host:")
					  for line in result.stdout.split('\n'))
		except subprocess.CalledProcessError:
			return False

	@staticmethod
	def run_with_remote(remote_name: str, commands: List[str]) -> None:
		"""Execute TcPkg command with remote flag. TcPkg prints its own errors."""
		# Run without capturing to preserve colors and immediate output
		result = subprocess.run(["TcPkg"] + commands + ["-r", remote_name])

		# Exit with same code as TcPkg
		if result.returncode != 0:
			sys.exit(result.returncode)

	@staticmethod
	def add_remote(remote_name: str, host: str, user: str, port: str, key_file: str,
				   has_internet_access: bool = False) -> None:
		"""Add remote target with provided parameters."""
		cmd = ["TcPkg", "remote", "add", "-n", remote_name,
			   "--host", host, "--port", port, "-u", user, "-y"]

		if has_internet_access:
			cmd.append("--internet-access")

		cmd.extend(["-k", key_file])

		Tcpkg._run_command(cmd, f"Failed to add remote target '{remote_name}'")

	@staticmethod
	def remove_remote(remote_name: str) -> None:
		"""Remove remote target."""
		Tcpkg._run_command(
			["TcPkg", "remote", "remove", remote_name],
			f"Failed to remove remote target '{remote_name}'"
		)

	@staticmethod
	def list_remotes() -> None:
		"""List all configured remote targets. Output goes directly to stdout."""
		subprocess.run(["TcPkg", "remote", "list"])
