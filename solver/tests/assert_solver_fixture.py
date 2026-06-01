#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


def value_at(document, path):
    value = document
    for part in path.split("."):
        if "[" in part:
            name, index = part[:-1].split("[", 1)
            value = value[name][int(index)]
        else:
            value = value[part]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--expect", action="append", default=[])
    args = parser.parse_args()

    fixture = Path(args.input)
    completed = subprocess.run(
        [args.solver],
        input=fixture.read_text(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode

    document = json.loads(completed.stdout)
    for expectation in args.expect:
        path, expected = expectation.split("=", 1)
        actual = value_at(document, path)
        if str(actual) != expected:
            sys.stderr.write(
                f"{fixture}: expected {path}={expected!r}, got {actual!r}\n"
            )
            sys.stderr.write(completed.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
