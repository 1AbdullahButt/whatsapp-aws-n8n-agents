"""pytest setup: make `app`, `tests` and `shared` importable."""
import sys
from pathlib import Path

TENANT_DESK = Path(__file__).resolve().parent
PORTFOLIO_ROOT = TENANT_DESK.parent  # holds the shared/ folder

for folder in (TENANT_DESK, PORTFOLIO_ROOT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
