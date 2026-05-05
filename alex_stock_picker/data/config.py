from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    load_dotenv()
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    validate_sec_user_agent(config)
    return config


def validate_sec_user_agent(config: dict[str, Any]) -> None:
    env_key = config.get("sec", {}).get("user_agent_env", "SEC_USER_AGENT")
    user_agent = os.getenv(env_key, "")

    # Only validate when SEC functionality is used later, but warn early by requiring a real-looking value.
    if not user_agent:
        return

    invalid_markers = ["example.com", "replace_with_email", "your_email"]
    if any(marker in user_agent for marker in invalid_markers):
        raise ValueError("Please set a real SEC User-Agent email in .env")

    if "@" not in user_agent:
        raise ValueError("SEC User-Agent should include a contact email address.")
