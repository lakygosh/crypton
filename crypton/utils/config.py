"""
Configuration utilities for the Crypton trading bot.

This module provides functions for loading and managing configuration settings.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger


def get_project_root() -> Path:
    """
    Get the project root directory.
    
    Returns:
        Path to the project root
    """
    return Path(__file__).parent.parent.parent


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path: Path to the configuration file (optional)
        
    Returns:
        Dictionary containing configuration settings
    """
    # Default to config.yml in the project root if not specified
    if not config_path:
        config_path = os.path.join(get_project_root(), "config.yml")
    
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {config_path}")
        # Try to find the sample config file
        sample_path = f"{config_path}.sample"
        try:
            with open(sample_path, "r") as f:
                config = yaml.safe_load(f)
            
            logger.warning(f"Using sample configuration from {sample_path}")
            return config
        except FileNotFoundError:
            logger.error(f"No configuration file found: {config_path} or {sample_path}")
            return {}
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return {}
