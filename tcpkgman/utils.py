"""Utility functions and constants for tcpkgman."""

import ctypes
import sys
from typing import List, NoReturn

# ANSI color codes
BOLD = "\033[1m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"


class Utils:
	"""Utility class for tcpkgman."""

	@staticmethod
	def check_admin_privileges() -> None:
		"""Check if running with administrator privileges."""
		if not ctypes.windll.shell32.IsUserAnAdmin():
			raise RuntimeError("Requires administrator privileges. Run as Administrator.")

	@staticmethod
	def prompt(field: str, default: str | None, required: bool) -> str:
		"""Prompt for input with optional default."""
		prompt_text = f"{field} [{default}]: " if default else f"{field}: "
		value = input(prompt_text).strip() or default or ""
		if required and not value:
			raise ValueError(f"{field} is required")
		return value

	@staticmethod
	def choice(prompt: str, choices: List[str], default_index: int = 0) -> str:
		"""Display a numbered choice menu and return the selected option."""
		print(f"\n{CYAN}{prompt}{RESET}")
		for i, choice in enumerate(choices, 1):
			marker = f"{GREEN}*{RESET}" if i - 1 == default_index else " "
			print(f"  {marker} {DIM}{i}.{RESET} {choice}")

		while True:
			try:
				choice_input = input(f"\n{DIM}Select [1-{len(choices)}] (default: {default_index + 1}):{RESET} ").strip()
				if not choice_input:
					return choices[default_index]

				index = int(choice_input) - 1
				if 0 <= index < len(choices):
					return choices[index]
				else:
					print(f"Please enter a number between 1 and {len(choices)}")
			except ValueError:
				print(f"Please enter a valid number")

	@staticmethod
	def error(msg: str) -> NoReturn:
		"""Print error and exit."""
		print(f"Error: {msg}", file=sys.stderr)
		sys.exit(1)
