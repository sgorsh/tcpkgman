"""ctypes wrapper for TcAdsDll.dll - Beckhoff ADS communication library."""

import ctypes
import sys
from pathlib import Path

# Type definitions
ads_i32 = ctypes.c_long
ads_ui32 = ctypes.c_ulong
ads_ui16 = ctypes.c_ushort
ads_ui8 = ctypes.c_ubyte

ADSERR_NOERR = 0x00


class AmsNetId(ctypes.Structure):
	"""AMS NetID structure (6 bytes)."""
	_fields_ = [("b", ads_ui8 * 6)]

	@staticmethod
	def from_string(net_id: str) -> 'AmsNetId':
		"""Parse AMS NetID from string (e.g., "192.168.1.100.1.1")."""
		parts = [int(p) for p in net_id.split('.')]
		if len(parts) != 6:
			raise ValueError(f"Invalid AMS NetID format: {net_id}")
		addr = AmsNetId()
		for i in range(6):
			addr.b[i] = parts[i]
		return addr


class AmsAddr(ctypes.Structure):
	"""AMS address structure (NetID + port)."""
	_fields_ = [("netId", AmsNetId), ("port", ads_ui16)]

	def __init__(self, net_id: str | None = None, port: int = 10000):
		super().__init__()
		if net_id:
			self.netId = AmsNetId.from_string(net_id)
			self.port = port


class ADSError(Exception):
	"""ADS error with code."""
	def __init__(self, code: int, message: str | None = None):
		self.code = code
		self.message = message or f"ADS error 0x{code:04X}"
		super().__init__(self.message)


class TcAdsDll:
	"""ctypes wrapper for TcAdsDll.dll."""

	def __init__(self):
		if sys.platform != 'win32':
			raise RuntimeError("TcAdsDll.dll is only available on Windows")

		# Try loading from PATH first
		try:
			self._dll = ctypes.WinDLL("TcAdsDll.dll")
		except OSError:
			# Try typical TwinCAT installation location
			typical_path = Path(r"C:\Program Files (x86)\Beckhoff\TwinCAT\Common64\TcAdsDll.dll")
			if typical_path.exists():
				self._dll = ctypes.WinDLL(str(typical_path))
			else:
				raise FileNotFoundError(
					"TcAdsDll.dll not found. TwinCAT Router is not installed.\n"
					"Install TwinCAT XAE or TwinCAT ADS Runtime.\n"
					f"Expected location: {typical_path}"
				)
		self._setup_functions()

	def _setup_functions(self):
		"""Setup function signatures for ADS API calls."""
		self._dll.AdsPortOpenEx.restype = ads_i32
		self._dll.AdsPortCloseEx.argtypes = [ads_i32]
		self._dll.AdsPortCloseEx.restype = ads_i32
		self._dll.AdsSyncReadStateReqEx.argtypes = [
			ads_i32, ctypes.POINTER(AmsAddr), ctypes.POINTER(ads_ui16), ctypes.POINTER(ads_ui16)
		]
		self._dll.AdsSyncReadStateReqEx.restype = ads_i32
		self._dll.AdsSyncWriteReqEx.argtypes = [
			ads_i32, ctypes.POINTER(AmsAddr), ads_ui32, ads_ui32, ads_ui32, ctypes.c_void_p
		]
		self._dll.AdsSyncWriteReqEx.restype = ads_i32
		self._dll.AdsSyncReadWriteReqEx2.argtypes = [
			ads_i32, ctypes.POINTER(AmsAddr), ads_ui32, ads_ui32, ads_ui32,
			ctypes.c_void_p, ads_ui32, ctypes.c_void_p, ctypes.POINTER(ads_ui32)
		]
		self._dll.AdsSyncReadWriteReqEx2.restype = ads_i32

	def port_open(self) -> int:
		"""Open ADS port."""
		port = self._dll.AdsPortOpenEx()
		if port == 0:
			raise ADSError(0, "Failed to open ADS port")
		return port

	def port_close(self, port: int):
		"""Close ADS port."""
		result = self._dll.AdsPortCloseEx(port)
		if result != ADSERR_NOERR:
			raise ADSError(result, f"Failed to close ADS port {port}")

	def read_state(self, port: int, addr: AmsAddr) -> int:
		"""Read ADS state (connection check). Returns error code (0 = success)."""
		ads_state = ads_ui16()
		device_state = ads_ui16()
		result = self._dll.AdsSyncReadStateReqEx(
			port, ctypes.byref(addr), ctypes.byref(ads_state), ctypes.byref(device_state)
		)
		return result

	def write(self, port: int, addr: AmsAddr, index_group: int, index_offset: int, data: bytes):
		"""Write data to ADS device."""
		result = self._dll.AdsSyncWriteReqEx(
			port, ctypes.byref(addr), index_group, index_offset, len(data),
			ctypes.cast(ctypes.c_char_p(data), ctypes.c_void_p) if data else None
		)
		if result != ADSERR_NOERR:
			raise ADSError(result, f"Write failed (group={index_group}, offset={index_offset})")

	def read_write(self, port: int, addr: AmsAddr, index_group: int, index_offset: int,
				   read_length: int, write_data: bytes) -> bytes:
		"""Read and write data in single ADS call."""
		read_buffer = ctypes.create_string_buffer(read_length)
		bytes_read = ads_ui32()
		result = self._dll.AdsSyncReadWriteReqEx2(
			port, ctypes.byref(addr), index_group, index_offset, read_length,
			ctypes.cast(read_buffer, ctypes.c_void_p), len(write_data),
			ctypes.cast(ctypes.c_char_p(write_data), ctypes.c_void_p) if write_data else None,
			ctypes.byref(bytes_read)
		)
		if result != ADSERR_NOERR:
			raise ADSError(result, f"Read/write failed (group={index_group}, offset={index_offset})")
		return read_buffer.raw[:bytes_read.value]


# Singleton instance
_ads_dll = None


def get_ads_dll() -> TcAdsDll:
	"""Get singleton TcAdsDll instance."""
	global _ads_dll
	if _ads_dll is None:
		_ads_dll = TcAdsDll()
	return _ads_dll
