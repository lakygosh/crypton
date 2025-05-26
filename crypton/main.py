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
from crypton.utils.logger import setup_logger
from crypton.utils.notify import notify_trade_execution, notify_trade_completed, notify_error, discord, slack
from crypton.utils.debug import ensure_indicator_columns, debug_dataframe


def setup_environment(config_path: Optional[str] = None):
    """Initialize environment variables and logger."""
    # Load environment variables from .env file
    load_dotenv()
    
    # Kreiraj logs direktorijum ako ne postoji
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Kreiraj log fajl sa vremenskim žigom
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(logs_dir, f"crypton_{current_time}.log")
    
    # Load configuration if provided to check for debug_mode
    debug_mode = False
    if config_path:
        config = load_config(config_path)
        debug_mode = config.get('debug_mode', False)
    
    # Set up logging with file
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_level=log_level, debug_mode=debug_mode, log_file=log_file)
    
    logger.info(f"Logging to file: {log_file}")
    
    # Notifikatori su već inicijalizovani u notify.py
    # Samo ćemo ažurirati webhook URL-ove ako su definisani
    webhook_url = os.getenv("DISCORD_WEBHOOK")
    if webhook_url:
        try:
            discord.webhook_url = webhook_url
            discord.enabled = True
        except Exception as e:
            logger.error(f"Failed to set Discord webhook URL: {e}")
            
    slack_webhook = os.getenv("SLACK_WEBHOOK")
    if slack_webhook and "your_webhook_url" not in slack_webhook:
        try:
            slack.webhook_url = slack_webhook
            slack.enabled = True
        except Exception as e:
            logger.error(f"Failed to set Slack webhook URL: {e}")
    
    logger.info("Environment initialized")


def run_portfolio_backtest(config_path: Optional[str] = None):
    """
    Run portfolio backtesting with historical data for multiple symbols simultaneously.
    This approach treats all symbols as a single portfolio, allowing for capital allocation
    and reinvestment across symbols.
    
    Args:
        config_path: Path to configuration file
    """
    logger.info("Starting portfolio backtest")
    
    # Load configuration
    config = load_config(config_path)
    
    # Get symbols and initial cash
    symbols = config.get('symbols', ['BTC/USDT', 'ETH/USDT', 'SUI/USDT'])
    initial_cash = config.get('initial_cash', 1000.0)
    
    # Create data fetcher
    data_fetcher = DataFetcher(testnet=True)
    
    # Create backtest harness
    backtest_harness = BacktestHarness(config)
    
    # Load backtest config for time period
    backtest_config = config.get('backtest', {})
    if 'start_date' in backtest_config:
        try:
            since = datetime.strptime(backtest_config['start_date'], '%Y-%m-%d')
            logger.info(f"Using start_date from config: {since}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid start_date in config, using default. Error: {e}")
            since = datetime.now() - timedelta(days=30)  # Default to last 30 days
    else:
        since = datetime.now() - timedelta(days=30)  # Default to last 30 days
    
    # Get end_date from config if provided
    end_date = None
    if 'end_date' in backtest_config:
        try:
            end_date = datetime.strptime(backtest_config['end_date'], '%Y-%m-%d')
            logger.info(f"Using end_date from config: {end_date}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid end_date in config, using default (current time). Error: {e}")
    
    # Calculate approximate number of candles needed
    timeframe = config.get('interval', '15m')
    days_between = 30  # Default
    if end_date:
        days_between = (end_date - since).days
    
    # Determine limit based on timeframe and days
    limit = 1000  # Default
    if days_between > 10:
        # Approximately calculate needed candles
        if timeframe == '15m':
            candles_needed = 4 * 24 * days_between
        elif timeframe == '1h':
            candles_needed = 24 * days_between
        elif timeframe == '4h':
            candles_needed = 6 * days_between
        elif timeframe == '1d':
            candles_needed = days_between
        else:
            candles_needed = 1000
        
        limit = min(candles_needed, 1000)  # Most APIs limit to 1000
    
    # Fetch data for all symbols
    symbol_data_dict = {}
    for symbol in symbols:
        logger.info(f"Fetching data for {symbol}")
        df = data_fetcher.get_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=limit
        )
        
        if df.empty:
            logger.error(f"No historical data available for {symbol}")
            continue
            
        symbol_data_dict[symbol] = df
    
    if not symbol_data_dict:
        logger.error("No data available for any symbol. Aborting portfolio backtest.")
        return {}
    
    # Run portfolio backtest
    logger.info(f"Running portfolio backtest with {len(symbol_data_dict)} symbols")
    strategy, metrics = backtest_harness.run_portfolio_backtest(
        symbol_data_dict=symbol_data_dict,
        initial_cash=initial_cash,
        commission=0.001
    )
    
    logger.info(f"Portfolio backtest completed with final value: ${metrics['final_value']:.2f}")
    logger.info(f"Total return: {metrics['total_return_pct']:.2f}%")
    
    return metrics


def run_backtest(config_path: Optional[str] = None):
    """
    Run backtesting with historical data for individual symbols separately.
    
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
        # Use backtest config for start_date if provided, otherwise default to last 30 days
        backtest_config = config.get('backtest', {})
        if 'start_date' in backtest_config:
            try:
                since = datetime.strptime(backtest_config['start_date'], '%Y-%m-%d')
                logger.info(f"Using start_date from config: {since}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid start_date in config, using default. Error: {e}")
                since = datetime.now() - timedelta(days=30)  # Default to last 30 days
        else:
            since = datetime.now() - timedelta(days=30)  # Default to last 30 days
        
        # Get end_date from config if provided
        end_date = None
        if 'end_date' in backtest_config:
            try:
                end_date = datetime.strptime(backtest_config['end_date'], '%Y-%m-%d')
                logger.info(f"Using end_date from config: {end_date}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid end_date in config, using default (current time). Error: {e}")
        
        timeframe = config.get('interval', '15m')
        
        # Za duže periode ćemo možda morati da preuzimamo podatke u delovima
        # Proveravamo koliko dana ima između start_date i end_date
        # Za interval od 15 minuta, 1000 sveća pokriva oko 10 dana
        # Napomena: Za produkciju bi trebalo implementirati paging u DataFetcher-u
        
        if end_date is not None:
            days_between = (end_date - since).days
            logger.info(f"Backtest period: {days_between} days from {since} to {end_date}")
            
            # Ako je period duži od 10 dana, povećajmo limit
            if days_between > 10:
                # Proračun aproksimativnog broja sveća potrebnih
                # Za 15m interval: 4 sveće po satu × 24 sata × broj dana
                if timeframe == '15m':
                    candles_needed = 4 * 24 * days_between
                elif timeframe == '1h':
                    candles_needed = 24 * days_between
                elif timeframe == '4h':
                    candles_needed = 6 * days_between
                elif timeframe == '1d':
                    candles_needed = days_between
                else:
                    candles_needed = 1000  # Default
                
                # Ograničimo na maksimum koji API dozvoljava
                limit = min(candles_needed, 1000)  # Većina API-ja ima limit od 1000
                logger.info(f"Setting limit to {limit} candles for extended period")
            else:
                limit = 1000
        else:
            limit = 1000
            logger.info(f"Using default limit of {limit} candles")
        
        # Preuzimanje podataka
        df = data_fetcher.get_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=limit,
            end_date=end_date  # Dodajemo end_date parametar
        )
        
        if df.empty:
            logger.error(f"No historical data available for {symbol}")
            continue
            
        # Debug: Log the actual date range of the fetched data
        if not df.empty:
            actual_start_date = df['timestamp'].min()
            actual_end_date = df['timestamp'].max()
            logger.info(f"ACTUAL DATA RANGE: {symbol} data from {actual_start_date} to {actual_end_date}")
            logger.info(f"REQUESTED RANGE: from {since} to {end_date if end_date else 'now'}")
            
            # Provera da li se stvarni datumi poklapaju sa traženim
            if actual_start_date.date() > since.date():
                logger.warning(f"Actual start date {actual_start_date} is later than requested {since}")
            if end_date and actual_end_date.date() < end_date.date():
                logger.warning(f"Actual end date {actual_end_date} is earlier than requested {end_date}")
        
        # Run backtest
        strategy, metrics = backtest_harness.run_backtest(symbol, timeframe, df)
        
        # Check if backtest was successful
        if strategy is None or metrics is None:
            logger.error(f"Backtest failed for {symbol}")
            continue
        
        # Store results
        results[symbol] = metrics
    
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
    
    # Create components - koristimo posebne testnet API ključeve
    data_fetcher = DataFetcher(testnet=True)
    strategy = MeanReversionStrategy(config)
    execution = ExecutionEngine(testnet=True)
    
    # Main trading loop
    # --- Optimizacija: čuvaj istoriju i samo dodaj novu sveću u svakom ciklusu ---
    symbol_data = {}
    for symbol in config.get('symbols', ['SUI/USDT']):
        logger.info(f"Initial fetch for {symbol}")
        df = data_fetcher.get_historical_ohlcv(
            symbol=symbol,
            timeframe=config.get('interval', '15m'),
            limit=100
        )
        if df.empty:
            logger.error(f"No data available for {symbol} on initial fetch")
            symbol_data[symbol] = pd.DataFrame()
        else:
            symbol_data[symbol] = df.copy()
    try:
        while True:
            for symbol in config.get('symbols', ['SUI/USDT']):
                logger.info(f"Processing {symbol}")
                df = symbol_data[symbol]
                if df.empty:
                    logger.error(f"No data available for {symbol}")
                    continue
                # Povuci samo najnoviju sveću
                last_timestamp = df['timestamp'].max() if not df.empty else None
                
                # Dodaj mali buffer da bismo sigurno dobili nove sveće (1 minut)
                since_time = None
                if last_timestamp is not None:
                    # Konvertuj pandas timestamp u datetime i dodaj mali offset da izbegnemo duple podatke
                    since_time = last_timestamp.to_pydatetime() - timedelta(minutes=1)
                    logger.info(f"Fetching new candles for {symbol} since {since_time}")
                
                new_df = data_fetcher.get_historical_ohlcv(
                    symbol=symbol,
                    timeframe=config.get('interval', '15m'),
                    since=since_time,  # Počni od poslednjeg timestamp-a
                    limit=5  # Dovoljno za nekoliko novih sveća
                )
                if not new_df.empty:
                    # Dodaj samo nove sveće
                    latest = new_df[new_df['timestamp'] > last_timestamp] if last_timestamp is not None else new_df
                    if not latest.empty:
                        df = pd.concat([df, latest], ignore_index=True)
                        # Ograniči dužinu DataFrame-a na 100
                        df = df.sort_values('timestamp').reset_index(drop=True)
                        if len(df) > 100:
                            df = df.iloc[-100:]
                        symbol_data[symbol] = df
                # Check for signals
                logger.info(f"Checking for signal on {symbol} with DataFrame of shape {df.shape}")
                signal, price, data = strategy.check_for_signal(df, symbol)
                logger.info(f"Signal check result for {symbol}: {signal}")
                
                # Execute trades based on signals
                if signal == SignalType.BUY:
                    logger.info(f"Processing BUY signal for {symbol} at price {price}")
                    quantity, notional = execution.calculate_position_size(symbol, price)
                    logger.info(f"Calculated position size for {symbol}: {quantity} units (≈{notional} USDT)")
                    
                    try:
                        order = execution.place_market_order(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=quantity
                        )
                        logger.info(f"Order placement result: {order}")
                        
                        if order:
                            logger.info(f"Executed BUY order for {symbol}: {quantity} @ {price}")
                            notify_trade_execution(
                                symbol=symbol,
                                side="BUY",
                                price=price,
                                quantity=quantity,
                                order_id=order.get("orderId")
                            )
                        else:
                            logger.warning(f"Order placement returned empty result for {symbol}")
                    except Exception as e:
                        logger.error(f"Error placing buy order for {symbol}: {e}", exc_info=True)
                elif signal == SignalType.SELL:
                    positions = execution.open_positions
                    if symbol in positions:
                        quantity = positions[symbol]["quantity"]
                        order = execution.place_market_order(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=quantity
                        )
                        if order:
                            logger.info(f"Executed SELL order for {symbol}: {quantity} @ {price}")
                            notify_trade_execution(
                                symbol=symbol,
                                side="SELL",
                                price=price,
                                quantity=quantity,
                                order_id=order.get("orderId")
                            )
                    else:
                        logger.warning(f"SELL signal for {symbol} but no open position")
            logger.info("Sleeping before next iteration...")
            time.sleep(60 * 15)  # 15 minuta
    except KeyboardInterrupt:
        logger.info("Paper trading stopped by user")
    except Exception as e:
        notify_error(f"Paper trading error: {e}")
    finally:
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
    
    # Daily loss tracking
    daily_loss_cap = config.get('risk', {}).get('daily_loss_cap', 0.05)  # 5% default
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    starting_balance = execution.get_account_balance()
    daily_low_balance = starting_balance
    
    # Setup WebSocket connections for live price updates
    for symbol in config.get('symbols', ['SUI/USDT']):
        formatted_symbol = symbol.replace('/', '')
        data_fetcher.start_live_kline_stream(formatted_symbol, config.get('interval', '15m'))
    
    # Initialize data storage
    symbol_data = {}
    
    # Main trading loop
    try:
        while True:
            # Reset daily loss tracking at midnight
            now = datetime.now()
            if now.date() > day_start.date():
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                starting_balance = execution.get_account_balance()
                daily_low_balance = starting_balance
                logger.info(f"New trading day started. Starting balance: ${starting_balance:.2f}")
            
            for symbol in config.get('symbols', ['SUI/USDT']):
                logger.info(f"Processing {symbol}")
                
                # Fetch latest data if not in cache
                if symbol not in symbol_data or symbol_data[symbol].empty:
                    df = data_fetcher.get_historical_ohlcv(
                        symbol=symbol,
                        timeframe=config.get('interval', '15m'),
                        limit=100
                    )
                    if df.empty:
                        logger.error(f"No data available for {symbol}")
                        continue
                    symbol_data[symbol] = df
                else:
                    # Update with latest candle
                    df = symbol_data[symbol]
                    latest_time = df['timestamp'].max()
                    
                    # Calculate time since last candle
                    current_time = datetime.now()
                    time_diff = (current_time - latest_time.to_pydatetime()).total_seconds() / 60  # minutes
                    
                    # Only fetch new data if it's been long enough for a new candle
                    timeframe_mins = int(config.get('interval', '15m')[:-1])
                    if time_diff >= timeframe_mins:
                        # Fetch only new candles
                        since_time = latest_time.to_pydatetime() - timedelta(minutes=1)  # Small buffer
                        new_df = data_fetcher.get_historical_ohlcv(
                            symbol=symbol,
                            timeframe=config.get('interval', '15m'),
                            since=since_time,
                            limit=5  # Just a few recent candles
                        )
                        
                        if not new_df.empty:
                            # Add only new candles
                            new_df = new_df[new_df['timestamp'] > latest_time]
                            if not new_df.empty:
                                df = pd.concat([df, new_df], ignore_index=True)
                                # Keep dataframe size manageable
                                df = df.sort_values('timestamp').tail(100).reset_index(drop=True)
                                symbol_data[symbol] = df
                                logger.info(f"Added {len(new_df)} new candles for {symbol}")
                
                # Check for signals
                signal, price, data = strategy.check_for_signal(df, symbol)
                
                # Check current account balance for daily loss cap
                current_balance = execution.get_account_balance()
                daily_low_balance = min(daily_low_balance, current_balance)
                daily_loss = (starting_balance - daily_low_balance) / starting_balance
                
                # Execute trades based on signals
                if signal == SignalType.BUY:
                    # Check daily loss cap
                    if daily_loss > daily_loss_cap:
                        logger.warning("Daily loss cap reached. Skipping buy signal.")
                        notify_error("Daily loss cap reached", "Trading paused for 24 hours")
                        continue
                    
                    # Calculate position size
                    quantity, notional = execution.calculate_position_size(symbol, price)
                    
                    # Place order
                    try:
                        order = execution.place_market_order(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=quantity
                        )
                        
                        if order:
                            logger.info(f"Executed BUY order for {symbol}: {quantity} @ {price}")
                            notify_trade_execution(
                                symbol=symbol,
                                side="BUY",
                                price=price,
                                quantity=quantity,
                                order_id=order.get("orderId")
                            )
                    except Exception as e:
                        error_msg = f"Greška pri izvršavanju BUY naloga za {symbol}: {e}"
                        logger.error(error_msg)
                        notify_error(error_msg, f"Cena: {price}, Količina: {quantity}")
                
                elif signal == SignalType.SELL:
                    # Get current position size
                    positions = execution.open_positions
                    if symbol in positions:
                        quantity = positions[symbol]["quantity"]
                        
                        # Place order
                        try:
                            order = execution.place_market_order(
                                symbol=symbol,
                                side=OrderSide.SELL,
                                quantity=quantity
                            )
                            
                            if order:
                                logger.info(f"Executed SELL order for {symbol}: {quantity} @ {price}")
                                notify_trade_execution(
                                    symbol=symbol,
                                    side="SELL",
                                    price=price,
                                    quantity=quantity,
                                    order_id=order.get("orderId")
                                )
                        except Exception as e:
                            error_msg = f"Greška pri izvršavanju SELL naloga za {symbol}: {e}"
                            logger.error(error_msg)
                            notify_error(error_msg, f"Cena: {price}, Količina: {quantity}")
                    else:
                        error_msg = f"SELL signal za {symbol} ali nema otvorene pozicije"
                        logger.warning(error_msg)
                        notify_error(error_msg, "Propušten SELL signal")
            
            # Sleep between iterations
            logger.info("Sleeping before next iteration...")
            time.sleep(60 * 15)  # 15 minutes
            
    except KeyboardInterrupt:
        logger.info("Live trading stopped by user")
        notify_error("LIVE TRADING STOPPED BY USER", "Trading bot was manually stopped")
    except Exception as e:
        logger.error(f"Error in live trading: {e}")
        notify_error(f"Live trading error: {e}")
    finally:
        # Clean up
        data_fetcher.stop_all_streams()
        logger.info("Live trading ended")


def main():
    """Main entry point for the application."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Crypton - Crypto Trading Bot")
    
    # Add positional argument for mode
    parser.add_argument('mode', choices=['backtest', 'portfolio', 'paper', 'live'],
                      help='Mode: backtest (separate symbol backtesting), portfolio (multi-symbol portfolio backtest), paper (paper trading), live (live trading)')
    
    # Add optional argument for config file
    parser.add_argument('--config', type=str, default='config.yml',
                      help='Path to configuration file')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set up environment with config path
    setup_environment(args.config)
    
    # Run in selected mode
    if args.mode == 'backtest':
        run_backtest(args.config)
    elif args.mode == 'portfolio':
        run_portfolio_backtest(args.config)
    elif args.mode == 'paper':
        run_paper_trade(args.config)
    elif args.mode == 'live':
        run_live_trade(args.config)
    else:
        logger.error(f"Unknown mode: {args.mode}")


if __name__ == "__main__":
    main()
