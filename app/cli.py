"""Flask CLI commands (e.g. `flask create-admin`)."""

from __future__ import annotations

from flask import Flask


def register_cli(app: Flask) -> None:
    from app.cli_commands import create_admin

    app.cli.add_command(create_admin)
