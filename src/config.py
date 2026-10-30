import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from dotenv import load_dotenv

from src.models import AppConfig, TradingConfig

# Default project paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
ENV_PATH = BASE_DIR / ".env"

# Load environment variables
load_dotenv(ENV_PATH)


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_PATH
        self.app_config: AppConfig = self._load_config()

    def _load_config(self) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return AppConfig(**data)
        except Exception as e:
            print(f"[!] Warning: Failed to parse config.yaml: {e}. Using defaults.")
            return AppConfig()

    def reload(self) -> AppConfig:
        self.app_config = self._load_config()
        return self.app_config

    def save(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.app_config.model_dump(), f, default_flow_style=False, sort_keys=False)

    @property
    def tg_api_id(self) -> Optional[int]:
        val = os.getenv("TG_API_ID")
        return int(val) if val and val.strip().isdigit() else None

    @property
    def tg_api_hash(self) -> Optional[str]:
        val = os.getenv("TG_API_HASH")
        return val.strip() if val else None

    @property
    def tg_phone(self) -> Optional[str]:
        val = os.getenv("TG_PHONE")
        return val.strip() if val else None

    @property
    def mt5_path(self) -> Optional[str]:
        val = os.getenv("MT5_PATH")
        if val and val.strip():
            return val.strip()
        return self.app_config.trading.target_path

    @property
    def mt5_login(self) -> Optional[int]:
        val = os.getenv("MT5_LOGIN")
        if val and val.strip().isdigit():
            return int(val)
        return self.app_config.trading.target_login

    @property
    def mt5_password(self) -> Optional[str]:
        val = os.getenv("MT5_PASSWORD")
        return val.strip() if val else None

    @property
    def mt5_server(self) -> Optional[str]:
        val = os.getenv("MT5_SERVER")
        return val.strip() if val else None


config_mgr = ConfigManager()
