"""
Backtesting harness for the Crypton trading bot.

This module integrates with backtrader to provide comprehensive
backtesting capabilities for trading strategies.
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import backtrader as bt
import pandas as pd
from loguru import logger

from crypton.strategy.mean_reversion import MeanReversionStrategy, SignalType
from crypton.utils.config import load_config


class MeanReversionBT(bt.Strategy):
    """Backtrader implementation of Mean Reversion strategy."""
    
    params = (
        ('bb_length', 20),
        ('bb_std', 2.0),
        ('rsi_length', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('sma_length', 50),
        ('stop_loss_pct', 0.02),
        ('take_profit_pct', 0.04),
        ('position_size_pct', 0.01),
        ('cool_down_hours', 4),
    )
    
    def __init__(self):
        """Initialize indicators and variables for the strategy."""
        # Initialize indicators
        self.bb = bt.indicators.BollingerBands(
            self.data.close, 
            period=self.params.bb_length, 
            devfactor=self.params.bb_std
        )
        self.rsi = bt.indicators.RSI(
            self.data.close, 
            period=self.params.rsi_length
        )
        self.sma = bt.indicators.SMA(
            self.data.close, 
            period=self.params.sma_length
        )
        
        # Track last trade time for cool-down
        self.last_trade_time = datetime.min
        
        # Store signals for analysis
        self.buy_signals = []
        self.sell_signals = []
    
    def log(self, txt, dt=None):
        """Log strategy information with timestamp."""
        dt = dt or self.datas[0].datetime.datetime(0)
        logger.info(f'{dt.isoformat()} {txt}')
    
    def notify_order(self, order):
        """Handle order status notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            # Order submitted/accepted - no action
            return
        
        # Check if order has been completed
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
            else:
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order Canceled/Margin/Rejected: {order.status}')
        
        # Reset order reference
        self.order = None
    
    def notify_trade(self, trade):
        """Handle trade completed notifications."""
        if not trade.isclosed:
            return
        
        self.log(f'TRADE COMPLETED, Gross: {trade.pnl:.2f}, Net: {trade.pnlcomm:.2f}')
    
    def next(self):
        """Strategy logic executed on each bar."""
        # Skip if in cool-down period
        current_time = self.datas[0].datetime.datetime(0)
        if (current_time - self.last_trade_time) < timedelta(hours=self.params.cool_down_hours):
            return
        
        # Check for buy signal
        if (self.data.close[0] <= self.bb.lines.bot[0] and 
            self.rsi[0] < self.params.rsi_oversold and 
            not self.position):
            
            # Calculate position size based on equity percentage
            size = self.broker.getcash() * self.params.position_size_pct / self.data.close[0]
            
            # Place buy order
            self.log(f'BUY CREATE, Price: {self.data.close[0]:.2f}, Size: {size:.6f}')
            self.buy(size=size)
            
            # Record signal
            self.buy_signals.append((current_time, self.data.close[0]))
            
            # Update last trade time
            self.last_trade_time = current_time
        
        # If we have a position, check for take profit
        elif self.position:
            # Check for take profit (sell when price increases by take_profit_pct)
            if self.data.close[0] > self.position.price * (1 + self.params.take_profit_pct):
                profit_pct = (self.data.close[0] / self.position.price - 1) * 100
                self.log(f'TAKE PROFIT, Price: {self.data.close[0]:.2f}, Profit: {profit_pct:.2f}%')
                self.sell()
                
                # Record signal
                self.sell_signals.append((current_time, self.data.close[0]))
                
                # Update last trade time
                self.last_trade_time = current_time
            
            # Check for stop loss
            elif self.data.close[0] < self.position.price * (1 - self.params.stop_loss_pct):
                loss_pct = (1 - self.data.close[0] / self.position.price) * 100
                self.log(f'STOP LOSS, Price: {self.data.close[0]:.2f}, Loss: {loss_pct:.2f}%')
                self.sell()
                
                # Update last trade time
                self.last_trade_time = current_time


class BacktestHarness:
    """
    Harness for running and analyzing backtrader backtests.
    
    Provides functionality to load historical data, run backtests,
    and generate performance reports.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the backtest harness with configuration.
        
        Args:
            config: Dictionary containing configuration settings
        """
        self.config = config or load_config()
        
        # Extract relevant config parameters
        self.symbols = self.config.get('symbols', ['SUI/USDT'])
        self.interval = self.config.get('interval', '15m')
        self.bb_config = self.config.get('bb', {})
        self.rsi_config = self.config.get('rsi', {})
        self.risk_config = self.config.get('risk', {})
        self.cool_down = self.config.get('cool_down', {})
        
        logger.info("Backtest harness initialized with configuration:")
        logger.info(f"  Symbols: {self.symbols}")
        logger.info(f"  Interval: {self.interval}")
    
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
        data: Union[pd.DataFrame, bt.feeds.PandasData],
        initial_cash: float = 10000.0,
        commission: float = 0.001  # 0.1% taker fee
    ) -> Tuple[bt.Strategy, Dict]:
        """
        Run backtest with mean reversion strategy.
        
        Args:
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
                logger.error("Failed to prepare data for backtesting")
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
        logger.info("Starting backtest...")
        results = cerebro.run()
        strategy = results[0]
        
        # Calculate metrics
        metrics = self._calculate_metrics(strategy, initial_cash)
        
        logger.info(f"Backtest completed with final portfolio value: ${cerebro.broker.getvalue():.2f}")
        logger.info(f"Metrics: {metrics}")
        
        return strategy, metrics
    
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
            sharpe = strategy.analyzers.sharpe.get_analysis() if hasattr(strategy.analyzers, 'sharpe') else {}
            returns = strategy.analyzers.returns.get_analysis() if hasattr(strategy.analyzers, 'returns') else {}
            drawdown = strategy.analyzers.drawdown.get_analysis() if hasattr(strategy.analyzers, 'drawdown') else {}
            trades = strategy.analyzers.trades.get_analysis() if hasattr(strategy.analyzers, 'trades') else {}
            
            # Calculate portfolio value and return
            final_value = strategy.broker.getvalue()
            total_return = (final_value / initial_cash - 1) * 100
            
            # Extract trade metrics with safe dictionary access
            total_trades = trades.get('total', {}).get('total', 0)
            wins = trades.get('won', {}).get('total', 0)
            losses = trades.get('lost', {}).get('total', 0)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            # Get Sharpe ratio with a default value if not available
            sharpe_ratio = sharpe.get('sharperatio', None)
            if sharpe_ratio is not None and not isinstance(sharpe_ratio, (int, float)):
                sharpe_ratio = float(sharpe_ratio) if hasattr(sharpe_ratio, '__float__') else 0.0
            
            # Get max drawdown with a default value if not available
            max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
            if max_drawdown is not None:
                max_drawdown = float(max_drawdown) * 100
            else:
                max_drawdown = 0.0
            
            # Compile metrics with safe defaults
            metrics = {
                'initial_cash': float(initial_cash),
                'final_value': float(final_value),
                'total_return_pct': float(total_return) if total_return is not None else 0.0,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown_pct': max_drawdown,
                'total_trades': int(total_trades),
                'win_rate_pct': float(win_rate) if win_rate is not None else 0.0,
                'wins': int(wins),
                'losses': int(losses),
                'buy_signals': len(getattr(strategy, 'buy_signals', [])),
                'sell_signals': len(getattr(strategy, 'sell_signals', [])),
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            # Return default metrics in case of error
            return {
                'initial_cash': float(initial_cash),
                'final_value': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown_pct': 0.0,
                'total_trades': 0,
                'win_rate_pct': 0.0,
                'wins': 0,
                'losses': 0,
                'buy_signals': 0,
                'sell_signals': 0,
            }
        
        return metrics
    
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
                'total_trades': 0,
                'win_rate_pct': 0.0,
                'wins': 0,
                'losses': 0,
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
            'total_trades': 0,
            'win_rate_pct': 0.0,
            'wins': 0,
            'losses': 0,
            'buy_signals': 0,
            'sell_signals': 0,
        }
        
        # Update default metrics with actual values
        for key in default_metrics:
            if key not in metrics or metrics[key] is None:
                metrics[key] = default_metrics[key]
        
        # Create HTML report
        html_content = f"""<!DOCTYPE html>
            <html>
            <head>
                <title>Crypton Backtest Report</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1, h2 {{ color: #333; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ text-align: left; padding: 8px; border: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                    .metric-good {{ color: green; }}
                    .metric-bad {{ color: red; }}
                </style>
            </head>
            <body>
                <h1>Crypton Backtest Report</h1>
                <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                
                <h2>Overall Performance</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Initial Capital</td>
                        <td>${metrics['initial_cash']:.2f}</td>
                    </tr>
                    <tr>
                        <td>Final Portfolio Value</td>
                        <td>${metrics['final_value']:.2f}</td>
                    </tr>
                    <tr>
                        <td>Total Return</td>
                        <td class="{('metric-good' if metrics['total_return_pct'] > 0 else 'metric-bad')}">
                            {metrics['total_return_pct']:.2f}%
                        </td>
                    </tr>
                    <tr>
                        <td>Sharpe Ratio</td>
                        <td class="{('metric-good' if metrics['sharpe_ratio'] > 1 else 'metric-bad')}">
                            {metrics['sharpe_ratio']:.2f}
                        </td>
                    </tr>
                    <tr>
                        <td>Maximum Drawdown</td>
                        <td class="{('metric-good' if metrics['max_drawdown_pct'] < 10 else 'metric-bad')}">
                            {metrics['max_drawdown_pct']:.2f}%
                        </td>
                    </tr>
                </table>
                
                <h2>Trade Statistics</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Total Trades</td>
                        <td>{metrics['total_trades']}</td>
                    </tr>
                    <tr>
                        <td>Win Rate</td>
                        <td class="{('metric-good' if metrics['win_rate_pct'] > 50 else 'metric-bad')}">
                            {metrics['win_rate_pct']:.2f}%
                        </td>
                    </tr>
                    <tr>
                        <td>Winning Trades</td>
                        <td>{metrics['wins']}</td>
                    </tr>
                    <tr>
                        <td>Losing Trades</td>
                        <td>{metrics['losses']}</td>
                    </tr>
                    <tr>
                        <td>Buy Signals</td>
                        <td>{metrics['buy_signals']}</td>
                    </tr>
                    <tr>
                        <td>Sell Signals</td>
                        <td>{metrics['sell_signals']}</td>
                    </tr>
                </table>
            </body>
            </html>
            """
        
        # Write to file
        with open(report_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"Generated backtest report: {report_path}")
        return report_path
