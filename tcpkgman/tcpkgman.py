"""Command-line interface for tcpkgman."""

import argparse
import os
import platform
import sys
from . import Tcpkg, __version__
from .ads_ssh_key_manager import ADSSSHKeyManager
from .ads_interface import ADSInterface
from .ads_dll import ADSError
from .utils import Utils, BOLD, CYAN, YELLOW, GREEN, DIM, RESET


class Tcpkgman:
	"""CLI for tcpkgman."""

	def __init__(self):
		if platform.system() != "Windows":
			raise RuntimeError("tcpkgman only supports Windows for now")
		
		self.parser = argparse.ArgumentParser(
			prog="tcpkgman",
			description=f"tcpkgman v{__version__} - TwinCAT Package Manager Helper",
			epilog="""Examples:
  tcpkgman --remote myplc install pkg
  tcpkgman --remote-add myplc
  tcpkgman --remote-add
  tcpkgman --remote-remove myplc

  TCPKG_REMOTE=myplc tcpkgman install pkg""",
			formatter_class=argparse.RawDescriptionHelpFormatter,
		)

		self.parser.add_argument(
			"--remote",
			metavar="<name>",
			help="Remote target (or use TCPKG_REMOTE env var)",
		)
		self.parser.add_argument(
			"--remote-add",
			metavar="<name>",
			nargs="?",
			const="",
			help="Add remote target interactively",
		)
		self.parser.add_argument(
			"--remote-remove",
			metavar="<name>",
			help="Remove remote target",
		)
		self.parser.add_argument(
			"--remote-list",
			action="store_true",
			help="List all configured remote targets",
		)
		self.parser.add_argument(
			"--remote-ssh-init",
			action="store_true",
			help="Initialize SSH connection to target via ADS",
		)

	def _collect_remote_parameters(self, remote_name: str | None = None) -> dict:
		"""Collect remote configuration parameters from user."""
		print(f"\n{BOLD}Configure remote target:{RESET}")

		host = Utils.prompt(f"{CYAN}Host address or IP{RESET}", remote_name, False)
		user = Utils.prompt(f"{CYAN}User{RESET}", "Administrator", True)
		port = Utils.prompt(f"{CYAN}SSH Port{RESET}", "22", False)

		# Internet access
		internet_choice = Utils.choice(
			"Does the remote target have internet access?\n"
			"(If no, packages will be copied from this machine to the target)",
			["no (copy packages from here)", "yes (download directly on target)"],
			default_index=0
		)
		has_internet_access = internet_choice == "yes (download directly on target)"

		# SSH key
		default_key = ADSSSHKeyManager.find_default_key()
		if default_key is None:
			ssh_dir = ADSSSHKeyManager.get_ssh_dir()
			generate_choice = Utils.choice(
				f"No SSH key found in {ssh_dir}. Would you like to generate SSH public key (ed25519)?",
				["yes", "no (provide custom path)"],
				default_index=0
			)
			if generate_choice == "yes":
				default_key = ADSSSHKeyManager.generate_key("ed25519")

		key_file = Utils.prompt("Path to private key file", default_key, True)

		return {
			"host": host,
			"user": user,
			"port": port,
			"key_file": key_file,
			"has_internet_access": has_internet_access
		}

	def run(self):
		"""Run CLI."""
		try:
			args, remaining = self.parser.parse_known_args()

			# Check for TCPKG_REMOTE environment variable if --remote not provided
			if not args.remote:
				args.remote = os.environ.get('TCPKG_REMOTE')

			# Check if any operation requires TcPkg
			needs_tcpkg = args.remote_add or args.remote_remove or args.remote_list or remaining
			if needs_tcpkg:
				Tcpkg.check_tcpkg_installed()

			# Handle remote-ssh-init
			if args.remote_ssh_init:
				self._ssh_init_interactive()
				return

			# Handle remote-add
			if args.remote_add is not None:
				# Prompt for name if not provided
				remote_name = args.remote_add if args.remote_add else Utils.prompt(f"{CYAN}Remote name{RESET}", None, True)

				if Tcpkg.check_remote_exists(remote_name):
					print(f"Remote '{remote_name}' already exists")
				else:
					self._add_remote_interactive(remote_name, skip_confirmation=True)
				return

			# Handle remote-remove
			if args.remote_remove:
				Utils.check_admin_privileges()
				Tcpkg.remove_remote(args.remote_remove)
				return

			# Handle remote-list
			if args.remote_list:
				Tcpkg.list_remotes()
				return

			# Handle other commands
			if not remaining:
				self.parser.print_help()
				sys.exit(0)

			if not args.remote:
				Utils.error("--remote or TCPKG_REMOTE required")

			if not Tcpkg.check_remote_exists(args.remote):
				self._add_remote_interactive(args.remote)
			Tcpkg.run_with_remote(args.remote, remaining)

		except KeyboardInterrupt:
			print("\nCancelled", file=sys.stderr)
			sys.exit(130)
		except Exception as e:
			Utils.error(str(e))

	def _add_remote_interactive(self, remote_name: str, skip_confirmation: bool = False) -> None:
		"""Add remote target interactively."""

		if not skip_confirmation:
			response = input(
				f"\n{YELLOW}Remote target '{CYAN}{remote_name}{RESET}{YELLOW}' "
				f"does not exist. Add it now? (y/n):{RESET} "
			)
			if response.lower() != "y":
				raise RuntimeError("Remote target not configured.")

		Utils.check_admin_privileges()

		params = self._collect_remote_parameters(remote_name)

		# Check if SSH key exists and connection works
		if not self._check_ssh_setup(params["host"], params["user"], params["port"], params["key_file"]):
			# Offer to run SSH init via ADS
			if self._offer_ssh_init_via_ads():
				self._ssh_init_interactive()
				print()  # Empty line for readability

		Tcpkg.add_remote(
			remote_name,
			params["host"],
			params["user"],
			params["port"],
			params["key_file"],
			params["has_internet_access"]
		)

	def _check_ssh_setup(self, host: str, user: str, port: str, key_file: str) -> bool:
		"""Check if SSH key exists and connection works. Returns True if setup is good."""
		from pathlib import Path

		# Check if key file exists
		if not Path(key_file).exists():
			print(f"\n{YELLOW}SSH key not found: {key_file}{RESET}")
			return False

		# Try SSH connection
		print(f"\n{CYAN}Testing SSH connection to {user}@{host}:{port}...{RESET}")
		if ADSSSHKeyManager.test_ssh_connection(host, user, port, key_file):
			print(f"{GREEN}SSH connection successful{RESET}")
			return True
		else:
			print(f"{YELLOW}SSH connection failed{RESET}")
			return False

	def _offer_ssh_init_via_ads(self) -> bool:
		"""Ask user if they want to set up SSH via ADS. Returns True if user accepts."""
		response = input(
			f"\n{CYAN}Set up SSH connection via ADS (requires TwinCAT route to target)? (y/n):{RESET} "
		)
		return response.lower() == "y"

	def _ssh_init_interactive(self) -> None:
		print(f"\n{BOLD}Initialize SSH connection via ADS{RESET}")

		# Check if TwinCAT Router is installed by loading DLL
		try:
			from .ads_dll import get_ads_dll
			get_ads_dll()
		except FileNotFoundError as e:
			raise RuntimeError(
				"TwinCAT Router not installed. Install TwinCAT XAE or TwinCAT ADS Runtime to use this feature.\n"
				f"Details: {e}"
			)

		# Try to read TwinCAT targets
		targets = ADSInterface.get_twincat_targets()

		# Build choices list with mapping (targets + manual entry)
		choices = []
		choice_to_netid = {}
		for name, (net_id, ip_addr) in targets.items():
			display = f"{name} (IP: {ip_addr}, Net ID: {net_id})"
			choices.append(display)
			choice_to_netid[display] = net_id
		choices.append("Manual entry")

		choice = Utils.choice(
			"Select target:",
			choices,
			default_index=0
		)

		if choice == "Manual entry":
			ams_net_id = Utils.prompt(f"{CYAN}Target AMS NetID{RESET}", None, True)
		else:
			ams_net_id = choice_to_netid[choice]

		username = Utils.prompt(f"{CYAN}Username{RESET}", "Administrator", False)

		try:
			manager = ADSSSHKeyManager(ams_net_id, username)

			print(f"\n{CYAN}Connecting to {ams_net_id}...{RESET}")
			manager.check_connection()

			# Find which key will be used
			key_path = ADSSSHKeyManager.find_default_public_key()
			key_generated = False
			if not key_path:
				ssh_dir = ADSSSHKeyManager.get_ssh_dir()
				generate_choice = Utils.choice(
					f"No SSH key found in {ssh_dir}. Would you like to generate SSH public key (ed25519)?",
					["yes", "no"],
					default_index=1
				)
				if generate_choice == "yes":
					private_key = ADSSSHKeyManager.generate_key("ed25519")
					key_path = private_key + ".pub"
					key_generated = True
				else:
					print("Cancelled")
					return

			# Confirm before copying
			if key_generated:
				print(f"\n{GREEN}SSH key {key_path} generated.{RESET}")
			else:
				print(f"\n{CYAN}SSH public key found:{RESET} {DIM}{key_path}{RESET}")
			confirm = input(f"Copy this key to {ams_net_id} over ADS? (y/n): ").strip().lower()
			if confirm != 'y':
				print("Cancelled")
				return

			print(f"{CYAN}Copying SSH key...{RESET}")
			manager.copy_ssh_key(key_path)

			print(f"{CYAN}Restarting OpenSSH server...{RESET}")
			manager.restart_openssh_server()

			print(f"{CYAN}Checking SSH connection...{RESET}")
			if manager.check_ssh_connection():
				print(f"{GREEN}SSH connection successful!{RESET}")
			else:
				print(f"{YELLOW}SSH connection check failed. Verify SSH server is running on target.{RESET}")

		except ADSError as e:
			if e.code == 0x7:
				raise RuntimeError(
					f"Target not found (ADS error 0x7).\n"
					f"Create AMS route to {ams_net_id} in TwinCAT Router and try again."
				)
			elif e.code == 0x745:
				raise RuntimeError(
					f"Target timeout (ADS error 0x745).\n"
					f"Check network connection to target."
				)
			else:
				raise RuntimeError(f"ADS error: {e.message}")

