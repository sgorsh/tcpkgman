"""Generic ADS interface for TwinCAT targets."""

from contextlib import contextmanager
import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from .ads_dll import get_ads_dll, AmsAddr

# TwinCAT System Service constants
SYSTEMSERVICE_PORT = 10000
SYSTEMSERVICE_NOSEEK = -1
SYSTEMSERVICE_FOPEN = 120
SYSTEMSERVICE_FREAD = 122
SYSTEMSERVICE_FWRITE = 123
SYSTEMSERVICE_FGETSTATUS = 134
SYSTEMSERVICE_STARTPROCESS = 500


# FOPEN mode flags
FOPEN_READ = 1 << 0
FOPEN_WRITE = 1 << 1
FOPEN_PLUS = 1 << 3
FOPEN_BINARY = 1 << 4
FOPEN_ENSURE_DIR = 1 << 6
FOPEN_OVERWRITE = 1 << 8
FOPEN_PATH_GENERIC = 1 << 16


class ADSInterface:
	"""Generic ADS interface for TwinCAT System Service operations."""

	def __init__(self, ams_net_id: str):
		"""Initialize ADS interface. Requires ADS route configured in TwinCAT Router."""
		self.ams_net_id = ams_net_id
		self._dll = get_ads_dll()

	def check_connection(self) -> bool:
		"""
		Check if target is reachable via ADS.

		Returns:
			True if connection successful, False otherwise

		Raises:
			ADSError: If connection fails with specific ADS error
		"""
		from .ads_dll import AmsAddr, ADSError, ADSERR_NOERR

		port = self._dll.port_open()
		try:
			addr = AmsAddr(self.ams_net_id, SYSTEMSERVICE_PORT)
			result = self._dll.read_state(port, addr)

			if result == ADSERR_NOERR:
				return True
			else:
				raise ADSError(result)
		finally:
			self._dll.port_close(port)

	@staticmethod
	def get_twincat_targets() -> dict[str, tuple[str, str]]:
		"""
		Read TwinCAT static routes from StaticRoutes.xml.

		Returns:
			Dict of {name: (ams_net_id, ip_address)} for configured routes.
			Routes with missing Name, NetId, or Address are skipped.

		Note:
			Reads from StaticRoutes.xml using TWINCAT3DIR environment variable.
			All three fields (Name, NetId, Address) are mandatory.
		"""
		targets = {}

		# Get path from TWINCAT3DIR environment variable
		twincat_dir = os.environ.get("TWINCAT3DIR")
		if not twincat_dir:
			return targets

		routes_path = Path(twincat_dir) / "Target" / "StaticRoutes.xml"
		if not routes_path.exists():
			return targets

		try:
			tree = ET.parse(routes_path)
			root = tree.getroot()

			# Parse each Route entry
			for route in root.findall(".//Route"):
				name = route.findtext("Name")
				net_id = route.findtext("NetId")
				address = route.findtext("Address")
				if name and net_id and address:
					targets[name] = (net_id, address)
		except Exception:
			pass

		return targets

	@contextmanager
	def _connect(self):
		"""Connect to System Service."""
		port = self._dll.port_open()
		addr = AmsAddr(self.ams_net_id, SYSTEMSERVICE_PORT)
		try:
			yield (self._dll, port, addr)
		finally:
			self._dll.port_close(port)

	@contextmanager
	def _file_handle(self, dll, port, addr, path: str, mode_flags: int):
		"""Context manager for file operations."""
		# Open file
		path_bytes = path.encode('utf-8') + b'\x00'
		result = dll.read_write(port, addr, SYSTEMSERVICE_FOPEN, mode_flags, 4, path_bytes)
		handle = struct.unpack('<I', result)[0]
		try:
			yield handle
		finally:
			# Close file (suppress errors)
			try:
				dll.write(port, addr, handle, SYSTEMSERVICE_NOSEEK, b'')
			except Exception:
				pass

	def write_file(self, remote_path: str, content: str):
		"""Write file to target."""
		mode = FOPEN_WRITE | FOPEN_PLUS | FOPEN_BINARY | FOPEN_ENSURE_DIR | FOPEN_OVERWRITE | FOPEN_PATH_GENERIC
		data = content.encode('utf-8')
		with self._connect() as (dll, port, addr):
			with self._file_handle(dll, port, addr, remote_path, mode) as handle:
				dll.read_write(port, addr, SYSTEMSERVICE_FWRITE, handle, 4, data)

	def read_file(self, remote_path: str, max_size: int = 1024 * 1024) -> str:
		"""Read file from target (up to max_size bytes)."""
		mode = FOPEN_READ | FOPEN_BINARY | FOPEN_PATH_GENERIC
		with self._connect() as (dll, port, addr):
			with self._file_handle(dll, port, addr, remote_path, mode) as handle:
				data = dll.read_write(port, addr, SYSTEMSERVICE_FREAD, handle, max_size, b'')
				return data.rstrip(b'\x00').decode('utf-8', errors='replace')

	def file_exists(self, remote_path: str) -> bool:
		"""Check if file exists on target."""
		try:
			path_bytes = remote_path.encode('utf-8') + b'\x00'
			with self._connect() as (dll, port, addr):
				dll.read_write(port, addr, SYSTEMSERVICE_FGETSTATUS, 1, 36, path_bytes)
				return True
		except Exception:
			return False

	def run_command(self, command: str, working_dir: str = "", timeout_ms: int = 5000, hide_window: bool = True) -> int:
		"""Execute command on target. Returns 0 (exit code not available via ADS)."""
		with self._connect() as (dll, port, addr):
			# Parse command
			parts = command.split(None, 1)
			process_str = parts[0] if parts else command
			cmdline_str = parts[1] if len(parts) > 1 else ""

			# Build STARTPROCESS structure
			process_bytes = process_str.encode('utf-8')
			dir_bytes = working_dir.encode('utf-8')
			cmdline_bytes = cmdline_str.encode('utf-8')
			data = struct.pack('<III', len(process_bytes), len(dir_bytes), len(cmdline_bytes))
			data += process_bytes + b'\x00' + dir_bytes + b'\x00' + cmdline_bytes + b'\x00'

			# Execute command
			index_offset = (timeout_ms & 0xFFFF) | (0x10000 if hide_window else 0)
			dll.write(port, addr, SYSTEMSERVICE_STARTPROCESS, index_offset, data)
			return 0
