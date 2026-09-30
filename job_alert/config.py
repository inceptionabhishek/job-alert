from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    from . import toml_compat as tomllib


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Settings:
    raw: dict[str, Any]
    config_path: Path
    database_path: Path
    log_level: str
    dry_run: bool
    telegram_token: str | None
    telegram_chat_id: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def matching(self) -> dict[str, Any]:
        return self.raw.get("matching", {})

    @property
    def http(self) -> dict[str, Any]:
        return self.raw.get("http", {})

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.raw.get("telegram", {}).get("enabled", True))


def load_config(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    load_dotenv(config_path.parent / ".env")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    app = raw.get("app", {})
    db = Path(app.get("database_path", "data/jobs.db"))
    if not db.is_absolute():
        db = config_path.parent / db
    sources = [source for source in raw.get("sources", []) if source.get("enabled", True)]
    return Settings(
        raw=raw,
        config_path=config_path,
        database_path=db,
        log_level=str(app.get("log_level", "INFO")),
        dry_run=bool(app.get("dry_run", False)),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        sources=sources,
    )
