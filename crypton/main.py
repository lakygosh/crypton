"""
Main entry point for the Crypton trading bot.

This module provides command-line interfaces for backtesting,
paper trading, and live trading with the Crypton bot.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

from crypton.backtesting.backtest import BacktestHarness
from crypton.data.fetcher import DataFetcher
from crypton.execution.order_manager import ExecutionEngine, OrderSide
from crypton.strategy.mean_reversion import MeanReversionStrategy, SignalType
from crypton.utils.config import load_config
from crypton.utils.logger import SlackNotifier, setup_logger


def setup_environment():
    """Initialize environment variables and logger."""
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_level=log_level)
    
    logger.info("Environment initialized")


def run_backtest(config_path: Optional[str] = None):
    """
    Run backtesting with historical data.
    
    Args:
        config_path: Path to configuration file
    """
    logger.info("Starting backtest")
    
    # Load configuration
    config = load_config(config_path)
    
    # Create data fetcher
    data_fetcher = DataFetcher(testnet=True)
    
    # Create backtest harness
    backtest_harness = BacktestHarness(config)
    
    # Process each symbol
    results = {}
    for symbol in config.get('symbols', ['SUI/USDT']):
        logger.info(f"Running backtest for {symbol}")
        
        # Fetch historical data
        since = datetime.now() - timedelta(days=30)  # Default to last 30 days
        timeframe = config.get('interval', '15m')
        
        df = data_fetcher.get_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=1000
        )
        
        if df.empty:
            logger.error(f"No historical data available for {symbol}")
            continue
        
        # Run backtest
        strategy, metrics = backtest_harness.run_backtest(df)
        
        # Check if backtest was successful
        if strategy is None or metrics is None:
            logger.error(f"Backtest failed for {symbol}")
            continue
        
        # Store results
        results[symbol] = metrics
        
        # Generate report
        report_path = os.path.join(
            Path.cwd(),
            f"backtest_report_{symbol.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        backtest_harness.generate_report(strategy, metrics, report_path)
        
        logger.info(f"Backtest report generated: {report_path}")
    
    # Log combined results
    logger.info(f"Backtest completed for all symbols: {list(results.keys())}")
    
    return results


def run_paper_trade(config_path: Optional[str] = None):
    """
    Run paper trading with Binance testnet.
    
    Args:
        config_path: Path to configuration file
    """
    logger.info("Starting paper trading mode")
    
    # Load configuration
    config = load_config(config_path)
    
    # Create components
    data_fetcher = DataFetcher(testnet=True)
    strategy = MeanReversionStrategy(config)
    execution = ExecutionEngine(testnet=True)
    
    # Set up Slack notifications
    slack = SlackNotifier()
    
    # Main trading loop
    try:
        while True:
            for symbol in config.get('symbols', ['SUI/USDT']):
                logger.info(f"Processing {symbol}")
                
                # Fetch recent data
                df = data_fetcher.get_historical_ohlcv(
                    symbol=symbol,
                    timeframe=config.get('interval', '15m'),
                    limit=100
                )
                
                if df.empty:
                    logger.error(f"No data available for {symbol}")
                    continue
                
                # Check for signals
                signal, price, data = strategy.check_for_signal(df, symbol)
                
                # Execute trades based on signals
                if signal == SignalType.BUY:
                    # Calculate position size
                    quantity, notional = execution.calculate_position_size(symbol, price)
                    
                    # Place order
                    order = execution.place_market_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=quantity
                    )
                    
                    if order:
                        logger.info(f"Executed BUY order for {symbol}: {quantity} @ {price}")
                        slack.notify_trade(
                            symbol=symbol,
                            side="BUY",
                            price=price,
                            quantity=quantity,
                            order_id=order.get("orderId")
                        )
                
                elif signal == SignalType.SELL:
                    # Get current position size
                    positions = execution.open_positions
                    if symbol in positions:
                        quantity = positions[symbol]["quantity"]
                        
                        # Place order
                        order = execution.place_market_order(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=quantity
                        )
                        
                        if order:
                            logger.info(f"Executed SELL order for {symbol}: {quantity} @ {price}")
                            slack.notify_trade(
                                symbol=symbol,
                                side="SELL",
                                price=price,
                                quantity=quantity,
                                order_id=order.get("orderId")
                            )
                    else:
                        logger.warning(f"SELL signal for {symbol} but no open position")
            
            # Sleep between iterations
            logger.info("Sleeping before next iteration...")
            time.sleep(60 * 15)  # 15 minutes
            
    except KeyboardInterrupt:
        logger.info("Paper trading stopped by user")
    except Exception as e:
        logger.error(f"Error in paper trading: {e}")
        slack.notify_error(f"Paper trading error: {e}")
    finally:
        # Clean up
        data_fetcher.stop_all_streams()
        logger.info("Paper trading ended")


def run_live_trade(config_path: Optional[str] = None):
    """
    Run live trading with real money.
    
    Args:
        config_path: Path to configuration file
    """
    logger.warning("Starting LIVE trading mode with REAL funds")
    
    # Load configuration
    config = load_config(config_path)
    
    # Create components
    data_fetcher = DataFetcher(testnet=False)  # Use real API
    strategy = MeanReversionStrategy(config)
    execution = ExecutionEngine(testnet=False)  # Use real API
    
    # Set up Slack notifications
    slack = SlackNotifier()
    
    # Confirm with user
    print("WARNING: You are about to start live trading with real funds.")
    print("This will execute real trades on your Binance account.")
    confirmation = input("Type 'CONFIRM' to continue or anything else to abort: ")
    
    if confirmation != "CONFIRM":
        logger.info("Live trading aborted by user")
        return
    
    # Send notification
    slack.send_message(":rotating_light: *LIVE TRADING STARTED* :rotating_light:")
    
    # Main trading loop - same as paper trading but with real money
    try:
        while True:
            for symbol in config.get('symbols', ['SUI/USDT']):
                logger.info(f"Processing {symbol}")
                
                # Fetch recent data
                df = data_fetcher.get_historical_ohlcv(
                    symbol=symbol,
                    timeframe=config.get('interval', '15m'),
                    limit=100
                )
                
                if df.empty:
                    logger.error(f"No data available for {symbol}")
                    continue
                
                # Check for signals
                signal, price, data = strategy.check_for_signal(df, symbol)
                
                # Execute trades based on signals
                if signal == SignalType.BUY:
                    # Check if we've reached daily loss cap
                    if execution.check_daily_loss_cap():
                        logger.warning("Daily loss cap reached. Skipping buy signal.")
                        slack.notify_error("Daily loss cap reached", "Trading paused for 24 hours")
                        continue
                    
                    # Calculate position size
                    quantity, notional = execution.calculate_position_size(symbol, price)
                    
                    # Place order
                    order = execution.place_market_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        quantity=quantity
                    )
                    
                    if order:
                        logger.info(f"Executed BUY order for {symbol}: {quantity} @ {price}")
                        slack.notify_trade(
                            symbol=symbol,
                            side="BUY",
                            price=price,
                            quantity=quantity,
                            order_id=order.get("orderId")
                        )
                
                elif signal == SignalType.SELL:
                    # Get current position size
                    positions = execution.open_positions
                    if symbol in positions:
                        quantity = positions[symbol]["quantity"]
                        
                        # Place order
                        order = execution.place_market_order(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=quantity
                        )
                        
                        if order:
                            logger.info(f"Executed SELL order for {symbol}: {quantity} @ {price}")
                            slack.notify_trade(
                                symbol=symbol,
                                side="SELL",
                                price=price,
                                quantity=quantity,
                                order_id=order.get("orderId")
                            )
                    else:
                        logger.warning(f"SELL signal for {symbol} but no open position")
            
            # Sleep between iterations
            logger.info("Sleeping before next iteration...")
            time.sleep(60 * 15)  # 15 minutes
            
    except KeyboardInterrupt:
        logger.info("Live trading stopped by user")
        slack.send_message(":octagonal_sign: *LIVE TRADING STOPPED BY USER* :octagonal_sign:")
    except Exception as e:
        logger.error(f"Error in live trading: {e}")
        slack.notify_error(f"Live trading error: {e}")
    finally:
        # Clean up
        data_fetcher.stop_all_streams()
        logger.info("Live trading ended")


def main():
    """Main entry point for the application."""
    # Set up environment
    setup_environment()
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Crypton - Crypto Trading Bot")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtesting")
    backtest_parser.add_argument("--config", help="Path to configuration file")
    
    # Trade command
    trade_parser = subparsers.add_parser("trade", help="Run trading")
    trade_parser.add_argument("--mode", choices=["test", "live"], default="test", help="Trading mode")
    trade_parser.add_argument("--config", help="Path to configuration file")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if args.command == "backtest":
        run_backtest(args.config)
    elif args.command == "trade":
        if args.mode == "test":
            run_paper_trade(args.config)
        elif args.mode == "live":
            run_live_trade(args.config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
