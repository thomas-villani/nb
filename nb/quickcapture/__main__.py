"""Windowless entry point for autostart: ``pythonw -m nb.quickcapture``.

Launching via ``pythonw.exe`` avoids a console window flashing at login,
which is why the autostart registry entry targets this module rather than the
``nb`` console script.
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="nb.quickcapture")
    parser.add_argument("--hotkey", default="ctrl+alt+n")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("nb quickcapture currently supports Windows only.", file=sys.stderr)
        raise SystemExit(1)

    from nb.quickcapture.app import QuickCaptureApp

    QuickCaptureApp(hotkey=args.hotkey).run()


if __name__ == "__main__":
    main()
