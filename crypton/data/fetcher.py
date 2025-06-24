"""
DataFetcher module for retrieving market data from Binance.

This module provides functionality to fetch both historical OHLCV data via REST API
and real-time market data via WebSocket connections.
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import ccxt
import pandas as pd
from binance.client import Client
from binance.websockets import BinanceSocketManager
from loguru import logger

from crypton.utils.config import load_config


class DataFetcher:
    """
    Class for fetching market data from Binance.
    
    Provides methods for historical data retrieval via REST API
    and real-time market data via WebSocket connections.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True):
        """
        Initialize the DataFetcher with API credentials.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Whether to use the testnet (default: True)
        """
        # Get API credentials from environment if not provided
        self.testnet = testnet
        
        # Koristi posebne ključeve za testnet i produkciju
        if self.testnet:
            self.api_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
            self.api_secret = api_secret or os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET")
            logger.info("Using TESTNET API credentials")
        else:
            self.api_key = api_key or os.getenv("BINANCE_API_KEY")
            self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
            logger.info("Using PRODUCTION API credentials")
        
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials not provided. Some functionality will be limited.")
        
        # Initialize CCXT client
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
                'testnet': self.testnet
            }
        })
        
        # Initialize Binance client with retry mechanism
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                if self.testnet:
                    # For testnet, we need to use the testnet base URL
                    self.client = Client(
                        api_key=self.api_key, 
                        api_secret=self.api_secret
                    )
                    # Set the testnet URL
                    self.client.API_URL = 'https://testnet.binance.vision/api'
                else:
                    # For production
                    self.client = Client(
                        api_key=self.api_key, 
                        api_secret=self.api_secret
                    )
                logger.info(f"Binance client initialized successfully on attempt {attempt + 1}")
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to initialize Binance client (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to initialize Binance client after {max_retries} attempts: {e}")
                    raise
        
        # WebSocket manager for live data
        self.ws_manager = None
        
        # Load configuration
        self.config = load_config()
        self.symbols = self.config.get('symbols', ['SUI/USDT'])
        self.interval = self.config.get('interval', '15m')
        
        logger.info(f"DataFetcher initialized with testnet={self.testnet}")
    
    def get_historical_ohlcv(
        self, 
        symbol: str, 
        timeframe: str = '15m', 
        since: Optional[Union[int, datetime]] = None, 
        limit: int = 1000,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV (Open, High, Low, Close, Volume) data.
        Supports pagination for fetching longer time ranges.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1m', '1h', '1d')
            since: Start time in milliseconds or datetime
            limit: Maximum number of candles per request
            end_date: Optional end date to stop fetching
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Logging current time and timezone info for debugging
            current_time = datetime.now()
            logger.info(f"Current local time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}, Timestamp: {int(current_time.timestamp() * 1000)}ms")
            logger.info(f"Fetching historical data for {symbol} at {timeframe} timeframe from {since} to {end_date if end_date else 'now'}")
            
            # Convert datetime to timestamp if needed
            if isinstance(since, datetime):
                since_ts = int(since.timestamp() * 1000)
            elif since is not None:
                since_ts = since
            else:
                # Default to 1 day ago if since is None
                default_start = datetime.now() - timedelta(days=1)
                since_ts = int(default_start.timestamp() * 1000)
                logger.info(f"No start time provided, defaulting to 1 day ago: {default_start}")
                
            # Convert end_date to timestamp if provided
            end_ts = None
            if end_date is not None:
                end_ts = int(end_date.timestamp() * 1000)
            
            # Calculate time per candle in milliseconds
            timeframe_ms = self._get_timeframe_ms(timeframe)
            
            # Use pagination to fetch all data within date range
            all_candles = []
            current_since = since_ts
            page_count = 0
            max_pages = 50  # Ograničimo na 50 stranica (50,000 sveća) kao sigurnosna mera
            
            # Set exchange to use adjust for time difference
            self.exchange.options['adjustForTimeDifference'] = True
            
            while True:
                page_count += 1
                # Log the fetch time to track when we're making the API call
                fetch_time = datetime.now()
                logger.debug(f"Fetch time: {fetch_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.debug(f"Fetching batch {page_count} for {symbol} since {datetime.fromtimestamp(current_since/1000)}")
                
                # Force recent data with newer until parameter
                until_param = None
                if page_count == 1:  # Only for first page to ensure we get latest data
                    until_param = int(fetch_time.timestamp() * 1000)  # Current time in ms
                    logger.debug(f"Setting until parameter to current time: {fetch_time}")
                
                # Fetch batch of candles with options for better time handling
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=limit,
                    params={'until': until_param} if until_param else {}
                )
                
                if not ohlcv or len(ohlcv) == 0:
                    logger.debug(f"No more data for {symbol}")
                    break  # No more data
                    
                all_candles.extend(ohlcv)
                logger.debug(f"Added {len(ohlcv)} candles, total now: {len(all_candles)}")
                
                # Check if we've reached the end date
                last_candle_time = ohlcv[-1][0]
                if end_ts and last_candle_time >= end_ts:
                    logger.debug(f"Reached end date, stopping pagination")
                    break
                    
                # Check if we got fewer candles than requested (end of data)
                if len(ohlcv) < limit:
                    logger.debug(f"Received fewer candles than limit, probably reached end of data")
                    break
                    
                # Update since timestamp for next batch (add 1 to avoid duplicates)
                current_since = last_candle_time + 1
                
                # Safety check - don't fetch too many pages
                if page_count >= max_pages:
                    logger.warning(f"Reached maximum page limit ({max_pages}) for {symbol}, truncating results")
                    break
            
            if not all_candles:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(
                all_candles, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Store original timestamp for debug purposes
            df['timestamp_ms'] = df['timestamp'].copy()
            
            # Add local time (UTC+2) column
            utc_offset = 2 * 60 * 60 * 1000  # 2 sata u milisekundama za CEST/UTC+2
            df['local_timestamp_ms'] = df['timestamp_ms'] + utc_offset
            
            # Convert timestamp to datetime (UTC)
            df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms')
            df['datetime'] = df['timestamp']  # Human-readable UTC time
            
            # Convert local timestamp to datetime
            df['local_time'] = pd.to_datetime(df['local_timestamp_ms'], unit='ms')
            
            # Filter by end_date if provided
            if end_date is not None:
                df = df[df['timestamp'] <= end_date]
            
            # Sort by timestamp to ensure chronological order
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Log more detailed information about the data we fetched
            if not df.empty:
                first_candle = df.iloc[0]
                last_candle = df.iloc[-1]
                latest_local = datetime.now()
                
                logger.info(f"Fetched {len(df)} candles for {symbol} from {first_candle['datetime']} to {last_candle['datetime']} (UTC)")
                logger.info(f"Local time range: from {first_candle['local_time']} to {last_candle['local_time']} (CEST/UTC+2)")
                logger.info(f"Latest candle UTC: {last_candle['datetime']}, Local: {last_candle['local_time']}, Current time: {latest_local.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"Time difference from latest candle: {(latest_local - last_candle['local_time']).total_seconds()/60:.2f} minutes")
                
                # Check if we're missing the most recent candle using local time
                timeframe_mins = int(timeframe[:-1]) if timeframe.endswith('m') else int(timeframe[:-1])*60 if timeframe.endswith('h') else 1440
                if (latest_local - last_candle['local_time']).total_seconds()/60 > timeframe_mins*2:
                    logger.warning(f"Missing recent data! Latest candle local time is {last_candle['local_time']}, which is more than 2 timeframes old!")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            logger.error(f"Exception details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return pd.DataFrame()
    
    def _get_timeframe_ms(self, timeframe: str) -> int:
        """
        Convert timeframe string to milliseconds.
        
        Args:
            timeframe: Timeframe string (e.g. '1m', '5m', '1h', '1d')
            
        Returns:
            Timeframe in milliseconds
        """
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        elif unit == 'w':
            return value * 7 * 24 * 60 * 60 * 1000
        else:
            logger.warning(f"Unknown timeframe unit: {unit}, defaulting to 1m")
            return 60 * 1000  # default to 1m
    
    def start_live_kline_stream(self, symbol: str, interval: str = '1m', callback=None):
        """
        Start a WebSocket stream for live kline/candlestick data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1m', '1h')
            callback: Function to call with the received data
        """
        try:
            # Initialize WebSocket manager if needed
            if not self.ws_manager:
                self.ws_manager = BinanceSocketManager(self.client)
                self.ws_manager.start()
            
            # Format symbol for WebSocket (remove '/')
            formatted_symbol = symbol.replace('/', '').upper()
            
            # Start the kline stream
            self.ws_manager.start_kline_socket(
                symbol=formatted_symbol,
                interval=interval,
                callback=callback or self._handle_kline_message
            )
            
            logger.info(f"Started live kline stream for {symbol} at {interval} interval")
        
        except Exception as e:
            logger.error(f"Error starting live kline stream: {e}")
    
    def _handle_kline_message(self, msg):
        """
        Default handler for kline messages.
        
        Args:
            msg: WebSocket message data
        """
        try:
            # Check if it's an error message
            if not msg or 'e' in msg and msg['e'] == 'error':
                logger.error(f"WebSocket error: {msg}")
                return
            
            # The message contains the kline data directly
            kline = msg.get('k', {})
            if not kline:
                return
                
            # Extract kline data
            symbol = kline.get('s', '')
            is_closed = kline.get('x', False)
            
            # Only process closed candles by default
            if is_closed:
                candle_data = {
                    'timestamp': kline.get('t'),
                    'symbol': symbol,
                    'interval': kline.get('i'),
                    'open': float(kline.get('o')),
                    'high': float(kline.get('h')),
                    'low': float(kline.get('l')),
                    'close': float(kline.get('c')),
                    'volume': float(kline.get('v')),
                    'closed': is_closed
                }
                
                logger.debug(f"Received closed candle: {symbol} {candle_data}")
                # This data would typically be passed to a processing queue
                # or used to update indicators directly
        
        except Exception as e:
            logger.error(f"Error handling kline message: {e}")
    
    def stop_all_streams(self):
        """Stop all running WebSocket streams."""
        if self.ws_manager:
            try:
                self.ws_manager.close()
                logger.info("Stopped all WebSocket streams")
            except Exception as e:
                logger.error(f"Error stopping WebSocket streams: {e}")
            finally:
                self.ws_manager = None
    
    def get_account_info(self) -> Dict:
        """
        Get account information including balances.
        
        Returns:
            Dict containing account information
        """
        try:
            account_info = self.client.get_account()
            return account_info
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return {}
    
    def get_ticker_prices(self, symbols: Optional[List[str]] = None) -> Dict:
        """
        Get current ticker prices for specified symbols.
        
        Args:
            symbols: List of symbols (e.g., ['BTCUSDT', 'ETHUSDT'])
            
        Returns:
            Dict mapping symbols to prices
        """
        try:
            if symbols:
                # Format symbols for Binance API (remove '/')
                formatted_symbols = [s.replace('/', '') for s in symbols]
                tickers = self.client.get_all_tickers()
                return {t['symbol']: float(t['price']) for t in tickers if t['symbol'] in formatted_symbols}
            else:
                tickers = self.client.get_all_tickers()
                return {t['symbol']: float(t['price']) for t in tickers}
        except Exception as e:
            logger.error(f"Error fetching ticker prices: {e}")
            return {}
    
    def __del__(self):
        """Clean up resources when the object is destroyed."""
        try:
            self.stop_all_streams()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
