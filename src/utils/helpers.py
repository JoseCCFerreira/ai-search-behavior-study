from pathlib import Path
from typing import Iterable


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_region(region: str) -> str:
    return region.strip().title()


def normalize_platform(platform: str) -> str:
    return platform.strip().title()


def normalize_string(value: str) -> str:
    return value.strip().title()


def safe_read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
