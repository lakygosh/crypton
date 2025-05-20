"""
Technical indicators module for the Crypton trading bot.

Implements various technical indicators used for trading decisions,
including Bollinger Bands, RSI, and SMA.
"""
from typing import Dict, Optional, Union

import pandas as pd
import pandas_ta as ta
from loguru import logger

from crypton.utils.config import load_config


class IndicatorEngine:
    """
    Engine for calculating technical indicators on price data.
    
    Supports:
    - Bollinger Bands (BB)
    - Relative Strength Index (RSI)
    - Simple Moving Average (SMA)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the indicator engine with configuration settings.
        
        Args:
            config: Dictionary containing configuration settings
        """
        self.config = config or load_config()
        
        # Load default parameters from config
        self.bb_length = self.config.get('bb', {}).get('length', 20)
        self.bb_std = self.config.get('bb', {}).get('std', 2)
        self.rsi_length = self.config.get('rsi', {}).get('length', 14)
        self.sma_length = self.config.get('sma', {}).get('length', 50)
        
        logger.info("Indicator engine initialized with parameters:")
        logger.info(f"  BB: length={self.bb_length}, std={self.bb_std}")
        logger.info(f"  RSI: length={self.rsi_length}")
        logger.info(f"  SMA: length={self.sma_length}")
    
    def add_bollinger_bands(
        self, 
        df: pd.DataFrame, 
        length: Optional[int] = None, 
        std: Optional[float] = None,
        source_column: str = 'close'
    ) -> pd.DataFrame:
        """
        Add Bollinger Bands to a DataFrame.
        
        Args:
            df: DataFrame containing price data
            length: Period length for calculation (defaults to config value)
            std: Standard deviation multiplier (defaults to config value)
            source_column: Column to use for calculations (default: 'close')
            
        Returns:
            DataFrame with Bollinger Bands columns added
        """
        try:
            # Use provided parameters or default to class values
            length = length or self.bb_length
            std = std or self.bb_std
            
            # Check if the source column exists
            if source_column not in df.columns:
                logger.error(f"Column '{source_column}' not found in DataFrame")
                return df
            
            # Calculate Bollinger Bands
            bb_result = ta.bbands(
                close=df[source_column], 
                length=length, 
                std=std
            )
            
            # Merge with original dataframe
            # BBL = lower band, BBM = middle band, BBU = upper band
            df = pd.concat([df, bb_result], axis=1)
            
            logger.debug(f"Added Bollinger Bands (length={length}, std={std})")
            return df
            
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return df
    
    def add_rsi(
        self, 
        df: pd.DataFrame, 
        length: Optional[int] = None,
        source_column: str = 'close'
    ) -> pd.DataFrame:
        """
        Add Relative Strength Index (RSI) to a DataFrame.
        
        Args:
            df: DataFrame containing price data
            length: Period length for calculation (defaults to config value)
            source_column: Column to use for calculations (default: 'close')
            
        Returns:
            DataFrame with RSI column added
        """
        try:
            # Use provided parameter or default to class value
            length = length or self.rsi_length
            
            # Check if the source column exists
            if source_column not in df.columns:
                logger.error(f"Column '{source_column}' not found in DataFrame")
                return df
            
            # Calculate RSI
            df['RSI'] = ta.rsi(
                close=df[source_column], 
                length=length
            )
            
            logger.debug(f"Added RSI (length={length})")
            return df
            
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return df
    
    def add_sma(
        self, 
        df: pd.DataFrame, 
        length: Optional[int] = None,
        source_column: str = 'close'
    ) -> pd.DataFrame:
        """
        Add Simple Moving Average (SMA) to a DataFrame.
        
        Args:
            df: DataFrame containing price data
            length: Period length for calculation (defaults to config value)
            source_column: Column to use for calculations (default: 'close')
            
        Returns:
            DataFrame with SMA column added
        """
        try:
            # Use provided parameter or default to class value
            length = length or self.sma_length
            
            # Check if the source column exists
            if source_column not in df.columns:
                logger.error(f"Column '{source_column}' not found in DataFrame")
                return df
            
            # Calculate SMA
            df['SMA'] = ta.sma(
                close=df[source_column], 
                length=length
            )
            
            logger.debug(f"Added SMA (length={length})")
            return df
            
        except Exception as e:
            logger.error(f"Error calculating SMA: {e}")
            return df
    
    def add_all_indicators(
        self, 
        df: pd.DataFrame,
        source_column: str = 'close'
    ) -> pd.DataFrame:
        """
        Add all configured indicators to a DataFrame.
        
        Args:
            df: DataFrame containing price data
            source_column: Column to use for calculations (default: 'close')
            
        Returns:
            DataFrame with all indicator columns added
        """
        df = self.add_bollinger_bands(df, source_column=source_column)
        df = self.add_rsi(df, source_column=source_column)
        df = self.add_sma(df, source_column=source_column)
        
        logger.info("Added all technical indicators to DataFrame")
        return df
