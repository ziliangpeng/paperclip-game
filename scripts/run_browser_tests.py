#!/usr/bin/env python3
# owner: paperclip-game CI
# trigger: pull requests, main pushes, and local native UI verification
# purpose: run real two-page Chrome checks against the public game page
"""Project CLI for the bounded native-browser acceptance checks."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> int:
    test_path = Path(__file__).resolve().parent.parent / "tests/browser_m1.py"
    spec = importlib.util.spec_from_file_location("paperclip_browser_m1", test_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
