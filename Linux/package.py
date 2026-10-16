#!/usr/bin/env python3
"""Build a transferable source ZIP without modifying the macOS project."""

from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parent
    output = root / "QuotaMonitor-GNOME46.zip"
    files = [root / name for name in ("README.md", "install.py", "package.py")]
    files += sorted(path for folder in ("extension", "tests") for path in (root / folder).rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts and
                    path.suffix != ".pyc" and path.name != "gschemas.compiled")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "QuotaMonitor-GNOME46/" + path.relative_to(root).as_posix())
    print(output)


if __name__ == "__main__":
    main()
