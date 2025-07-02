"""
Mean reversion strategy implementation using Bollinger Bands and RSI.

This module implements the core trading strategy:
BUY  when close ≤ lower_band AND RSI < 30
SELL when close ≥ upper_band AND RSI > 70
"""
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from crypton.indicators.technical import IndicatorEngine
from crypton.utils.trade_history import TradeHistoryManager


class SignalType(Enum):
    """Enum representing trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class MeanReversionStrategy:
    """
    Mean reversion strategy using Bollinger Bands and RSI.
    
    The strategy generates buy signals when price touches the lower Bollinger Band
    and RSI is below 30 (oversold), and sell signals when price touches the upper
    Bollinger Band and RSI is above 70 (overbought).
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the strategy with configuration.
        
        Args:
            config: Dictionary containing configuration settings
        """
        from crypton.utils.config import load_config
        
        self.config = config or load_config()
        self.indicator_engine = IndicatorEngine(self.config)
        
        # Trading parameters
        self.rsi_oversold = self.config.get('rsi', {}).get('oversold', 30)
        self.rsi_overbought = self.config.get('rsi', {}).get('overbought', 70)

        # Graduated take-profit konfiguracija
        tp_cfg = self.config.get("risk", {}).get("take_profit", {})
        self.take_profit_tier1_pct = tp_cfg.get("tier1_pct", 0.01)
        self.take_profit_tier2_pct = tp_cfg.get("tier2_pct", 0.02)
        self.take_profit_tier3_pct = tp_cfg.get("tier3_pct", 0.03)

        # Prepare list for iteraciju u generate_signals
        self.tp_tiers = [
            {"name": "tier1", "pct": self.take_profit_tier1_pct, "size": tp_cfg.get("tier1_size_pct", 0.5)},
            {"name": "tier2", "pct": self.take_profit_tier2_pct, "size": tp_cfg.get("tier2_size_pct", 0.3)},
            {"name": "tier3", "pct": self.take_profit_tier3_pct, "size": tp_cfg.get("tier3_size_pct", 1.0)},
        ]
        
        # Cool-down period for trades (to avoid overtrading)
        cool_down_config = self.config.get('cool_down', {})
        cool_down_value = cool_down_config.get('minutes') or cool_down_config.get('hours', 4)
        
        # If we got minutes directly from config, convert to appropriate format
        if 'minutes' in cool_down_config:
            self.cool_down_hours = 0
            self.cool_down_minutes = cool_down_config['minutes']
            logger.info(f"Cool-down set to {self.cool_down_minutes} minutes")
        else:
            # Support for time interval formats like '15m' or legacy hours config
            self.cool_down_hours = 0
            self.cool_down_minutes = 0
            
            if isinstance(cool_down_value, str):
                if cool_down_value.endswith('m'):
                    try:
                        self.cool_down_minutes = int(cool_down_value.rstrip('m'))
                        logger.info(f"Cool-down set to {self.cool_down_minutes} minutes")
                    except ValueError:
                        logger.error(f"Invalid cool_down format: {cool_down_value}, using default 4 hours")
                        self.cool_down_hours = 4
                elif cool_down_value.endswith('h'):
                    try:
                        self.cool_down_hours = int(cool_down_value.rstrip('h'))
                        logger.info(f"Cool-down set to {self.cool_down_hours} hours")
                    except ValueError:
                        logger.error(f"Invalid cool_down format: {cool_down_value}, using default 4 hours")
                        self.cool_down_hours = 4
                else:
                    try:
                        # Assume hours if no unit is specified
                        self.cool_down_hours = float(cool_down_value)
                        logger.info(f"Cool-down set to {self.cool_down_hours} hours")
                    except ValueError:
                        logger.error(f"Invalid cool_down format: {cool_down_value}, using default 4 hours")
                        self.cool_down_hours = 4
            else:
                # If a numeric value, assume it's hours
                self.cool_down_hours = float(cool_down_value)
        
        # Track last trade time per symbol
        self.last_trade_time: Dict[str, datetime] = {}
        
        # Track positions with entry prices (in-memory only)
        self.positions: Dict[str, Dict] = {}
        
        logger.info("Mean reversion strategy initialized with parameters:")
        logger.info(f"  RSI oversold: {self.rsi_oversold}")
        logger.info(f"  RSI overbought: {self.rsi_overbought}")
        logger.info("  Take-profit tiers: " + ", ".join([f"{t['name']}={t['pct']*100:.1f}%" for t in self.tp_tiers]))
        if self.cool_down_minutes > 0:
            logger.info(f"  Cool-down period: {self.cool_down_minutes} minutes")
        else:
            logger.info(f"  Cool-down period: {self.cool_down_hours} hours")
        
        # Log loaded positions
        if self.positions:
            logger.info(f"Loaded {len(self.positions)} existing positions:")
            for symbol, pos in self.positions.items():
                entry_price = pos.get('entry_price', 'N/A')
                entry_time = pos.get('entry_time', 'N/A')
                logger.info(f"  {symbol}: Entry={entry_price} at {entry_time}")
        else:
            logger.info("No existing positions found")
        
        self.trade_history = TradeHistoryManager()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all required indicators for the strategy.
        
        Args:
            df: DataFrame containing price data (with at least 'close' column)
            
        Returns:
            DataFrame with added indicator columns
        """
        # Add Bollinger Bands
        df = self.indicator_engine.add_bollinger_bands(df)
        
        # Add RSI
        df = self.indicator_engine.add_rsi(df)
        
        # Add SMA (optional trend filter)
        df = self.indicator_engine.add_sma(df)
        
        return df
    
    def generate_signals(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Generate trading signals based on mean reversion strategy.
        Now only generates signals for the most recent candle to avoid showing
        historical signals repeatedly.
        
        Args:
            df: DataFrame with price data and indicators
            symbol: Trading pair symbol
            current_time: Current time for cool-down checking
            
        Returns:
            DataFrame with signals column added
        """
        try:
            # Initialize signal column with neutral values
            df['signal'] = SignalType.NEUTRAL.value
            
            # Check if we have enough data
            if len(df) < 20:  # Need at least 20 periods for indicators
                logger.warning(f"Insufficient data for {symbol}: {len(df)} candles")
                return df
            
            # Check cool-down period for this symbol if current_time is provided
            in_cooldown = False
            if current_time and symbol in self.last_trade_time:
                last_trade = self.last_trade_time[symbol]
                time_since_last_trade = current_time - last_trade
                cooldown_threshold = timedelta(hours=self.cool_down_hours, minutes=self.cool_down_minutes)
                
                if time_since_last_trade < cooldown_threshold:
                    in_cooldown = True
                    logger.info(f"{symbol} is in cool-down period. {time_since_last_trade.total_seconds() / 3600:.2f} hours since last trade.")
            
            if not in_cooldown:
                # Log values for the last few candles
                last_candles = df.iloc[-5:] if len(df) >= 5 else df
                for i, row in last_candles.iterrows():
                    logger.info(f"Candle {i} - Time: {row.name}, Close: {row['close']:.4f}, BBL: {row['BBL']:.4f}, RSI: {row['RSI']:.2f}")
                    logger.info(f"  Conditions: Price <= BBL: {row['close'] <= row['BBL']}, RSI < {self.rsi_oversold}: {row['RSI'] < self.rsi_oversold}")
                
                # Only generate signals for the most recent candle to avoid repeated historical signals
                latest_idx = df.index[-1]
                latest_candle = df.iloc[-1]
                
                # Generate BUY signal for latest candle only
                buy_condition = (latest_candle['close'] <= latest_candle['BBL']) and (latest_candle['RSI'] < self.rsi_oversold)
                if buy_condition:
                    df.loc[latest_idx, 'signal'] = SignalType.BUY.value
                    logger.info(f"NEW Buy signal generated for latest candle:")
                    logger.info(f"  Row {latest_idx}: Close={latest_candle['close']:.4f}, BBL={latest_candle['BBL']:.4f}, RSI={latest_candle['RSI']:.2f}")
                
                # For SELL signals, check if we have an open position and if current price is above entry price by profit target %
                position = self.trade_history.get_position(symbol)
                logger.info(f"DEBUG: Checking for {symbol} position: {position}")
                if position:
                    entry_price = position["entry_price"]
                    remaining_qty = position["quantity"]
                    tp_hits      = {hit["tier"] for hit in position.get("tp_hits", [])}

                    for tier in self.tp_tiers:
                        if tier["name"] in tp_hits:
                            continue                     # već odrađeno
                        target_price = entry_price * (1 + tier["pct"])
                        if latest_candle["close"] >= target_price:
                            df.loc[latest_idx, "signal"] = SignalType.SELL.value
                            df.loc[latest_idx, "sell_size_pct"] = tier["size"]
                            df.loc[latest_idx, "sell_tier"] = tier["name"]
                            break                         # samo jedan tier po svijeći
                
                # Count signals in the entire dataframe (for logging purposes)
            buy_count = (df['signal'] == SignalType.BUY.value).sum()
            sell_count = (df['signal'] == SignalType.SELL.value).sum()
            
                # Log how many signals are in the current dataframe and specifically for the latest candle
            latest_signal = df.iloc[-1]['signal']
            logger.info(f"Signal status for {symbol}: Latest candle signal = {latest_signal}")
            logger.info(f"Total signals in dataframe: {buy_count} BUY, {sell_count} SELL (mostly historical)")
            
            return df
            
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            df['signal'] = SignalType.NEUTRAL.value
            return df
    
    def check_for_signal(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[SignalType, Optional[float], Optional[pd.Series]]:
        """
        Check the most recent candle for a trading signal.
        
        Args:
            df: DataFrame with price data and indicators
            symbol: Trading pair symbol
            current_time: Current time (defaults to now)
            
        Returns:
            Tuple containing (signal_type, price, row_data)
        """
        try:
            # Debug info about the incoming dataframe
            logger.debug(f"DataFrame for {symbol} has columns: {df.columns.tolist()}")
            logger.debug(f"DataFrame shape: {df.shape}")
            
            # Check if 'close' column exists
            if 'close' not in df.columns:
                logger.error(f"Missing 'close' column in dataframe for {symbol}")
                return SignalType.NEUTRAL, None, None
            
            # Calculate indicators and generate signals
            df = self.calculate_indicators(df)
            
            # Debug info after calculating indicators
            logger.debug(f"After indicators, DataFrame for {symbol} has columns: {df.columns.tolist()}")
            
            # Check for required indicators before generating signals
            required_indicators = ['BBL', 'BBU', 'RSI']
            missing_indicators = [col for col in required_indicators if col not in df.columns]
            
            if missing_indicators:
                logger.error(f"Missing indicators for {symbol}: {missing_indicators}")
                return SignalType.NEUTRAL, None, None
            
            # Set current time if not provided
            if current_time is None:
                current_time = datetime.now()
            
            # Generate signals after ensuring all indicators are present
            df = self.generate_signals(df, symbol, current_time)
            
            # Get the last (most recent) row for price information
            last_row = df.iloc[-1]
            price = last_row.get('close')
            
            # Check the signal for the most recent candle only
            latest_signal = last_row.get('signal', SignalType.NEUTRAL.value)
            
            # Convert signal value to SignalType enum
            if latest_signal == SignalType.BUY.value:
                signal = SignalType.BUY
                logger.info(f"ACTIVE BUY signal found for {symbol} at price {price}")
            elif latest_signal == SignalType.SELL.value:
                signal = SignalType.SELL
                logger.info(f"ACTIVE SELL signal found for {symbol} at price {price}")
            else:
                signal = SignalType.NEUTRAL
                logger.info(f"No active trade signal for {symbol} at price {price}")
            
            logger.info(f"Final signal determined for {symbol}: {signal.name} at price {price}")
            
            # Update position and last trade time if a BUY signal is generated
            if signal == SignalType.BUY:
                self.last_trade_time[symbol] = current_time
                # Track entry price for this symbol
                self.positions[symbol] = {
                    'entry_price': price,
                    'entry_time': current_time
                }
                logger.info(f"Updated position tracking for {symbol} - Entry: {price} at {current_time}")
            
            # Update last trade time if a SELL signal is generated
            elif signal == SignalType.SELL:
                self.last_trade_time[symbol] = current_time
                # If we have position information, calculate profit
                if symbol in self.positions and 'entry_price' in self.positions[symbol]:
                    entry_price = self.positions[symbol]['entry_price']
                    profit_pct = (price / entry_price - 1) * 100
                    logger.info(f"Position closed for {symbol} - Entry: {entry_price}, Exit: {price}, Profit: {profit_pct:.2f}%")
                    # Clear position data after selling
                    self.positions.pop(symbol, None)
            
            return signal, price, last_row
            
        except Exception as e:
            logger.error(f"Error checking for signal: {e}")
            return SignalType.NEUTRAL, None, None
    
    def backtest(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with historical price data
            symbol: Trading pair symbol
            
        Returns:
            Tuple of (DataFrame with signals, metrics dictionary)
        """
        try:
            # Reset the last trade time for backtesting
            if symbol in self.last_trade_time:
                del self.last_trade_time[symbol]
            
            # Calculate indicators
            df = self.calculate_indicators(df)
            
            # Initialize columns for backtesting
            df['signal'] = SignalType.NEUTRAL.value
            df['position'] = 0
            df['entry_price'] = None
            
            # Process each row to generate signals and track positions
            for i in range(1, len(df)):
                current_row = df.iloc[i]
                previous_row = df.iloc[i-1]
                
                # Use row timestamp as current_time for cool-down tracking
                current_time = df.index[i]
                
                # Check for signals
                # Buy condition: price at or below lower band and RSI oversold
                if (current_row['close'] <= current_row['BBL'] and 
                    current_row['RSI'] < self.rsi_oversold):
                    
                    # Check cool-down period
                    last_trade = self.last_trade_time.get(symbol)
                    if not last_trade or (current_time - last_trade) >= timedelta(hours=self.cool_down_hours, minutes=self.cool_down_minutes):
                        df.at[df.index[i], 'signal'] = SignalType.BUY.value
                        self.last_trade_time[symbol] = current_time
                
                # Sell condition: price at or above upper band and RSI overbought
                elif (current_row['close'] >= current_row['BBU'] and 
                      current_row['RSI'] > self.rsi_overbought):
                    
                    # Check cool-down period
                    last_trade = self.last_trade_time.get(symbol)
                    if not last_trade or (current_time - last_trade) >= timedelta(hours=self.cool_down_hours, minutes=self.cool_down_minutes):
                        df.at[df.index[i], 'signal'] = SignalType.SELL.value
                        self.last_trade_time[symbol] = current_time
                
                # Position tracking logic (simplified)
                if df.at[df.index[i], 'signal'] == SignalType.BUY.value:
                    df.at[df.index[i], 'position'] = 1
                    df.at[df.index[i], 'entry_price'] = current_row['close']
                elif df.at[df.index[i], 'signal'] == SignalType.SELL.value:
                    df.at[df.index[i], 'position'] = -1
                    df.at[df.index[i], 'entry_price'] = current_row['close']
                else:
                    df.at[df.index[i], 'position'] = previous_row['position']
                    df.at[df.index[i], 'entry_price'] = previous_row['entry_price']
            
            # Calculate basic backtest metrics
            metrics = self._calculate_backtest_metrics(df)
            
            return df, metrics
            
        except Exception as e:
            logger.error(f"Error in backtest: {e}")
            return df, {}
    
    def _calculate_backtest_metrics(self, df: pd.DataFrame) -> Dict:
        """
        Calculate performance metrics from backtest results.
        
        Args:
            df: DataFrame with backtest results
            
        Returns:
            Dictionary with performance metrics
        """
        try:
            # Count signals
            buy_signals = (df['signal'] == SignalType.BUY.value).sum()
            sell_signals = (df['signal'] == SignalType.SELL.value).sum()
            
            # Basic metrics (more sophisticated metrics would be calculated in a real backtest)
            metrics = {
                'total_bars': len(df),
                'buy_signals': buy_signals,
                'sell_signals': sell_signals,
                'signal_ratio': (buy_signals + sell_signals) / len(df) if len(df) > 0 else 0,
                'first_date': df.index[0].strftime('%Y-%m-%d') if len(df) > 0 else None,
                'last_date': df.index[-1].strftime('%Y-%m-%d') if len(df) > 0 else None,
            }
            
            logger.info(f"Backtest metrics: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating backtest metrics: {e}")
            return {}
