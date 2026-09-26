"""Reject incomplete Python installations, including cached zero-byte files."""

from importlib import metadata
from pathlib import Path
import sysconfig


def main() -> int:
    problems = []
    checked = 0
    root = Path(sysconfig.get_path("purelib"))
    for info in sorted(root.glob("*.dist-info")):
        for name in ("METADATA", "WHEEL", "RECORD"):
            path = info / name
            if not path.is_file() or path.stat().st_size == 0:
                problems.append(f"Missing/empty package metadata: {path}")
    for distribution in metadata.distributions():
        for record in distribution.files or ():
            # pip rewrites console-script shebangs; package source and binary
            # files keep the wheel's declared size after installation.
            if record.size is None or not str(record).endswith((".py", ".so", ".pyd")):
                continue
            path = Path(distribution.locate_file(record))
            # The official slim base deliberately omits pip/setuptools tests.
            # Ignore only absent test files from those two bundled packages;
            # an existing empty file is still checked against its RECORD.
            if (not path.exists()
                    and distribution.metadata.get("Name", "").lower() in {"pip", "setuptools"}
                    and {"test", "tests", "idle_test"}.intersection(record.parts)):
                continue
            checked += 1
            if not path.is_file() or path.stat().st_size != record.size:
                problems.append(f"Missing/truncated package file: {path}")
    for problem in problems[:30]:
        print(problem)
    print(f"Package integrity: checked {checked} source/binary files; {len(problems)} failures")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
