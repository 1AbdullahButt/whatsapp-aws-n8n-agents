"""Collect the Lambda code into aws/build/ for `sam build`.

    py -3.12 aws\\build.py

Copies app/ (minus the FastAPI server), cloud/ and the two shared helpers.
The only dependency Lambda needs is httpx: boto3 is already in the runtime.
"""
import shutil
from pathlib import Path

TENANT_DESK = Path(__file__).resolve().parents[1]
BUILD = TENANT_DESK / "aws" / "build"
SHARED = TENANT_DESK.parent / "shared"

SKIP_IN_APP = {"webhook.py"}   # the local FastAPI server; Lambda uses cloud/webhook.py
HTTPX_VERSION = "0.28.1"


def copy_package(source, target, skip=()):
    target.mkdir(parents=True)
    for path in source.glob("*.py"):
        if path.name not in skip:
            shutil.copy2(path, target / path.name)


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    copy_package(TENANT_DESK / "app", BUILD / "app", SKIP_IN_APP)
    copy_package(TENANT_DESK / "cloud", BUILD / "cloud")
    (BUILD / "shared").mkdir()
    for name in ("__init__.py", "config.py", "logging_setup.py"):
        shutil.copy2(SHARED / name, BUILD / "shared" / name)
    (BUILD / "requirements.txt").write_text(f"httpx=={HTTPX_VERSION}\n", encoding="utf-8")
    files = sorted(p.relative_to(BUILD).as_posix() for p in BUILD.rglob("*") if p.is_file())
    print(f"Wrote {len(files)} files to {BUILD}:")
    for name in files:
        print("  " + name)


if __name__ == "__main__":
    main()
