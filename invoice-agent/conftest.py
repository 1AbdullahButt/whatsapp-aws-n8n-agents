"""pytest setup: make `shared` (one folder up) and `extractor` importable."""
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent      # D:\Project\Portfolio\invoice-agent
PORTFOLIO_DIR = PROJECT_DIR.parent                 # D:\Project\Portfolio

for folder in (PROJECT_DIR, PORTFOLIO_DIR):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
