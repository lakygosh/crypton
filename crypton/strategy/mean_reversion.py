"""
Mean reversion strategy implementation using Bollinger Bands and RSI.

This module implements the core trading strategy:
BUY  when close ≤ lower_band AND RSI < 30
SELL when close ≥ upper_band AND RSI > 70
"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from crypton.indicators.technical import IndicatorEngine


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
        self.take_profit_pct = self.config.get('risk', {}).get('take_profit_pct', 0.02)  # 2% profit target
        
        # Cool-down period for trades (to avoid overtrading)
        cool_down_value = self.config.get('cool_down', {}).get('hours', 4)
        # Support for time interval formats like '15m'
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
        
        # Track positions with entry prices
        self.positions: Dict[str, Dict] = {}
        
        logger.info("Mean reversion strategy initialized with parameters:")
        logger.info(f"  RSI oversold: {self.rsi_oversold}")
        logger.info(f"  RSI overbought: {self.rsi_overbought}")
        logger.info(f"  Take profit: {self.take_profit_pct * 100:.1f}%")
        if self.cool_down_minutes > 0:
            logger.info(f"  Cool-down period: {self.cool_down_minutes} minutes")
        else:
            logger.info(f"  Cool-down period: {self.cool_down_hours} hours")
    
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
        Generate trading signals based on the mean reversion strategy.
        
        Args:
            df: DataFrame with price data and indicators
            symbol: Trading pair symbol
            current_time: Current time (defaults to now)
            
        Returns:
            DataFrame with added 'signal' column
        """
        try:
            # Ensure dataframe has required columns
            required_columns = ['close', 'BBL', 'BBU', 'RSI']
            for col in required_columns:
                if col not in df.columns:
                    logger.error(f"Missing required column: {col}")
                    df['signal'] = SignalType.NEUTRAL.value
                    return df
            
            # Initialize signal column as NEUTRAL
            df['signal'] = SignalType.NEUTRAL.value
            
            # Current time defaults to now
            current_time = current_time or datetime.now()
            
            # Check if we're in the cool-down period
            last_trade = self.last_trade_time.get(symbol)
            in_cooldown = False
            
            if last_trade:
                time_since_last_trade = current_time - last_trade
                in_cooldown = time_since_last_trade < timedelta(hours=self.cool_down_hours, minutes=self.cool_down_minutes)
                if in_cooldown:
                    logger.info(f"{symbol} is in cool-down period. {time_since_last_trade.total_seconds() / 3600:.2f} hours since last trade.")
            
            if not in_cooldown:
                # Generate BUY signals - still use Bollinger Bands + RSI for entry
                df.loc[(df['close'] <= df['BBL']) & (df['RSI'] < self.rsi_oversold), 'signal'] = SignalType.BUY.value
                
                # For SELL signals, check if we have an open position and if current price is above entry price by profit target %
                position = self.positions.get(symbol, {})
                entry_price = position.get('entry_price')
                
                if entry_price:
                    # Calculate profit percentage
                    profit_threshold = entry_price * (1 + self.take_profit_pct)
                    
                    # Generate sell signals based on profit target
                    df.loc[df['close'] >= profit_threshold, 'signal'] = SignalType.SELL.value
                else:
                    # If no position, we're looking to enter, not exit
                    pass
            
            # Count signals
            buy_count = (df['signal'] == SignalType.BUY.value).sum()
            sell_count = (df['signal'] == SignalType.SELL.value).sum()
            
            logger.info(f"Generated signals for {symbol}: {buy_count} BUY, {sell_count} SELL")
            
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
            
            # Generate signals after ensuring all indicators are present
            df = self.generate_signals(df, symbol, current_time)
            
            # Get the last (most recent) row
            last_row = df.iloc[-1]
            signal_value = last_row.get('signal', SignalType.NEUTRAL.value)
            price = last_row.get('close')
            
            # Convert string signal to enum
            signal = SignalType(signal_value)
            
            # Update position and last trade time if a BUY signal is generated
            if signal == SignalType.BUY and current_time:
                self.last_trade_time[symbol] = current_time
                # Track entry price for this symbol
                self.positions[symbol] = {
                    'entry_price': price,
                    'entry_time': current_time
                }
                logger.info(f"Generated BUY signal for {symbol} at {price}")
            
            # Update last trade time if a SELL signal is generated
            elif signal == SignalType.SELL and current_time:
                self.last_trade_time[symbol] = current_time
                # If we have position information, calculate profit
                if symbol in self.positions and 'entry_price' in self.positions[symbol]:
                    entry_price = self.positions[symbol]['entry_price']
                    profit_pct = (price / entry_price - 1) * 100
                    logger.info(f"Generated SELL signal for {symbol} at {price}, profit: {profit_pct:.2f}%")
                    # Clear position data after selling
                    self.positions.pop(symbol, None)
                else:
                    logger.info(f"Generated SELL signal for {symbol} at {price}")
            
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
