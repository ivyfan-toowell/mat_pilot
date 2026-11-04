"""Read-only environment diagnostics; never print configuration values or keys."""

import importlib.metadata
import json
import platform
import shutil
import socket
import subprocess
import sys

from app.core.config import get_settings


def docker_status() -> str:
    if not shutil.which("docker"):
        return "not_installed"
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return "ready" if result.returncode == 0 else "engine_unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable_or_timed_out"


def port_available(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def main() -> None:
    settings = get_settings()
    versions = {}
    for package in ["fastapi", "mp-api", "pymatgen", "pandas", "streamlit", "pydantic"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not_installed"
    report = {
        "os": platform.system(),
        "python": platform.python_version(),
        "python_supported": sys.version_info[:2] == (3, 13),
        "uv_installed": shutil.which("uv") is not None,
        "docker": docker_status(),
        "ports_reachable_only_not_db_authentication": {
            "5432": port_available(5432),
            "5433": port_available(5433),
        },
        "configured_not_live_verified": {
            "materials_project": bool(settings.mp_api_key),
            "dashscope": bool(settings.dashscope_api_key),
            "database_url": bool(settings.database_url),
        },
        "packages": versions,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
