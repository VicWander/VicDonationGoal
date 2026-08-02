from __future__ import annotations

import os
import platform
import subprocess
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
TARGET = TOOLS_DIR / "cloudflared.exe"


def architecture_download_url() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        filename = "cloudflared-windows-amd64.exe"
    elif machine in {"arm64", "aarch64"}:
        filename = "cloudflared-windows-arm64.exe"
    else:
        filename = "cloudflared-windows-386.exe"
    return f"https://github.com/cloudflare/cloudflared/releases/latest/download/{filename}"


def verify(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 1_000_000:
        return False, "file missing or too small"
    try:
        result = subprocess.run(
            [str(path), "--version"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        text = (result.stdout or result.stderr).strip()
        return result.returncode == 0, text
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


def install(force: bool = False) -> Path:
    if os.name != "nt":
        raise RuntimeError("cloudflared installer is intended for Windows")

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() and not force:
        ok, version = verify(TARGET)
        if ok:
            print(f"cloudflared is already installed: {version}")
            return TARGET

    url = architecture_download_url()
    download = TOOLS_DIR / "cloudflared.download.exe"
    print("Downloading cloudflared from the official Cloudflare GitHub release...")
    print(url)

    if download.exists():
        try:
            download.unlink()
        except Exception:
            pass

    request = urllib.request.Request(url, headers={"User-Agent": "VicDonationGoal/1.4.3"})
    with urllib.request.urlopen(request, timeout=180) as response, download.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())

    if download.stat().st_size < 1_000_000:
        raise RuntimeError("Downloaded file is unexpectedly small")

    # Windows Defender can hold a freshly downloaded EXE for a short scan. Retry
    # instead of failing with WinError 32. No leaked mkstemp descriptor is used.
    last_error: BaseException | None = None
    for attempt in range(40):
        try:
            os.replace(download, TARGET)
            last_error = None
            break
        except (PermissionError, OSError) as error:
            last_error = error
            time.sleep(min(0.5, 0.05 * (attempt + 1)))
    if last_error:
        raise last_error

    ok, version = verify(TARGET)
    if not ok:
        raise RuntimeError(version)
    print("Installed successfully:")
    print(TARGET)
    print(version)
    return TARGET


def main() -> int:
    try:
        install()
        return 0
    except Exception as error:
        print(f"Installation failed: {type(error).__name__}: {error}")
        print("Manual fallback:")
        print("1. Download cloudflared-windows-amd64.exe from the official release.")
        print("2. Rename it to cloudflared.exe.")
        print(f"3. Place it here: {TARGET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
