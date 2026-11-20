"""Tenant desk app package.

The shared helpers (config, logging) live one folder up, in
D:\\Project\\Portfolio\\shared. We add that folder to sys.path here so
`from shared.config import ...` works when you run the server or the
staff CLI from inside tenant-desk.
"""
import sys
from pathlib import Path

PORTFOLIO_ROOT = Path(__file__).resolve().parents[2]
if str(PORTFOLIO_ROOT) not in sys.path:
    sys.path.append(str(PORTFOLIO_ROOT))
