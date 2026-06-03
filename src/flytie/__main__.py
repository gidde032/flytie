"""Allow `python -m flytie` to invoke the CLI."""

from flytie.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
