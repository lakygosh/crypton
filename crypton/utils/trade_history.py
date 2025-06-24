"""
Trade history management for Crypton trading bot.

This module handles the persistent storage of trade information,
allowing the bot to track positions across restarts.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from loguru import logger

class TradeHistoryManager:
    """
    Manages trade history storage and retrieval.
    
    Stores trade data in a JSON file for persistence across bot restarts.
    """
    
    def __init__(self, file_path: Optional[str] = None):
        """
        Initialize the trade history manager.
        
        Args:
            file_path: Path to the trade history file (optional)
        """
        if file_path is None:
            # Check if we're running in Docker (common pattern: use /home/crypton/data)
            docker_data_path = Path("/home/crypton/data")
            if docker_data_path.exists():
                self.file_path = docker_data_path / "trade_history.json"
            else:
                # Default to data directory in project root (for local development)
                data_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                data_dir = data_dir / "data"
                data_dir.mkdir(exist_ok=True)
                self.file_path = data_dir / "trade_history.json"
        else:
            self.file_path = Path(file_path)
            
        logger.info(f"TradeHistoryManager initialized with file path: {self.file_path}")
        logger.info(f"Current working directory: {Path.cwd()}")
        logger.info(f"Data directory exists: {self.file_path.parent.exists()}")
        
        self.positions = {}
        self.closed_trades = []
        
        # Load existing data if available
        self._load_data()
        
    def _load_data(self):
        """Load trade history from file if it exists."""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    self.positions = data.get('positions', {})
                    self.closed_trades = data.get('closed_trades', [])
                logger.info(f"Loaded trade history from {self.file_path}")
            except Exception as e:
                logger.error(f"Error loading trade history: {e}")
                # Initialize with empty data
                self.positions = {}
                self.closed_trades = []
        else:
            logger.info(f"No trade history file found at {self.file_path}, starting fresh")
            self.positions = {}
            self.closed_trades = []
    
    def _save_data(self):
        """Save trade history to file."""
        try:
            data = {
                'positions': self.positions,
                'closed_trades': self.closed_trades,
                'last_updated': datetime.now().isoformat()
            }
            
            # Ensure the directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Debug info before saving
            logger.debug(f"Attempting to save trade history to: {self.file_path}")
            logger.debug(f"Directory exists: {self.file_path.parent.exists()}")
            logger.debug(f"File path is absolute: {self.file_path.is_absolute()}")
            logger.debug(f"Number of positions to save: {len(self.positions)}")
            
            with open(self.file_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()  # Ensure data is written to disk
                
            # Verify the file was written
            if self.file_path.exists() and self.file_path.stat().st_size > 0:
                logger.info(f"Successfully saved trade history to {self.file_path} ({self.file_path.stat().st_size} bytes)")
            else:
                logger.error(f"Trade history file was not created or is empty: {self.file_path}")
                
        except PermissionError as e:
            logger.error(f"Permission denied saving trade history to {self.file_path}: {e}")
        except OSError as e:
            logger.error(f"OS error saving trade history to {self.file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving trade history to {self.file_path}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def record_position_open(self, symbol: str, quantity: float, entry_price: float, 
                           order_id: str, timestamp: Optional[str] = None):
        """
        Record a new position being opened.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            quantity: Position size
            entry_price: Entry price
            order_id: Exchange order ID
            timestamp: ISO-formatted timestamp (optional, defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        position_data = {
            'symbol': symbol,
            'quantity': quantity,
            'entry_price': entry_price,
            'order_id': order_id,
            'entry_time': timestamp,
            'position_value': quantity * entry_price,
            'status': 'open',
            'tp_hits': [],
            'sl_hit': False
        }
        
        self.positions[symbol] = position_data
        logger.info(f"Recorded new position for {symbol}: {quantity} @ {entry_price}")
        self._save_data()
        
    def record_position_close(self, symbol: str, exit_price: float, exit_quantity: float,
                            order_id: str, profit_loss: float, exit_reason: str,
                            timestamp: Optional[str] = None):
        """
        Record a position being closed.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            exit_price: Exit price
            exit_quantity: Quantity sold
            order_id: Exchange order ID
            profit_loss: Realized profit/loss
            exit_reason: Reason for exit (e.g., 'take_profit', 'stop_loss', 'signal')
            timestamp: ISO-formatted timestamp (optional, defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        if symbol in self.positions:
            # Get the position data
            position = self.positions[symbol].copy()
            
            # Add exit information
            position['exit_price'] = exit_price
            position['exit_time'] = timestamp
            position['exit_quantity'] = exit_quantity
            position['exit_order_id'] = order_id
            position['profit_loss'] = profit_loss
            position['exit_reason'] = exit_reason
            position['status'] = 'closed'
            
            # Add to closed trades history
            self.closed_trades.append(position)
            
            # Remove from open positions
            del self.positions[symbol]
            
            logger.info(f"Recorded position close for {symbol}: {exit_quantity} @ {exit_price} (P/L: {profit_loss})")
            self._save_data()
        else:
            logger.warning(f"Attempted to close position for {symbol} but no open position found")
    
    def record_partial_take_profit(self, symbol: str, price: float, quantity: float, 
                                order_id: str, tier: int, timestamp: Optional[str] = None):
        """
        Record a partial take profit being hit.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            price: Take profit price
            quantity: Quantity sold
            order_id: Exchange order ID
            tier: Take profit tier (1, 2, or 3)
            timestamp: ISO-formatted timestamp (optional, defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        if symbol in self.positions:
            tp_data = {
                'tier': tier,
                'price': price,
                'quantity': quantity,
                'order_id': order_id,
                'time': timestamp
            }
            
            self.positions[symbol]['tp_hits'].append(tp_data)
            logger.info(f"Recorded TP{tier} hit for {symbol}: {quantity} @ {price}")
            self._save_data()
        else:
            logger.warning(f"Attempted to record TP for {symbol} but no open position found")
    
    def get_open_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all currently open positions.
        
        Returns:
            Dictionary of open positions by symbol
        """
        return self.positions
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get data for a specific position.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Position data or None if not found
        """
        return self.positions.get(symbol)
    
    def get_closed_trades(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get closed trade history.
        
        Args:
            limit: Maximum number of trades to return (optional)
            
        Returns:
            List of closed trades, newest first
        """
        trades = sorted(self.closed_trades, key=lambda x: x['exit_time'], reverse=True)
        if limit:
            return trades[:limit]
        return trades
        
    def get_trade_stats(self) -> Dict[str, Any]:
        """
        Get trading statistics.
        
        Returns:
            Dictionary of trading statistics
        """
        stats = {
            'total_trades': len(self.closed_trades),
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit_loss': 0.0,
            'win_rate': 0.0,
            'avg_profit': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0
        }
        
        if not self.closed_trades:
            return stats
            
        profits = []
        losses = []
        
        for trade in self.closed_trades:
            pl = trade.get('profit_loss', 0)
            stats['total_profit_loss'] += pl
            
            if pl > 0:
                stats['winning_trades'] += 1
                profits.append(pl)
                stats['largest_win'] = max(stats['largest_win'], pl)
            else:
                stats['losing_trades'] += 1
                losses.append(pl)
                stats['largest_loss'] = min(stats['largest_loss'], pl)
        
        if stats['total_trades'] > 0:
            stats['win_rate'] = stats['winning_trades'] / stats['total_trades']
            
        if profits:
            stats['avg_profit'] = sum(profits) / len(profits)
            
        if losses:
            stats['avg_loss'] = sum(losses) / len(losses)
            
        return stats
