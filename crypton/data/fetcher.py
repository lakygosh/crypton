"""
DataFetcher module for retrieving market data from Binance.

This module provides functionality to fetch both historical OHLCV data via REST API
and real-time market data via WebSocket connections.
"""
import os
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
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.testnet = testnet
        
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
        
        # Initialize Binance client
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
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV (Open, High, Low, Close, Volume) data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1m', '1h', '1d')
            since: Start time in milliseconds or datetime
            limit: Maximum number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            logger.info(f"Fetching historical data for {symbol} at {timeframe} timeframe")
            
            # Convert datetime to timestamp if needed
            if isinstance(since, datetime):
                since = int(since.timestamp() * 1000)
            
            # Fetch the data
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                limit=limit
            )
            
            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            logger.info(f"Fetched {len(df)} candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return pd.DataFrame()
    
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
