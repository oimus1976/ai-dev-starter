#!/usr/bin/env python3
"""Run one child command while mirroring its output to a shareable UTF-8 log."""

from __future__ import annotations

import argparse
import locale
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _component(value: str, label: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{label} must contain only letters, digits, '.', '_' or '-'"
        )
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mirror one child command to the terminal and a temporary UTF-8 log."
    )
    parser.add_argument(
        "--work-item",
        required=True,
        type=lambda value: _component(value, "work item"),
    )
    parser.add_argument(
        "--name",
        required=True,
        type=lambda value: _component(value, "name"),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _log_path(work_item: str, name: str) -> Path:
    temp_root = os.environ.get("TEMP")
    if not temp_root:
        raise RuntimeError("TEMP is not available")

    log_root = Path(temp_root) / "ai-dev-starter" / work_item
    log_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    suffix = uuid.uuid4().hex[:8]
    return log_root / f"{name}-{stamp}-{os.getpid()}-{suffix}.log"


def _decode_child_line(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        fallback = locale.getpreferredencoding(False) or "utf-8"
        if fallback.lower().replace("_", "-") == "utf-8":
            return data.decode("utf-8", errors="replace")
        return data.decode(fallback, errors="replace")


def _write_line(log_file, text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
    log_file.write(text)
    log_file.flush()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        _parser().error("a child command is required after '--'")

    log_path = _log_path(args.work_item, args.name)

    exit_code = 127
    with log_path.open("w", encoding="utf-8-sig", newline="") as log_file:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
            )
            assert process.stdout is not None
            for line in process.stdout:
                _write_line(log_file, _decode_child_line(line))
            exit_code = process.wait()
        except OSError as exc:
            _write_line(log_file, f"ERROR={exc}\n")

        _write_line(log_file, f"EXIT_CODE={exit_code}\n")

    print(f"LOG={log_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
