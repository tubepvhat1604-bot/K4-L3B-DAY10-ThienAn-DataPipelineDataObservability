"""One-click test: `python script/run_tests.py` (Bonus B3).

Chay toan bo pytest suite (ingestion -> cleaning -> GX gate -> retrieval -> pipelines end-to-end)
voi coverage, fail neu coverage < 80%. Test chay trong thu muc tam, khong dong vao `data/` that,
khong goi LLM API va khong can tai model embedding.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    if importlib.util.find_spec("pytest_cov") is None:
        sys.exit('Thieu pytest-cov. Cai bang: python -m pip install -e ".[dev]"  (hoac: uv sync --extra dev)')
    command = [
        sys.executable, "-m", "pytest",
        "--cov", "--cov-report=term-missing", "--cov-fail-under=80",
        *sys.argv[1:],
    ]
    sys.exit(subprocess.call(command, cwd=ROOT))
