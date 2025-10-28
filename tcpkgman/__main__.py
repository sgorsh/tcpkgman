"""Entry point for tcpkgman CLI."""

from .tcpkgman import Tcpkgman


def main() -> None:
    """Main entry point."""
    cli = Tcpkgman()
    cli.run()


if __name__ == "__main__":
    main()
