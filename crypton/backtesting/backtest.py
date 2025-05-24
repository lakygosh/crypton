"""
Backtesting harness for the Crypton trading bot.

This module integrates with backtrader to provide comprehensive
backtesting capabilities for trading strategies.

This module integrates with backtrader to provide comprehensive
backtesting capabilities for trading strategies.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

# Helper za JSON serijalizaciju datetime objekata
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(obj)

import backtrader as bt
import pandas as pd
from loguru import logger

from crypton.strategy.mean_reversion import MeanReversionStrategy, SignalType
from crypton.utils.config import load_config
import json
import csv

class MeanReversionBT(bt.Strategy):
    """Backtrader implementation of Mean Reversion strategy."""
    
    params = (
        ('bb_length', 20),
        ('bb_std', 2.0),
        ('rsi_length', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('stop_loss_pct', 0.02),
        ('take_profit_pct', 0.04),
        ('position_size_pct', 0.01),
        ('cool_down_hours', 4) # Default cool-down period
    )
    
    def __init__(self):
        """Initialize indicators and variables for the strategy."""
        # Initialize indicators
        self.bband = bt.indicators.BollingerBands(
            self.datas[0], 
            period=self.params.bb_length, 
            devfactor=self.params.bb_std
        )
        self.rsi = bt.indicators.RelativeStrengthIndex(self.datas[0], period=self.params.rsi_length)
        self.order = None
        self.buy_price = None
        self.buy_comm = None
        self.last_trade_time = datetime.min
        self.trades = []  # To store individual trade P&L
        self.buy_signals = []
        self.sell_signals = []
        self.trade_event_logs = [] # For detailed logging of events

    def log(self, txt, dt=None):
        """Log strategy information with timestamp."""
        dt = dt or self.datas[0].datetime.datetime(0)
        log_message = f'{dt.isoformat()} {txt}'
        logger.info(log_message) # Keep console logging if desired
        self.trade_event_logs.append(log_message) # Store for file logging

    def notify_order(self, order):
        """Handle order status notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            # Order submitted/accepted - no action
            return
        
        # Check if order has been completed
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.6f}, Value: ${order.executed.value:.2f}, Comm: ${order.executed.comm:.2f}')
                # Update the current trade with actual execution price
                if hasattr(self, 'current_trade'):
                    self.current_trade['executed_entry_price'] = order.executed.price
                    self.current_trade['commission'] = order.executed.comm
            else:
                # Calculate the actual dollar amount received from the sale
                sell_value = order.executed.price * order.executed.size
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.6f}, Value: ${sell_value:.2f}, Comm: ${order.executed.comm:.2f}')
                # Add the completed trade to the list when the sell order is executed
                if hasattr(self, 'current_trade') and 'exit_time' in self.current_trade:
                    # Update with actual execution details
                    self.current_trade['executed_exit_price'] = order.executed.price
                    self.current_trade['exit_commission'] = order.executed.comm
                    
                    # Add to trades list only when the order is executed
                    self.trades.append(self.current_trade.copy())
                    
                    # Clear current trade to prevent duplicates
                    delattr(self, 'current_trade')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order.status}')
        
        # Reset order reference
        self.order = None
    
    def notify_trade(self, trade):
        """Handle trade completed notifications."""
        if not trade.isclosed:
            return
        
        self.log(f'TRADE COMPLETED, Gross: {trade.pnl:.2f}, Net: {trade.pnlcomm:.2f}')
        # Populate self.trades for P&L analysis
        # trade.value is the initial value of the position
        # trade.pnlcomm is the net profit/loss
        if trade.value != 0: # Avoid division by zero if position size was zero for some reason
            pnl_pct = (trade.pnlcomm / abs(trade.value)) * 100 # abs(trade.value) because value of short position is negative
            self.trades.append({'pnl_pct': pnl_pct, 'net_pnl': trade.pnlcomm})
        else:
            self.trades.append({'pnl_pct': 0, 'net_pnl': trade.pnlcomm})

    def next(self):
        """Strategy logic executed on each bar."""
        # Skip if in cool-down period
        current_time = self.datas[0].datetime.datetime(0)
        if self.params.cool_down_hours > 0 and self.last_trade_time != datetime.min:
            if (current_time - self.last_trade_time) < timedelta(hours=self.params.cool_down_hours):
                return
        
        # Check for buy signal
        if (self.data.close[0] <= self.bband.lines.bot[0] and 
            self.rsi[0] < self.params.rsi_oversold and 
            not self.position):
            
            # Calculate position size based on equity percentage
            size = self.broker.getcash() * self.params.position_size_pct / self.data.close[0]
            
            # Store detailed indicator values
            bb_upper = self.bband.lines.top[0]
            bb_middle = self.bband.lines.mid[0]
            bb_lower = self.bband.lines.bot[0]
            rsi_value = self.rsi[0]
            sma_value = self.data.close[0]
            
            # Place buy order
            self.log(f'BUY CREATE, Price: {self.data.close[0]:.2f}, Size: {size:.6f}, Value: ${self.data.close[0] * size:.2f}, RSI: {rsi_value:.2f}, BB Lower: {bb_lower:.2f}')
            self.order = self.buy(size=size)
            
            # Record signal with detailed data
            signal_data = {
                'time': current_time,
                'price': self.data.close[0],
                'action': 'BUY',
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'rsi': rsi_value,
                'sma': sma_value,
                'size': size
            }
            self.buy_signals.append(signal_data)
            
            # Start a new trade record
            self.current_trade = {
                'entry_time': current_time,
                'entry_price': self.data.close[0],
                'entry_indicators': {
                    'bb_upper': bb_upper,
                    'bb_middle': bb_middle,
                    'bb_lower': bb_lower,
                    'rsi': rsi_value,
                    'sma': sma_value
                },
                'size': size
            }
            
            # Update last trade time
            self.last_trade_time = current_time
        
        # If we have a position, check for take profit
        elif self.position:
            # Store current indicator values
            bb_upper = self.bband.lines.top[0]
            bb_middle = self.bband.lines.mid[0]
            bb_lower = self.bband.lines.bot[0]
            rsi_value = self.rsi[0]
            sma_value = self.data.close[0]
            
            # Check for take profit (sell when price increases by take_profit_pct)
            if self.data.close[0] > self.position.price * (1 + self.params.take_profit_pct):
                profit_pct = (self.data.close[0] / self.position.price - 1) * 100
                # Sell the entire position by specifying size
                position_size = self.position.size
                self.log(f'TAKE PROFIT, Price: {self.data.close[0]:.2f}, Size: {position_size:.6f}, Profit: {profit_pct:.2f}%, RSI: {rsi_value:.2f}')
                self.order = self.sell(size=position_size)
                
                # Record signal with detailed data
                signal_data = {
                    'time': current_time,
                    'price': self.data.close[0],
                    'action': 'SELL',
                    'reason': 'TAKE_PROFIT',
                    'profit_pct': profit_pct,
                    'bb_upper': bb_upper,
                    'bb_middle': bb_middle,
                    'bb_lower': bb_lower,
                    'rsi': rsi_value,
                    'sma': sma_value
                }
                self.sell_signals.append(signal_data)
                
                # Complete the trade record (first check if it was added previously to avoid duplicates)
                # We will mark the trade for completion, actual recording happens in notify_order
                if hasattr(self, 'current_trade') and 'exit_time' not in self.current_trade:
                    self.current_trade.update({
                        'exit_time': current_time,
                        'exit_price': self.data.close[0],
                        'exit_indicators': {
                            'bb_upper': bb_upper,
                            'bb_middle': bb_middle,
                            'bb_lower': bb_lower,
                            'rsi': rsi_value,
                            'sma': sma_value
                        },
                        'profit_pct': profit_pct,
                        'exit_reason': 'TAKE_PROFIT'
                    })
                    # We'll add the trade to the list when the order is actually executed
                
                # Update last trade time
                self.last_trade_time = current_time
            
            # Check for stop loss
            elif self.data.close[0] < self.position.price * (1 - self.params.stop_loss_pct):
                loss_pct = (1 - self.data.close[0] / self.position.price) * 100
                # Sell the entire position by specifying size
                position_size = self.position.size
                self.log(f'STOP LOSS, Price: {self.data.close[0]:.2f}, Size: {position_size:.6f}, Loss: {loss_pct:.2f}%, RSI: {rsi_value:.2f}')
                self.order = self.sell(size=position_size)
                
                # Record signal with detailed data
                signal_data = {
                    'time': current_time,
                    'price': self.data.close[0],
                    'action': 'SELL',
                    'reason': 'STOP_LOSS',
                    'loss_pct': loss_pct,
                    'bb_upper': bb_upper,
                    'bb_middle': bb_middle,
                    'bb_lower': bb_lower,
                    'rsi': rsi_value,
                    'sma': sma_value
                }
                self.sell_signals.append(signal_data)
                
                # Complete the trade record (first check if it was added previously to avoid duplicates)
                if hasattr(self, 'current_trade') and 'exit_time' not in self.current_trade:
                    self.current_trade.update({
                        'exit_time': current_time,
                        'exit_price': self.data.close[0],
                        'exit_indicators': {
                            'bb_upper': bb_upper,
                            'bb_middle': bb_middle,
                            'bb_lower': bb_lower,
                            'rsi': rsi_value,
                            'sma': sma_value
                        },
                        'loss_pct': loss_pct,
                        'exit_reason': 'STOP_LOSS'
                    })
                    # We'll add the trade to the list when the order is actually executed
                
                # Update last trade time
                self.last_trade_time = current_time


class MultiAssetMeanReversionBT(bt.Strategy):
    """Backtrader implementation of Mean Reversion strategy for multiple assets.
    
    This strategy manages positions across multiple symbols simultaneously,
    allocating capital according to a portfolio approach.
    """
    
    params = (
        ('bb_length', 20),
        ('bb_std', 2.0),
        ('rsi_length', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('stop_loss_pct', 0.02),
        ('take_profit_pct', 0.04),
        ('position_size_pct', 0.333),  # Default to 1/3 of equity per symbol
        ('cool_down_hours', 4) # Default cool-down period
    )
    
    def __init__(self):
        """Initialize indicators and variables for the strategy."""
        # Initialize dictionaries to track data for each symbol
        self.indicators = {}
        self.orders = {}
        self.position_info = {}  # Promenili smo ime iz positions u position_info
        self.last_trade_time = {}
        self.trade_logs = {}
        
        # Initialize trade tracking
        self.trades = []  # To store individual trade P&L
        self.buy_signals = []
        self.sell_signals = []
        self.trade_event_logs = [] # For detailed logging of events
        
        # Setup indicators for each data feed
        for i, data in enumerate(self.datas):
            # Get the name of the data feed (symbol)
            symbol = data._name if hasattr(data, '_name') else f'Data{i}'
            
            # Initialize indicators for this symbol
            self.indicators[symbol] = {
                'bband': bt.indicators.BollingerBands(
                    data, 
                    period=self.params.bb_length, 
                    devfactor=self.params.bb_std
                ),
                'rsi': bt.indicators.RelativeStrengthIndex(data, period=self.params.rsi_length)
            }
            
            # Initialize orders and positions tracking
            self.orders[symbol] = None
            self.position_info[symbol] = {
                'size': 0,
                'price': 0,
                'value': 0
            }
            
            # Initialize last trade time
            self.last_trade_time[symbol] = datetime.min
            
            # Initialize trade logs
            self.trade_logs[symbol] = {
                'current_trade': {},
                'buy_signals': [],
                'sell_signals': []
            }
    
    def log(self, txt, dt=None, symbol=None):
        """Log strategy information with timestamp and optional symbol."""
        dt = dt or self.datas[0].datetime.datetime(0)
        symbol_prefix = f"[{symbol}] " if symbol else ""
        log_message = f"{dt} {symbol_prefix}{txt}"
        
        # Log to console via the logger
        logger.info(log_message)
        
        # Add to trade events log if it's a trade-related message
        if any(keyword in txt for keyword in ['BUY', 'SELL', 'STOP LOSS', 'TAKE PROFIT', 'TRADE COMPLETED']):
            self.trade_event_logs.append(log_message)
        
        return log_message
    
    def notify_order(self, order):
        """Handle order status notifications."""
        # Get the data name (symbol)
        data = order.data
        symbol = data._name if hasattr(data, '_name') else 'Unknown'
        
        if order.status in [order.Submitted, order.Accepted]:
            return
            
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.6f}, Value: ${order.executed.value:.2f}, Comm: ${order.executed.comm:.2f}', symbol=symbol)
                
                # Update position tracking
                self.position_info[symbol]['size'] = order.executed.size
                self.position_info[symbol]['price'] = order.executed.price
                self.position_info[symbol]['value'] = order.executed.value
                
                # Update current trade record if it exists
                if self.trade_logs[symbol].get('current_trade', {}):
                    self.trade_logs[symbol]['current_trade']['executed_entry_price'] = order.executed.price
                    self.trade_logs[symbol]['current_trade']['executed_size'] = order.executed.size
                    self.trade_logs[symbol]['current_trade']['executed_value'] = order.executed.value
                    self.trade_logs[symbol]['current_trade']['commission'] = order.executed.comm
                
            else:  # sell order
                # Calculate the actual dollar amount received from the sale
                sell_value = order.executed.price * order.executed.size
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.6f}, Value: ${sell_value:.2f}, Comm: ${order.executed.comm:.2f}', symbol=symbol)
                
                # Reset position tracking
                self.position_info[symbol]['size'] = 0
                self.position_info[symbol]['price'] = 0
                self.position_info[symbol]['value'] = 0
                
                # Complete the trade record if it exists
                if self.trade_logs[symbol].get('current_trade', {}) and 'exit_time' in self.trade_logs[symbol]['current_trade']:
                    self.trade_logs[symbol]['current_trade']['executed_exit_price'] = order.executed.price
                    self.trade_logs[symbol]['current_trade']['executed_exit_value'] = sell_value
                    self.trade_logs[symbol]['current_trade']['exit_commission'] = order.executed.comm
                    
                    # Calculate realized P&L
                    entry_value = self.trade_logs[symbol]['current_trade'].get('executed_value', 0)
                    if entry_value > 0:
                        profit_pct = ((sell_value - entry_value) / entry_value) * 100
                        self.trade_logs[symbol]['current_trade']['realized_profit_pct'] = profit_pct
                    
                    # Add the completed trade to the overall trades list
                    self.trades.append(self.trade_logs[symbol]['current_trade'].copy())
                    
                    # Reset current trade
                    self.trade_logs[symbol]['current_trade'] = {}
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order.status}', symbol=symbol)
        
        # Store the order
        self.orders[symbol] = None
    
    def notify_trade(self, trade):
        """Handle trade completed notifications."""
        if not trade.isclosed:
            return
        
        # Get the data name (symbol)
        data = trade.data
        symbol = data._name if hasattr(data, '_name') else 'Unknown'
        
        self.log(f'TRADE COMPLETED, Gross: {trade.pnl:.2f}, Net: {trade.pnlcomm:.2f}', symbol=symbol)
        
        # Add trade P&L data
        if trade.value != 0:  # Avoid division by zero
            pnl_pct = (trade.pnlcomm / abs(trade.value)) * 100
            self.trades.append({
                'symbol': symbol,
                'pnl_pct': pnl_pct,
                'net_pnl': trade.pnlcomm,
                'entry_time': getattr(trade, 'entry_time', None),
                'exit_time': getattr(trade, 'exit_time', None)
            })
        else:
            self.trades.append({
                'symbol': symbol,
                'pnl_pct': 0,
                'net_pnl': trade.pnlcomm,
                'entry_time': getattr(trade, 'entry_time', None),
                'exit_time': getattr(trade, 'exit_time', None)
            })
    
    def next(self):
        """Strategy logic executed on each bar for all data feeds."""
        # Process each data feed (symbol)
        for i, data in enumerate(self.datas):
            # Get the symbol name
            symbol = data._name if hasattr(data, '_name') else f'Data{i}'
            
            # Skip if an order is pending
            if self.orders[symbol]:
                continue
                
            # Skip if in cool-down period
            current_time = data.datetime.datetime(0)
            if self.params.cool_down_hours > 0 and self.last_trade_time[symbol] != datetime.min:
                if (current_time - self.last_trade_time[symbol]) < timedelta(hours=self.params.cool_down_hours):
                    continue
            
            # Get indicators for this symbol
            bb = self.indicators[symbol]['bband']
            rsi = self.indicators[symbol]['rsi']
            
            # Check for buy signal
            if (data.close[0] <= bb.lines.bot[0] and 
                rsi[0] < self.params.rsi_oversold and 
                not self.getposition(data).size):  # Check if we don't have a position
                
                # Calculate position size based on equity percentage
                # The idea is to allocate a fixed percentage of the total equity to each symbol
                # Koristimo total portfolio value koji već uključuje i cash i vrednost svih pozicija
                equity = self.broker.getvalue()
                size = equity * self.params.position_size_pct / data.close[0]
                
                # Store detailed indicator values
                bb_upper = bb.lines.top[0]
                bb_middle = bb.lines.mid[0]
                bb_lower = bb.lines.bot[0]
                rsi_value = rsi[0]
                
                # Log buy signal
                self.log(f'BUY CREATE, Price: {data.close[0]:.2f}, Size: {size:.6f}, Value: ${data.close[0] * size:.2f}, RSI: {rsi_value:.2f}, BB Lower: {bb_lower:.2f}', symbol=symbol)
                
                # Create buy order
                self.orders[symbol] = self.buy(data=data, size=size)
                
                # Record signal data
                signal_data = {
                    'time': current_time,
                    'price': data.close[0],
                    'action': 'BUY',
                    'bb_upper': bb_upper,
                    'bb_middle': bb_middle,
                    'bb_lower': bb_lower,
                    'rsi': rsi_value,
                    'size': size
                }
                self.buy_signals.append(signal_data)
                self.trade_logs[symbol]['buy_signals'].append(signal_data)
                
                # Start a new trade record
                self.trade_logs[symbol]['current_trade'] = {
                    'symbol': symbol,
                    'entry_time': current_time,
                    'entry_price': data.close[0],
                    'entry_indicators': {
                        'bb_upper': bb_upper,
                        'bb_middle': bb_middle,
                        'bb_lower': bb_lower,
                        'rsi': rsi_value
                    },
                    'size': size
                }
                
                # Update last trade time
                self.last_trade_time[symbol] = current_time
            
            # Check for sell signals if we have a position
            elif self.getposition(data).size > 0:  # We have a position in this symbol
                position = self.getposition(data)
                bb_upper = bb.lines.top[0]
                bb_middle = bb.lines.mid[0]
                bb_lower = bb.lines.bot[0]
                rsi_value = rsi[0]
                
                # Take profit condition
                if data.close[0] > position.price * (1 + self.params.take_profit_pct):
                    profit_pct = (data.close[0] / position.price - 1) * 100
                    
                    # Log take profit signal
                    self.log(f'TAKE PROFIT, Price: {data.close[0]:.2f}, Size: {position.size:.6f}, Profit: {profit_pct:.2f}%, RSI: {rsi_value:.2f}', symbol=symbol)
                    
                    # Create sell order
                    self.orders[symbol] = self.sell(data=data, size=position.size)
                    
                    # Record signal data
                    signal_data = {
                        'time': current_time,
                        'price': data.close[0],
                        'action': 'SELL',
                        'reason': 'TAKE_PROFIT',
                        'profit_pct': profit_pct,
                        'bb_upper': bb_upper,
                        'bb_middle': bb_middle,
                        'bb_lower': bb_lower,
                        'rsi': rsi_value
                    }
                    self.sell_signals.append(signal_data)
                    self.trade_logs[symbol]['sell_signals'].append(signal_data)
                    
                    # Complete the trade record
                    if 'exit_time' not in self.trade_logs[symbol]['current_trade']:
                        self.trade_logs[symbol]['current_trade'].update({
                            'exit_time': current_time,
                            'exit_price': data.close[0],
                            'exit_indicators': {
                                'bb_upper': bb_upper,
                                'bb_middle': bb_middle,
                                'bb_lower': bb_lower,
                                'rsi': rsi_value
                            },
                            'profit_pct': profit_pct,
                            'exit_reason': 'TAKE_PROFIT'
                        })
                    
                    # Update last trade time
                    self.last_trade_time[symbol] = current_time
                
                # Stop loss condition
                elif data.close[0] < position.price * (1 - self.params.stop_loss_pct):
                    loss_pct = (1 - data.close[0] / position.price) * 100
                    
                    # Log stop loss signal
                    self.log(f'STOP LOSS, Price: {data.close[0]:.2f}, Size: {position.size:.6f}, Loss: {loss_pct:.2f}%, RSI: {rsi_value:.2f}', symbol=symbol)
                    
                    # Create sell order
                    self.orders[symbol] = self.sell(data=data, size=position.size)
                    
                    # Record signal data
                    signal_data = {
                        'time': current_time,
                        'price': data.close[0],
                        'action': 'SELL',
                        'reason': 'STOP_LOSS',
                        'loss_pct': loss_pct,
                        'bb_upper': bb_upper,
                        'bb_middle': bb_middle,
                        'bb_lower': bb_lower,
                        'rsi': rsi_value
                    }
                    self.sell_signals.append(signal_data)
                    self.trade_logs[symbol]['sell_signals'].append(signal_data)
                    
                    # Complete the trade record
                    if 'exit_time' not in self.trade_logs[symbol]['current_trade']:
                        self.trade_logs[symbol]['current_trade'].update({
                            'exit_time': current_time,
                            'exit_price': data.close[0],
                            'exit_indicators': {
                                'bb_upper': bb_upper,
                                'bb_middle': bb_middle,
                                'bb_lower': bb_lower,
                                'rsi': rsi_value
                            },
                            'loss_pct': loss_pct,
                            'exit_reason': 'STOP_LOSS'
                        })
                    
                    # Update last trade time
                    self.last_trade_time[symbol] = current_time


class BacktestHarness:
    """
    Harness for running and analyzing backtrader backtests.
    
    Provides functionality to load historical data, run backtests,
    and generate performance reports.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the backtest harness with configuration.
        
        Args:
            config: Dictionary containing configuration settings
        """
        self.config = config
        self.bb_config = config.get('bb', {})
        self.rsi_config = config.get('rsi', {})
        self.risk_config = config.get('risk', {})
        self.cool_down = config.get('cool_down', {})
        
        # Define paths for logging
        self.performances_dir = "performances"
        self.json_logs_dir = os.path.join(self.performances_dir, "detailed_logs")
        self.csv_log_path = os.path.join(self.performances_dir, "backtest_summary.csv")

        # Create directories if they don't exist
        os.makedirs(self.performances_dir, exist_ok=True)
        os.makedirs(self.json_logs_dir, exist_ok=True)

    def prepare_data(
        self, 
        df: pd.DataFrame,
        datetime_col: str = 'timestamp'
    ) -> bt.feeds.PandasData:
        """
        Prepare pandas DataFrame for backtrader.
        
        Args:
            df: DataFrame with OHLCV data
            datetime_col: Column name for datetime
            
        Returns:
            Backtrader data feed
        """
        # Reset index if datetime is in the index
        if df.index.name == datetime_col:
            df = df.reset_index()
        
        # Make sure required columns exist and are named correctly
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return None
        
        # Create backtrader data feed
        data = bt.feeds.PandasData(
            dataname=df,
            datetime=df.columns.get_loc(datetime_col),
            open=df.columns.get_loc('open'),
            high=df.columns.get_loc('high'),
            low=df.columns.get_loc('low'),
            close=df.columns.get_loc('close'),
            volume=df.columns.get_loc('volume'),
            openinterest=-1
        )
        
        return data
    
    def run_backtest(
        self, 
        symbol: str, # Added symbol
        interval: str, # Added interval
        data: Union[pd.DataFrame, bt.feeds.PandasData],
        initial_cash: float = 10000.0,
        commission: float = 0.001  # 0.1% taker fee
    ) -> Tuple[bt.Strategy, Dict]:
        """
        Run backtest with mean reversion strategy.
        
        Args:
            symbol: Symbol of the asset
            interval: Interval of the data
            data: DataFrame with OHLCV data or backtrader data feed
            initial_cash: Initial account balance
            commission: Commission rate
            
        Returns:
            Tuple of (strategy instance, metrics dictionary)
        """
        # Create cerebro instance
        cerebro = bt.Cerebro()
        
        # Add data
        if isinstance(data, pd.DataFrame):
            data_feed = self.prepare_data(data)
            if data_feed is None:
                logger.error(f"Failed to prepare data for backtesting {symbol} {interval}")
                return None, {}
            cerebro.adddata(data_feed)
        else:
            cerebro.adddata(data)
        
        # Set strategy parameters
        strategy_params = {
            'bb_length': self.bb_config.get('length', 20),
            'bb_std': self.bb_config.get('std', 2.0),
            'rsi_length': self.rsi_config.get('length', 14),
            'rsi_oversold': self.rsi_config.get('oversold', 30),
            'rsi_overbought': self.rsi_config.get('overbought', 70),
            'stop_loss_pct': self.risk_config.get('stop_loss_pct', 0.02),
            'take_profit_pct': self.risk_config.get('take_profit_pct', 0.04),
            'position_size_pct': self.risk_config.get('position_size_pct', 0.01),
            'cool_down_hours': self.cool_down.get('hours', 4)
        }
        
        # Add strategy
        cerebro.addstrategy(MeanReversionBT, **strategy_params)
        
        # Set broker parameters
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        
        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Run backtest
        logger.info(f"Starting backtest for {symbol} ({interval}) with params: {strategy_params}...")
        results = cerebro.run()
        strategy = results[0]
        
        # Calculate metrics
        summary_metrics = self._calculate_metrics(strategy, initial_cash)
        
        logger.info(f"Backtest for {symbol} ({interval}) completed. Final portfolio value: ${cerebro.broker.getvalue():.2f}")
        logger.info(f"Metrics for {symbol} ({interval}): {summary_metrics}")

        # --- Logging to files ---
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # Sanitize symbol for filename
        safe_symbol = symbol.replace("/", "_") 
        json_filename = f"backtest_{safe_symbol}_{interval}_{run_timestamp}.json"
        json_filepath = os.path.join(self.json_logs_dir, json_filename)

        input_parameters_log = {
            "symbol": symbol,
            "interval": interval,
            "initial_cash": initial_cash,
            "commission": commission,
            **strategy_params
        }

        log_data_for_json = {
            "run_timestamp": run_timestamp,
            "input_parameters": input_parameters_log,
            "detailed_trade_events": strategy.trade_event_logs if hasattr(strategy, 'trade_event_logs') else [],
            "summary_metrics": summary_metrics
        }

        try:
            with open(json_filepath, 'w') as f_json:
                json.dump(log_data_for_json, f_json, indent=4)
            logger.info(f"Detailed log saved to {json_filepath}")
        except Exception as e:
            logger.error(f"Failed to save JSON log to {json_filepath}: {e}")

        # Prepare data for CSV
        csv_row = {**input_parameters_log, **summary_metrics}
        # Flatten any nested dicts in metrics for CSV, e.g. if Sharpe was a dict
        # For now, _calculate_metrics returns a flat dict, so this might not be strictly needed
        # but good practice if metrics structure changes.
        flat_csv_row = {}
        for k, v in csv_row.items():
            if isinstance(v, dict):
                for nk, nv in v.items():
                    flat_csv_row[f"{k}_{nk}"] = nv
            else:
                flat_csv_row[k] = v
        
        try:
            file_exists = os.path.isfile(self.csv_log_path)
            with open(self.csv_log_path, 'a', newline='') as f_csv:
                writer = csv.DictWriter(f_csv, fieldnames=sorted(flat_csv_row.keys())) # Sort keys for consistent order
                if not file_exists or os.path.getsize(self.csv_log_path) == 0:
                    writer.writeheader()
                writer.writerow(flat_csv_row)
            logger.info(f"Summary appended to {self.csv_log_path}")
        except Exception as e:
            logger.error(f"Failed to append to CSV log {self.csv_log_path}: {e}")
        # --- End Logging to files ---
        
        return strategy, summary_metrics

    def _calculate_metrics(self, strategy: bt.Strategy, initial_cash: float) -> Dict:
        """
        Calculate performance metrics from backtest results.
        
        Args:
            strategy: Backtrader strategy instance
            initial_cash: Initial account balance
            
        Returns:
            Dictionary with performance metrics
        """
        try:
            # Get analyzer results with error handling
            analyzers = strategy.analyzers
            sharpe_analysis = analyzers.sharpe.get_analysis() if hasattr(analyzers, 'sharpe') else {}
            # returns_analysis = analyzers.returns.get_analysis() if hasattr(analyzers, 'returns') else {}
            drawdown_analysis = analyzers.drawdown.get_analysis() if hasattr(analyzers, 'drawdown') else {}
            trade_analysis = analyzers.trades.get_analysis() if hasattr(analyzers, 'trades') else {}
            
            # Calculate portfolio value and return
            final_value = strategy.broker.getvalue()
            total_return_pct = (final_value / initial_cash - 1) * 100 if initial_cash != 0 else 0.0
            
            # Extract trade metrics from TradeAnalyzer
            total_trades = trade_analysis.get('total', {}).get('total', 0)
            wins = trade_analysis.get('won', {}).get('total', 0)
            losses = trade_analysis.get('lost', {}).get('total', 0)
            win_rate_pct = (wins / total_trades * 100) if total_trades > 0 else 0.0
            
            sharpe_ratio = sharpe_analysis.get('sharperatio', None)
            # Ensure sharpe_ratio is a float or None
            if sharpe_ratio is not None:
                try:
                    sharpe_ratio = float(sharpe_ratio)
                except (ValueError, TypeError):
                    sharpe_ratio = None # Set to None if conversion fails
            
            max_drawdown_pct = drawdown_analysis.get('max', {}).get('drawdown', 0.0)
            max_drawdown_pct = float(max_drawdown_pct) # Already a percentage from analyzer
            
            # Calculate metrics based on self.trades populated by notify_trade
            strategy_trades_list = getattr(strategy, 'trades', [])
            trade_based_pnl_pct_sum = 0.0
            winning_strategy_trades = 0
            losing_strategy_trades = 0

            if strategy_trades_list:
                for t_info in strategy_trades_list:
                    pnl_pct = t_info.get('pnl_pct', 0.0)
                    trade_based_pnl_pct_sum += pnl_pct
                    if t_info.get('net_pnl', 0.0) > 0:
                        winning_strategy_trades += 1
                    elif t_info.get('net_pnl', 0.0) < 0:
                        losing_strategy_trades += 1
                
                avg_trade_pnl_pct = trade_based_pnl_pct_sum / len(strategy_trades_list)
            else:
                avg_trade_pnl_pct = 0.0

            # Win rate from strategy.trades can be a cross-check but primary is TradeAnalyzer
            # total_strategy_trades = len(strategy_trades_list)
            # win_rate_from_strategy_trades_pct = (winning_strategy_trades / total_strategy_trades * 100) if total_strategy_trades > 0 else 0.0
            
            metrics = {
                'initial_cash': float(initial_cash),
                'final_value': float(final_value),
                'total_return_pct': total_return_pct,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown_pct': max_drawdown_pct, # This is already in % from analyzer
                
                # Metrics from TradeAnalyzer
                'total_trades_analyzer': total_trades,
                'win_rate_analyzer_pct': win_rate_pct,
                'wins_analyzer': wins,
                'losses_analyzer': losses,
                
                # Metrics from strategy.trades (for detailed P&L per trade)
                'avg_trade_pnl_pct_strat': avg_trade_pnl_pct, # Average P&L % per trade from strategy.trades
                'sum_pnl_pct_strat': trade_based_pnl_pct_sum, # Sum of P&L % from strategy.trades
                'total_trades_strat': len(strategy_trades_list),
                'winning_trades_strat': winning_strategy_trades,
                'losing_trades_strat': losing_strategy_trades,
                
                # Signal counts (can be useful for debugging strategy logic)
                'buy_signals': len(getattr(strategy, 'buy_signals', [])),
                'sell_signals': len(getattr(strategy, 'sell_signals', [])),
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}", exc_info=True)
            # Return default metrics in case of error
            return {
                'initial_cash': float(initial_cash),
                'final_value': float(initial_cash), # Or strategy.broker.getvalue() if available
                'total_return_pct': 0.0,
                'sharpe_ratio': None,
                'max_drawdown_pct': 0.0,
                'total_trades_analyzer': 0,
                'win_rate_analyzer_pct': 0.0,
                'wins_analyzer': 0,
                'losses_analyzer': 0,
                'avg_trade_pnl_pct_strat': 0.0,
                'sum_pnl_pct_strat': 0.0,
                'total_trades_strat': 0,
                'winning_trades_strat': 0,
                'losing_trades_strat': 0,
                'buy_signals': 0,
                'sell_signals': 0,
            }
        
        return metrics
    
    def run_portfolio_backtest(
        self,
        symbol_data_dict: Dict[str, Union[pd.DataFrame, bt.feeds.PandasData]],
        initial_cash: float = 1000.0,
        commission: float = 0.001
    ) -> Tuple[bt.Strategy, Dict]:
        """
        Run backtest with multiple symbols as a portfolio.
        
        Args:
            symbol_data_dict: Dictionary mapping symbols to their data (DataFrame or bt.feeds.PandasData)
            initial_cash: Initial account balance for entire portfolio
            commission: Commission rate
            
        Returns:
            Tuple of (strategy instance, metrics dictionary)
        """
        # Create cerebro instance
        cerebro = bt.Cerebro()
        
        # Add data for each symbol
        for symbol, data in symbol_data_dict.items():
            if isinstance(data, pd.DataFrame):
                data_feed = self.prepare_data(data)
                if data_feed is None:
                    logger.error(f"Failed to prepare data for {symbol}")
                    continue
                cerebro.adddata(data_feed, name=symbol)
            else:
                cerebro.adddata(data, name=symbol)
        
        # Set strategy parameters
        strategy_params = {
            'bb_length': self.bb_config.get('length', 20),
            'bb_std': self.bb_config.get('std', 2.0),
            'rsi_length': self.rsi_config.get('length', 14),
            'rsi_oversold': self.rsi_config.get('oversold', 30),
            'rsi_overbought': self.rsi_config.get('overbought', 70),
            'stop_loss_pct': self.risk_config.get('stop_loss_pct', 0.02),
            'take_profit_pct': self.risk_config.get('take_profit_pct', 0.04),
            'position_size_pct': self.risk_config.get('position_size_pct', 0.333),  # Use from config
            'cool_down_hours': self.cool_down.get('hours', 4)
        }
        
        # Add multi-asset strategy
        cerebro.addstrategy(MultiAssetMeanReversionBT, **strategy_params)
        
        # Set broker parameters
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=commission)
        
        # Add analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Run backtest
        logger.info(f"Starting portfolio backtest with {len(symbol_data_dict)} symbols...")
        results = cerebro.run()
        strategy = results[0]
        
        # Calculate metrics
        metrics = self._calculate_metrics(strategy, initial_cash)
        
        final_value = cerebro.broker.getvalue()
        logger.info(f"Portfolio backtest completed. Final portfolio value: ${final_value:.2f}")
        logger.info(f"Portfolio metrics: {metrics}")

        # --- Logging to files ---
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        json_filename = f"portfolio_backtest_{run_timestamp}.json"
        json_filepath = os.path.join(self.json_logs_dir, json_filename)

        # Create portfolio input parameters log
        symbols_str = ",".join(symbol_data_dict.keys())
        input_parameters_log = {
            "symbols": symbols_str,
            "initial_cash": initial_cash,
            "commission": commission,
            **strategy_params
        }

        # Get trade events by symbol
        trade_events_by_symbol = {}
        for event in strategy.trade_event_logs:
            for symbol in symbol_data_dict.keys():
                if f"[{symbol}]" in event:
                    if symbol not in trade_events_by_symbol:
                        trade_events_by_symbol[symbol] = []
                    trade_events_by_symbol[symbol].append(event)
        
        # Get all trades with symbol information
        trades_with_symbols = []
        for trade in getattr(strategy, 'trades', []):
            if isinstance(trade, dict) and 'symbol' in trade:
                trades_with_symbols.append(trade)

        log_data_for_json = {
            "run_timestamp": run_timestamp,
            "input_parameters": input_parameters_log,
            "detailed_trade_events_by_symbol": trade_events_by_symbol,
            "trades": trades_with_symbols,
            "summary_metrics": metrics
        }

        try:
            with open(json_filepath, 'w') as f_json:
                json.dump(log_data_for_json, f_json, indent=4, cls=DateTimeEncoder)
            logger.info(f"Detailed portfolio log saved to {json_filepath}")
        except Exception as e:
            logger.error(f"Failed to save portfolio JSON log: {e}")

        # Prepare data for CSV
        csv_row = {**input_parameters_log, **metrics}
        flat_csv_row = {}
        for k, v in csv_row.items():
            if isinstance(v, dict):
                for nk, nv in v.items():
                    flat_csv_row[f"{k}_{nk}"] = nv
            else:
                flat_csv_row[k] = v
        
        # Add portfolio_ prefix to CSV filename
        portfolio_csv_path = os.path.join(self.performances_dir, "portfolio_backtest_summary.csv")
        try:
            file_exists = os.path.isfile(portfolio_csv_path)
            with open(portfolio_csv_path, 'a', newline='') as f_csv:
                import csv
                writer = csv.DictWriter(f_csv, fieldnames=list(flat_csv_row.keys()))
                if not file_exists:
                    writer.writeheader()
                writer.writerow(flat_csv_row)
            logger.info(f"Portfolio summary appended to {portfolio_csv_path}")
        except Exception as e:
            logger.error(f"Failed to save portfolio CSV log: {e}")
        
        # Generate HTML report
        report_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            f"portfolio_backtest_report_{run_timestamp}.html"
        )
        self.generate_portfolio_report(strategy, metrics, symbol_data_dict.keys(), report_path)
        
        return strategy, metrics

    def generate_portfolio_report(
        self, 
        strategy: bt.Strategy, 
        metrics: Dict,
        symbols: List[str],
        report_path: Optional[str] = None
    ) -> str:
        """
        Generate HTML report for portfolio backtest results.
        
        Args:
            strategy: Backtrader strategy instance
            metrics: Metrics dictionary
            symbols: List of symbols in the portfolio
            report_path: Path to save the report (optional)
            
        Returns:
            Path to the generated report
        """
        # Create HTML content
        title = f"Portfolio Backtest Report - {', '.join(symbols)}"
        
        # Prepare the HTML template - similar to generate_report but adapted for portfolio
        total_return_class = 'positive' if metrics['total_return_pct'] > 0 else 'negative'
        total_return_sign = '+' if metrics['total_return_pct'] > 0 else ''
        
        # Bezbedna provera za Sharpe Ratio - pošto može biti None
        sharpe_ratio = metrics.get('sharpe_ratio')
        sharpe_class = ''
        if sharpe_ratio is not None:
            sharpe_class = 'positive' if sharpe_ratio > 1 else 'negative' if sharpe_ratio < 0.5 else ''
        
        drawdown_class = 'positive' if metrics['max_drawdown_pct'] < 10 else 'negative' if metrics['max_drawdown_pct'] > 20 else ''
        
        win_rate_class = 'positive' if metrics['win_rate_analyzer_pct'] > 50 else 'negative' if metrics['win_rate_analyzer_pct'] < 40 else ''
        
        avg_return_class = 'positive' if metrics['avg_trade_pnl_pct_strat'] > 0 else 'negative'
        avg_return_sign = '+' if metrics['avg_trade_pnl_pct_strat'] > 0 else ''

        # Create HTML report
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f7f7f7;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 5px 5px 0 0;
        }}
        .metrics-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 20px;
        }}
        .metric-card {{
            background-color: white;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            padding: 20px;
            flex: 1;
            min-width: 250px;
        }}
        .metric-title {{
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 15px;
            color: #2c3e50;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }}
        .metric-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }}
        .metric-label {{
            color: #7f8c8d;
        }}
        .metric-value {{
            font-weight: bold;
        }}
        .positive {{
            color: #27ae60;
        }}
        .negative {{
            color: #e74c3c;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background-color: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            border-radius: 5px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background-color: #f5f5f5;
            font-weight: bold;
            color: #2c3e50;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .parameters {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }}
        .parameter {{
            background-color: #eee;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            display: flex;
            align-items: center;
        }}
        .parameter-name {{
            font-weight: bold;
            margin-right: 5px;
        }}
        .summary-title {{
            margin-top: 30px;
            font-size: 1.5em;
            color: #2c3e50;
        }}
        .symbols-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}
        .symbol-tag {{
            background-color: #3498db;
            color: white;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>
        
        <div class="summary-title">Portfolio Symbols</div>
        <div class="symbols-list">
            {' '.join([f'<span class="symbol-tag">{symbol}</span>' for symbol in symbols])}
        </div>

        <div class="summary-title">Strategy Parameters</div>
        <div class="parameters">
            <div class="parameter"><span class="parameter-name">Initial Cash:</span> ${metrics['initial_cash']:.2f}</div>
            <div class="parameter"><span class="parameter-name">Position Size:</span> {strategy.params.position_size_pct * 100:.0f}%</div>
            <div class="parameter"><span class="parameter-name">BB Length:</span> {strategy.params.bb_length}</div>
            <div class="parameter"><span class="parameter-name">BB Std:</span> {strategy.params.bb_std}</div>
            <div class="parameter"><span class="parameter-name">RSI Length:</span> {strategy.params.rsi_length}</div>
            <div class="parameter"><span class="parameter-name">RSI Oversold:</span> {strategy.params.rsi_oversold}</div>
            <div class="parameter"><span class="parameter-name">Stop Loss:</span> {strategy.params.stop_loss_pct * 100:.1f}%</div>
            <div class="parameter"><span class="parameter-name">Take Profit:</span> {strategy.params.take_profit_pct * 100:.1f}%</div>
        </div>
        
        <div class="summary-title">Performance Summary</div>
        <div class="metrics-container">
            <div class="metric-card">
                <div class="metric-title">Portfolio Performance</div>
                <div class="metric-item">
                    <span class="metric-label">Initial Cash</span>
                    <span class="metric-value">${metrics['initial_cash']:.2f}</span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Final Value</span>
                    <span class="metric-value">${metrics['final_value']:.2f}</span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Total Return</span>
                    <span class="metric-value {total_return_class}">{total_return_sign}{abs(metrics['total_return_pct']):.2f}%</span>
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Risk Metrics</div>
                <div class="metric-item">
                    <span class="metric-label">Sharpe Ratio</span>
                    <span class="metric-value {sharpe_class}">{metrics['sharpe_ratio'] if metrics['sharpe_ratio'] is not None else 'N/A'}</span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Max Drawdown</span>
                    <span class="metric-value {drawdown_class}">{metrics['max_drawdown_pct']:.2f}%</span>
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Trade Statistics</div>
                <div class="metric-item">
                    <span class="metric-label">Total Trades</span>
                    <span class="metric-value">{metrics['total_trades_analyzer']}</span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Win Rate</span>
                    <span class="metric-value {win_rate_class}">{metrics['win_rate_analyzer_pct']:.1f}%</span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Avg Trade Return</span>
                    <span class="metric-value {avg_return_class}">{avg_return_sign}{abs(metrics['avg_trade_pnl_pct_strat']):.2f}%</span>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

        # Save the report
        if report_path is None:
            report_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                f"portfolio_backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Generated portfolio backtest report: {report_path}")
        return report_path

    def generate_report(
        self, 
        strategy: bt.Strategy, 
        metrics: Dict,
        report_path: Optional[str] = None
    ) -> str:
        """
        Generate HTML report for backtest results.
        
        Args:
            strategy: Backtrader strategy instance
            metrics: Metrics dictionary
            report_path: Path to save the report (optional)
            
        Returns:
            Path to the generated report
        """
        # If no path specified, save to current directory
        if not report_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(
                os.getcwd(), 
                f"backtest_report_{timestamp}.html"
            )
        
        # Ensure metrics is a dictionary
        if not isinstance(metrics, dict):
            logger.warning("Metrics is not a dictionary, creating default metrics")
            metrics = {
                'initial_cash': 0.0,
                'final_value': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown_pct': 0.0,
                'total_trades_analyzer': 0,
                'win_rate_analyzer_pct': 0.0,
                'wins_analyzer': 0,
                'losses_analyzer': 0,
                'avg_trade_pnl_pct_strat': 0.0,
                'sum_pnl_pct_strat': 0.0,
                'total_trades_strat': 0,
                'winning_trades_strat': 0,
                'losing_trades_strat': 0,
                'buy_signals': 0,
                'sell_signals': 0,
            }
        
        # Ensure all required keys exist in metrics
        default_metrics = {
            'initial_cash': 0.0,
            'final_value': 0.0,
            'total_return_pct': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown_pct': 0.0,
            'total_trades_analyzer': 0,
            'win_rate_analyzer_pct': 0.0,
            'wins_analyzer': 0,
            'losses_analyzer': 0,
            'avg_trade_pnl_pct_strat': 0.0,
            'sum_pnl_pct_strat': 0.0,
            'total_trades_strat': 0,
            'winning_trades_strat': 0,
            'losing_trades_strat': 0,
            'buy_signals': 0,
            'sell_signals': 0,
        }
        
        # Update default metrics with actual values
        for key in default_metrics:
            if key not in metrics or metrics[key] is None:
                metrics[key] = default_metrics[key]
        
        # Generate trade rows
        trade_rows = self._generate_trade_rows(strategy)
        
        # Determine CSS classes based on metrics
        total_return_class = 'positive' if metrics['total_return_pct'] >= 0 else 'negative'
        total_return_sign = '+' if metrics['total_return_pct'] >= 0 else ''
        
        sharpe_class = 'positive' if metrics['sharpe_ratio'] >= 1 else 'negative' if metrics['sharpe_ratio'] < 0.5 else ''
        sharpe_sign = '+' if metrics['sharpe_ratio'] > 0 else ''
        
        drawdown_class = 'positive' if metrics['max_drawdown_pct'] < 10 else 'negative' if metrics['max_drawdown_pct'] > 20 else ''
        
        win_rate_class = 'positive' if metrics['win_rate_analyzer_pct'] > 50 else 'negative' if metrics['win_rate_analyzer_pct'] < 40 else ''
        
        avg_return_class = 'positive' if metrics['avg_trade_pnl_pct_strat'] > 0 else 'negative'
        avg_return_sign = '+' if metrics['avg_trade_pnl_pct_strat'] > 0 else ''

        # Create HTML report
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Crypton Backtest Report</title>
    <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            line-height: 1.6;
            color: #333;
        }}
        h1, h2, h3 {{ 
            color: #2c3e50;
            margin-top: 1.5em;
        }}
        h1 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        h2 {{ border-bottom: 1px solid #f0f0f0; padding-bottom: 5px; }}
        table {{ 
            border-collapse: collapse; 
            width: 100%; 
            margin: 15px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{ 
            text-align: left; 
            padding: 10px 12px; 
            border: 1px solid #e0e0e0; 
        }}
        th {{ 
            background-color: #f5f7fa;
            font-weight: 600;
            color: #2c3e50;
        }}
        tr:nth-child(even) {{ background-color: #f9fafc; }}
        tr:hover {{ background-color: #f0f4f8; }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #fff;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #e0e6ed;
        }}
        .metric-title {{
            font-size: 1.1em;
            font-weight: 600;
            margin: 0 0 15px 0;
            color: #2c3e50;
            border-bottom: 1px solid #eaeff5;
            padding-bottom: 8px;
        }}
        .metric-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            padding: 8px 0;
            border-bottom: 1px solid #f5f7fa;
        }}
        .metric-item:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        .metric-label {{
            color: #7f8c8d;
            font-size: 0.92em;
        }}
        .metric-value {{
            font-weight: 500;
            font-size: 0.95em;
        }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        .neutral {{ color: #7f8c8d; }}
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .text-muted {{ color: #95a5a6; }}
    </style>
</head>
<body>
    <h1>Crypton Backtest Report</h1>
    <p class="text-muted">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <h2>Performance Summary</h2>
    <div class="metric-grid">
        <div class="metric-card">
            <div class="metric-title">📊 Portfolio</div>
            <div class="metric-item">
                <span class="metric-label">Initial Capital</span>
                <span class="metric-value">${metrics['initial_cash']:,.2f}</span>
            </div>
            <div class="metric-item">
                <span class="metric-label">Final Value</span>
                <span class="metric-value">${metrics['final_value']:,.2f}</span>
            </div>
            <div class="metric-item">
                <span class="metric-label">Total Return</span>
                <span class="metric-value {total_return_class}">{total_return_sign}{abs(metrics['total_return_pct']):.2f}%</span>
            </div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">📈 Risk & Performance</div>
            <div class="metric-item">
                <span class="metric-label">Sharpe Ratio</span>
                <span class="metric-value {sharpe_class}">{sharpe_sign}{metrics['sharpe_ratio']:.2f}</span>
            </div>
            <div class="metric-item">
                <span class="metric-label">Max Drawdown</span>
                <span class="metric-value {drawdown_class}">{metrics['max_drawdown_pct']:.2f}%</span>
            </div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">📊 Trade Statistics</div>
            <div class="metric-item">
                <span class="metric-label">Total Trades</span>
                <span class="metric-value">{metrics['total_trades_analyzer']}</span>
            </div>
            <div class="metric-item">
                <span class="metric-label">Win Rate</span>
                <span class="metric-value {win_rate_class}">{metrics['win_rate_analyzer_pct']:.1f}%</span>
            </div>
            <div class="metric-item">
                <span class="metric-label">Avg Trade Return</span>
                <span class="metric-value {avg_return_class}">{avg_return_sign}{abs(metrics['avg_trade_pnl_pct_strat']):.2f}%</span>
            </div>
        </div>
    </div>

    <h2>Trade History</h2>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Entry Time</th>
                <th class="text-right">Entry Price</th>
                <th class="text-right">Size</th>
                <th class="text-right">Entry RSI</th>
                <th>Exit Time</th>
                <th class="text-right">Exit Price</th>
                <th class="text-right">Exit RSI</th>
                <th class="text-right">P/L %</th>
                <th>Reason</th>
            </tr>
        </thead>
        <tbody>
            {trade_rows}
        </tbody>
    </table>
</body>
</html>"""
        
        # Write to file
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Generated backtest report: {report_path}")
        return report_path
    
    def _generate_trade_rows(self, strategy: bt.Strategy) -> str:
        """
        Generate HTML table rows for detailed trade analysis.
        
        Args:
            strategy: Backtrader strategy instance with trade data
            
        Returns:
            HTML table rows as string
        """
        if not hasattr(strategy, 'trades') or not strategy.trades:
            return "<tr><td colspan='10' style='text-align: center;'>No trades recorded</td></tr>"
        
        rows = []
        for i, trade in enumerate(strategy.trades, 1):
            # Get entry data
            entry_time = trade.get('entry_time', '').strftime('%Y-%m-%d %H:%M') if trade.get('entry_time') else 'N/A'
            entry_price = trade.get('executed_entry_price', trade.get('entry_price', 0))
            entry_price_str = f"{entry_price:.4f}" if entry_price else 'N/A'
            
            entry_rsi = f"{trade.get('entry_indicators', {}).get('rsi', 0):.2f}" if trade.get('entry_indicators', {}).get('rsi') is not None else 'N/A'
            entry_bb_lower = f"{trade.get('entry_indicators', {}).get('bb_lower', 0):.4f}" if trade.get('entry_indicators', {}).get('bb_lower') is not None else 'N/A'
            entry_bb_upper = f"{trade.get('entry_indicators', {}).get('bb_upper', 0):.4f}" if trade.get('entry_indicators', {}).get('bb_upper') is not None else 'N/A'
            
            # Get exit data
            exit_time = trade.get('exit_time', '').strftime('%Y-%m-%d %H:%M') if trade.get('exit_time') else 'N/A'
            exit_price = trade.get('executed_exit_price', trade.get('exit_price', 0))
            exit_price_str = f"{exit_price:.4f}" if exit_price else 'N/A'
            
            exit_rsi = f"{trade.get('exit_indicators', {}).get('rsi', 0):.2f}" if trade.get('exit_indicators', {}).get('rsi') is not None else 'N/A'
            
            # Get trade size and calculate position value
            trade_size = trade.get('size', 0)
            position_value = trade_size * entry_price if trade_size and entry_price else 0
            
            # Calculate result and determine style
            result = ''
            style = ''
            pnl = 0
            
            if 'profit_pct' in trade and trade['profit_pct'] is not None:
                pnl = trade['profit_pct']
                result = f"+{pnl:.2f}%"
                style = 'color: #00aa00; font-weight: bold;'
            elif 'loss_pct' in trade and trade['loss_pct'] is not None:
                pnl = -trade['loss_pct']
                result = f"-{trade['loss_pct']:.2f}%"
                style = 'color: #ff0000; font-weight: bold;'
                
            # Get exit reason
            exit_reason = trade.get('exit_reason', 'UNKNOWN').replace('_', ' ').title()
            
            # Determine the format specifier for trade_size
            trade_size_format_specifier = '.4f' if trade_size < 1 else '.2f'

            # Generate row with all trade details
            row = f"""
            <tr style='border-bottom: 1px solid #ddd;'>
                <td style='padding: 8px; border: 1px solid #ddd;'>{i}</td>
                <td style='padding: 8px; border: 1px solid #ddd;'>{entry_time}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd;'>{entry_price_str}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd;'>{trade_size:{trade_size_format_specifier}}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd;'>{entry_rsi}</td>
                <td style='padding: 8px; border: 1px solid #ddd;'>{exit_time}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd;'>{exit_price_str}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd;'>{exit_rsi}</td>
                <td style='padding: 8px; text-align: right; border: 1px solid #ddd; {style}'>{result}</td>
                <td style='padding: 8px; border: 1px solid #ddd;'>{exit_reason}</td>
            </tr>
            """
            rows.append(row)
        
        return '\n'.join(rows)
