"""``krititva`` operator CLI (FR-4.12.3).

A thin, auditable wrapper over the documented ``pg_dump -Fc`` / ``pg_restore``
backup procedure — it builds the exact commands and, unless ``--print-only`` is
passed, runs them. Postgres is dumped in the custom (``-Fc``) format and uploaded
assets are copied alongside the dump.

Deliberately minimal: no bespoke backup format, no scheduling. Operators own the
cron/retention policy; this just makes the round-trip a one-liner.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import get_settings


def libpq_dsn(async_dsn: str) -> str:
    """Convert a SQLAlchemy async DSN to a libpq one that pg_dump understands."""
    return async_dsn.replace("+asyncpg", "").replace("+psycopg2", "")


def build_backup_command(dsn: str, output: str) -> list[str]:
    return ["pg_dump", "-Fc", "--dbname", libpq_dsn(dsn), "--file", output]


def build_restore_command(dsn: str, input_file: str) -> list[str]:
    return [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--dbname",
        libpq_dsn(dsn),
        input_file,
    ]


def _run(cmd: list[str], *, print_only: bool) -> int:
    if print_only:
        print(" ".join(cmd))
        return 0
    return subprocess.run(cmd, check=False).returncode


def cmd_backup(args: argparse.Namespace) -> int:
    dsn = get_settings().postgres_dsn
    rc = _run(build_backup_command(dsn, args.output), print_only=args.print_only)
    if rc != 0:
        return rc

    assets = Path(args.assets_dir)
    dest = Path(f"{args.output}.assets")
    if args.print_only:
        print(f"# copy assets: {assets} -> {dest}")
    elif assets.is_dir():
        shutil.copytree(assets, dest, dirs_exist_ok=True)
        print(f"assets copied: {assets} -> {dest}")
    else:
        print(f"assets dir not found, skipped: {assets}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    dsn = get_settings().postgres_dsn
    return _run(build_restore_command(dsn, args.input), print_only=args.print_only)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="krititva", description="Krititva operator CLI")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="print the commands instead of executing them",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="pg_dump -Fc the database and copy assets")
    backup.add_argument("--output", default="krititva.dump", help="dump file path")
    backup.add_argument("--assets-dir", default="assets", help="uploaded-assets directory")
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="pg_restore a dump file")
    restore.add_argument("input", help="dump file to restore")
    restore.set_defaults(func=cmd_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
