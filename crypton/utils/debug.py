"""
Debug utilities for the Crypton trading bot.

This module provides helper functions for debugging data issues
and ensuring data formats are correct.
"""
import pandas as pd
from loguru import logger


def debug_dataframe(df: pd.DataFrame, title: str = "DataFrame Debug Info") -> None:
    """
    Print debug information about a DataFrame.
    
    Args:
        df: DataFrame to debug
        title: Title for the debug output
    """
    logger.debug(f"===== {title} =====")
    logger.debug(f"Shape: {df.shape}")
    logger.debug(f"Columns: {df.columns.tolist()}")
    logger.debug(f"Index: {df.index.name or 'unnamed'}")
    logger.debug(f"First few rows:\n{df.head(2)}")
    logger.debug("=====================")


def ensure_indicator_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure that a DataFrame has required indicator columns.
    If indicators are missing, they will be calculated.
    
    Args:
        df: DataFrame with price data
        
    Returns:
        DataFrame with required indicator columns
    """
    from crypton.indicators.technical import IndicatorEngine
    
    # Create indicator engine
    indicator_engine = IndicatorEngine()
    
    # Check for required columns
    required_indicators = {
        'BBL': lambda df: indicator_engine.add_bollinger_bands(df),
        'BBU': lambda df: df,  # Will be added with BBL
        'RSI': lambda df: indicator_engine.add_rsi(df)
    }
    
    # Add missing indicators
    for col, calc_func in required_indicators.items():
        if col not in df.columns:
            logger.info(f"Adding missing indicator: {col}")
            df = calc_func(df)
    
    return df
