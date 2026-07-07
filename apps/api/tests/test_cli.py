"""Unit tests for the ``krititva`` operator CLI (FR-4.12.3). No DB required."""

from __future__ import annotations

import pytest

from app.cli import (
    build_backup_command,
    build_restore_command,
    libpq_dsn,
    main,
)


def test_libpq_dsn_strips_async_driver() -> None:
    assert libpq_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_backup_command_uses_custom_format() -> None:
    cmd = build_backup_command("postgresql+asyncpg://u:p@h/db", "out.dump")
    assert cmd[:2] == ["pg_dump", "-Fc"]
    assert "--file" in cmd and "out.dump" in cmd
    assert "postgresql://u:p@h/db" in cmd


def test_restore_command_is_clean_idempotent() -> None:
    cmd = build_restore_command("postgresql+asyncpg://u:p@h/db", "in.dump")
    assert cmd[0] == "pg_restore"
    assert "--clean" in cmd and "--if-exists" in cmd
    assert cmd[-1] == "in.dump"


def test_main_print_only_backup(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--print-only", "backup", "--output", "snap.dump"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "pg_dump -Fc" in out
    assert "snap.dump" in out


def test_main_print_only_restore(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--print-only", "restore", "snap.dump"])
    assert rc == 0
    assert "pg_restore" in capsys.readouterr().out


def test_main_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        main([])
