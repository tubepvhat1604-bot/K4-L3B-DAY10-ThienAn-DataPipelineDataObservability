from __future__ import annotations

from core.config import load_settings
from observability.dashboard import build_dashboard


if __name__ == "__main__":
    settings = load_settings()
    path = build_dashboard(settings)
    print(f"Dashboard: {path}")
