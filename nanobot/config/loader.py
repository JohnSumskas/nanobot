"""Configuration loading utilities."""

import json
from pathlib import Path

import pydantic
from loguru import logger

from nanobot.config.schema import Config

# Global variable to store current config path (for multi-instance support)
_current_config_path: Path | None = None

# Flag to indicate if backup config was used (so agent can notify user)
_used_backup_config: bool = False


def set_config_path(path: Path) -> None:
    """Set the current config path (used to derive data directory)."""
    global _current_config_path
    _current_config_path = path


def get_config_path() -> Path:
    """Get the configuration file path."""
    if _current_config_path:
        return _current_config_path
    return Path.home() / ".nanobot" / "config.json"


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    If the main config fails to load, attempts to restore from backup.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    global _used_backup_config
    _used_backup_config = False
    
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            config = Config.model_validate(data)
            # Config loaded successfully - create backup
            _backup_config(path)
            return config
        except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            
            # Try to restore from backup
            config = _restore_from_backup(path)
            if config:
                return config
            
            logger.warning("No valid backup available. Using default configuration.")

    return Config()


def was_backup_used() -> bool:
    """Check if the backup config was used on startup.
    
    Call this after load_config() to determine if the agent should
    notify the user about config restoration.
    """
    return _used_backup_config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _backup_config(path: Path) -> None:
    """
    Create a backup of the config file.

    Called after successfully loading and validating config to preserve
    a known-good copy that can be restored if the config gets corrupted.
    """
    import shutil

    backup_path = path.with_suffix(".json.bak")
    try:
        shutil.copy2(path, backup_path)
        logger.debug(f"Config backed up to {backup_path}")
    except OSError as e:
        logger.warning(f"Failed to backup config: {e}")


def _restore_from_backup(path: Path) -> Config | None:
    """
    Attempt to load config from backup file.

    Does NOT overwrite the corrupted main config - leaves it in place
    so the user can inspect and fix it manually.

    Args:
        path: Path to the main config file (backup is derived from this).

    Returns:
        Config object if backup was successfully loaded, None otherwise.
    """
    global _used_backup_config

    backup_path = path.with_suffix(".json.bak")
    
    if not backup_path.exists():
        logger.warning(f"No backup config found at {backup_path}")
        return None
    
    try:
        with open(backup_path, encoding="utf-8") as f:
            data = json.load(f)
        data = _migrate_config(data)
        config = Config.model_validate(data)
        
        # Backup is valid - use it (but don't overwrite the corrupted config)
        logger.warning(f"Main config is corrupted. Using backup: {backup_path}")
        logger.warning("The corrupted config.json has NOT been modified - please fix it manually.")
        
        _used_backup_config = True
        return config
        
    except (json.JSONDecodeError, ValueError, pydantic.ValidationError, OSError) as e:
        logger.error(f"Backup config is also invalid: {e}")
        return None


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
