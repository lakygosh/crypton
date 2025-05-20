"""
Tests for the DataFetcher module.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from crypton.data.fetcher import DataFetcher


class TestDataFetcher:
    """Test cases for the DataFetcher class."""
    
    @pytest.fixture
    def mock_config(self):
        """Fixture for mocked configuration."""
        return {
            'symbols': ['BTC/USDT', 'ETH/USDT'],
            'interval': '1h'
        }
    
    @patch('crypton.data.fetcher.load_config')
    @patch('crypton.data.fetcher.Client')
    @patch('crypton.data.fetcher.ccxt.binance')
    def test_init(self, mock_ccxt, mock_client, mock_load_config, mock_config):
        """Test initialization of DataFetcher."""
        # Mock the configuration
        mock_load_config.return_value = mock_config
        
        # Create fetcher instance
        fetcher = DataFetcher(testnet=True)
        
        # Verify CCXT binance was created with correct parameters
        mock_ccxt.assert_called_once()
        
        # Verify Binance client was created with testnet=True
        mock_client.assert_called_once()
        assert mock_client.call_args[1]['testnet'] is True
        
        # Verify symbols and interval were loaded from config
        assert fetcher.symbols == ['BTC/USDT', 'ETH/USDT']
        assert fetcher.interval == '1h'
    
    @patch('crypton.data.fetcher.load_config')
    @patch('crypton.data.fetcher.Client')
    @patch('crypton.data.fetcher.ccxt.binance')
    def test_get_historical_ohlcv(self, mock_ccxt, mock_client, mock_load_config, mock_config):
        """Test fetching historical OHLCV data."""
        # Mock the configuration
        mock_load_config.return_value = mock_config
        
        # Mock the ccxt instance
        mock_instance = mock_ccxt.return_value
        
        # Create sample OHLCV data
        sample_data = [
            [1620000000000, 50000, 51000, 49000, 50500, 100],  # timestamp, open, high, low, close, volume
            [1620003600000, 50500, 52000, 50200, 51500, 150]
        ]
        mock_instance.fetch_ohlcv.return_value = sample_data
        
        # Create fetcher instance
        fetcher = DataFetcher(testnet=True)
        
        # Call the method
        df = fetcher.get_historical_ohlcv('BTC/USDT', '1h')
        
        # Verify exchange.fetch_ohlcv was called with correct parameters
        mock_instance.fetch_ohlcv.assert_called_once_with(
            symbol='BTC/USDT',
            timeframe='1h',
            since=None,
            limit=1000
        )
        
        # Verify the returned dataframe has the expected structure
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns
        
        # Check the dataframe has the correct values
        assert len(df) == 2
        assert df.iloc[0]['close'] == 50500
        assert df.iloc[1]['volume'] == 150


if __name__ == '__main__':
    pytest.main()
