"""Small local commands used to validate the project environment."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from srd import __version__

app = typer.Typer(no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"srd {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Run local Stewardship Research Dossier utilities."""


@app.command()
def doctor() -> None:
    """Confirm that the project is running on the supported Python version."""

    if sys.version_info[:2] != (3, 12):
        typer.echo("srd doctor: Python 3.12 is required", err=True)
        raise typer.Exit(code=1)

    typer.echo("srd doctor: ok (Python 3.12)")


if __name__ == "__main__":
    app()
