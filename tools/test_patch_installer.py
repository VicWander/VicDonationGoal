from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SOURCE = Path(__file__).resolve().parent / "apply_patch.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_test_project(root: Path, stability_exit: int) -> None:
    (root / "tools").mkdir(parents=True)
    (root / "core" / "data").mkdir(parents=True)
    (root / "_patch" / "files" / "tools").mkdir(parents=True)
    shutil.copy2(SOURCE, root / "tools" / "apply_patch.py")
    (root / "tools" / "stop_all.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (root / "tools" / "stability_check.py").write_text(f"raise SystemExit({stability_exit})\n", encoding="utf-8")
    (root / "VERSION").write_text("1.4.4\n", encoding="utf-8")
    (root / "core" / "data" / "donations.json").write_text('[{"amount":100}]\n', encoding="utf-8")
    (root / "app.txt").write_text("old\n", encoding="utf-8")

    payloads = {
        "VERSION": "1.4.4.1\n",
        "app.txt": "new\n",
        "tools/apply_patch.py": SOURCE.read_text(encoding="utf-8"),
    }
    files = []
    for relative, text in payloads.items():
        path = root / "_patch" / "files" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append({"path": relative, "sha256": digest(path)})
    manifest = {"compatibleFrom": ["1.4.4"], "targetVersion": "1.4.4.1", "files": files}
    (root / "_patch" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def run_case(stability_exit: int) -> tuple[int, Path]:
    directory = Path(tempfile.mkdtemp(prefix="vic_patch_test_"))
    write_test_project(directory, stability_exit)
    result = subprocess.run(
        [sys.executable, str(directory / "tools" / "apply_patch.py")],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, directory


def main() -> int:
    success_code, success = run_case(0)
    try:
        assert success_code == 0
        assert (success / "VERSION").read_text(encoding="utf-8").strip() == "1.4.4.1"
        assert (success / "app.txt").read_text(encoding="utf-8") == "new\n"
        assert json.loads((success / "core" / "data" / "donations.json").read_text(encoding="utf-8"))[0]["amount"] == 100
        assert list((success / "backups" / "patch_backups").glob("*.zip"))
    finally:
        shutil.rmtree(success, ignore_errors=True)

    failure_code, failure = run_case(1)
    try:
        assert failure_code == 1
        assert (failure / "VERSION").read_text(encoding="utf-8").strip() == "1.4.4"
        assert (failure / "app.txt").read_text(encoding="utf-8") == "old\n"
        assert json.loads((failure / "core" / "data" / "donations.json").read_text(encoding="utf-8"))[0]["amount"] == 100
    finally:
        shutil.rmtree(failure, ignore_errors=True)

    print("Patch installer: success and rollback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
