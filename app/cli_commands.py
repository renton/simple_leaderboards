"""Click commands exposed via the Flask CLI."""

from __future__ import annotations

import getpass
import os
import sys

import click
from flask.cli import with_appcontext


@click.command("create-admin")
@click.option("--username", required=True, help="Admin username to create.")
@click.option(
    "--password-env",
    "password_env",
    default=None,
    help="Name of an env var holding the new admin's password. "
    "If unset, you'll be prompted interactively.",
)
@with_appcontext
def create_admin(username: str, password_env: str | None) -> None:
    """Create a new admin user. Refuses to overwrite an existing username."""
    from app.extensions import db
    from app.models.user import AdminUser

    existing = AdminUser.query.filter_by(username=username).first()
    if existing is not None:
        click.echo(f"Admin '{username}' already exists. Aborting.", err=True)
        sys.exit(1)

    if password_env:
        password = os.environ.get(password_env)
        if not password:
            click.echo(f"Env var {password_env} is empty.", err=True)
            sys.exit(2)
    else:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm: ")
        if password != confirm:
            click.echo("Passwords did not match.", err=True)
            sys.exit(3)

    if len(password) < 12:
        click.echo("Password must be at least 12 characters.", err=True)
        sys.exit(4)

    user = AdminUser(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f"Created admin '{username}' (id={user.id}).")
