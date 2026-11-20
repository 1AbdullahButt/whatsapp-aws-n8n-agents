"""Collect the Lambda code into aws/build/ for `sam build`.

    .venv\\Scripts\\python aws\\build.py

Copies only the extraction modules (no FastAPI API, no review queue), cloud/
and the shared logging helper. The one dependency is pdfplumber, which pulls
in pdfminer.six, pypdfium2 and Pillow; `sam build` downloads their Linux wheels.
"""
import shutil
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BUILD = PROJECT / "aws" / "build"
SHARED = PROJECT.parent / "shared"

EXTRACTOR_FILES = ["__init__.py", "pipeline.py", "fields.py", "pdf_text.py", "validate.py", "duplicates.py"]
PDFPLUMBER_VERSION = "0.11.10"


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "extractor").mkdir(parents=True)
    for name in EXTRACTOR_FILES:
        source = PROJECT / "extractor" / name
        if source.exists():
            shutil.copy2(source, BUILD / "extractor" / name)
        else:
            (BUILD / "extractor" / name).write_text("", encoding="utf-8")
    shutil.copytree(PROJECT / "cloud", BUILD / "cloud", ignore=shutil.ignore_patterns("__pycache__"))
    (BUILD / "shared").mkdir()
    for name in ("__init__.py", "logging_setup.py"):
        shutil.copy2(SHARED / name, BUILD / "shared" / name)
    (BUILD / "requirements.txt").write_text(f"pdfplumber=={PDFPLUMBER_VERSION}\n", encoding="utf-8")
    files = sorted(p.relative_to(BUILD).as_posix() for p in BUILD.rglob("*") if p.is_file())
    print(f"Wrote {len(files)} files to {BUILD}:")
    for name in files:
        print("  " + name)


if __name__ == "__main__":
    main()
