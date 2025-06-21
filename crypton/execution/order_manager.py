"""
Order execution module for the Crypton trading bot.

Handles order placement, cancellation, and tracking. Manages interaction
with Binance Order API while respecting rate limits and implementing
position management.
"""
import os
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger

from crypton.utils.config import load_config
from crypton.utils.trade_history import TradeHistoryManager


class OrderSide(Enum):
    """Enum representing order sides."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Enum representing order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(Enum):
    """Enum representing order statuses."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionEngine:
    """
    Engine for executing trades on Binance.
    
    Handles order placement, tracking, and risk management.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True):
        """
        Initialize the execution engine with API credentials.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Whether to use the testnet (default: True)
        """
        self.testnet = testnet
        
        # Get API credentials from environment if not provided
        if self.testnet:
            # Use testnet-specific environment variables if available
            self.api_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
            self.api_secret = api_secret or os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET")
            logger.info("Using Binance Testnet environment")
        else:
            # For production, use the regular API key environment variables
            self.api_key = api_key or os.getenv("BINANCE_API_KEY")
            self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
            logger.info("Using Binance Production environment")
        
        if not self.api_key or not self.api_secret:
            logger.error("API credentials not provided. Order execution will not work.")
        
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
        
        # Load configuration
        self.config = load_config()
        
        # Risk management parameters
        self.risk_config = self.config.get('risk', {})
        self.max_positions = self.risk_config.get('max_open_positions', 3)
        self.position_size_pct = self.risk_config.get('position_size_pct', 0.01)  # 1% of equity
        self.stop_loss_pct = self.risk_config.get('stop_loss_pct', 0.02)  # 2%
        
        # Graduated take profit parameters
        self.take_profit_config = self.risk_config.get('take_profit', {})
        
        # If take_profit is a nested dictionary, use those values
        if isinstance(self.take_profit_config, dict) and self.take_profit_config:
            self.take_profit_tier1_pct = self.take_profit_config.get('tier1_pct', 0.02)  # 2%
            self.take_profit_tier2_pct = self.take_profit_config.get('tier2_pct', 0.03)  # 3%
            self.take_profit_tier3_pct = self.take_profit_config.get('tier3_pct', 0.04)  # 4%
            self.take_profit_tier1_size_pct = self.take_profit_config.get('tier1_size_pct', 0.33)  # 33%
            self.take_profit_tier2_size_pct = self.take_profit_config.get('tier2_size_pct', 0.33)  # 33%
            self.take_profit_tier3_size_pct = self.take_profit_config.get('tier3_size_pct', 0.34)  # 34%
        else:
            # Backward compatibility for old config format with single take_profit_pct
            self.take_profit_pct = self.risk_config.get('take_profit_pct', 0.04)  # 4%
            self.take_profit_tier1_pct = 0.02  # 2%
            self.take_profit_tier2_pct = 0.03  # 3%
            self.take_profit_tier3_pct = self.take_profit_pct  # Use existing value (4%)
            self.take_profit_tier1_size_pct = 0.33  # 33%
            self.take_profit_tier2_size_pct = 0.33  # 33%
            self.take_profit_tier3_size_pct = 0.34  # 34%
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.05  # 50ms minimum between requests (20 requests per second)
        
        # Initialize trade history manager
        self.trade_history = TradeHistoryManager()
        
        # Open positions tracking
        self.open_positions: Dict[str, Dict] = {}
        
        # Load existing positions from the exchange
        self.load_open_positions()
        
        logger.info(f"Execution engine initialized with testnet={self.testnet}")
        logger.info(f"Risk parameters: max_positions={self.max_positions}, " +
                   f"position_size_pct={self.position_size_pct}, " +
                   f"stop_loss_pct={self.stop_loss_pct}, " +
                   f"take_profit_tier1_pct={self.take_profit_tier1_pct}, " +
                   f"take_profit_tier2_pct={self.take_profit_tier2_pct}, " +
                   f"take_profit_tier3_pct={self.take_profit_tier3_pct}")
    
    def _respect_rate_limit(self):
        """Ensure we don't exceed API rate limits."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get_account_balance(self, asset: str = "USDT") -> float:
        """
        Get account balance for a specific asset.
        
        Args:
            asset: Asset symbol (default: "USDT")
            
        Returns:
            Float representing the free balance of the asset
        """
        try:
            self._respect_rate_limit()
            account = self.client.get_account()
            balances = account.get("balances", [])
            
            for balance in balances:
                if balance["asset"] == asset:
                    return float(balance["free"])
            
            logger.warning(f"Asset {asset} not found in account")
            return 0.0
            
        except BinanceAPIException as e:
            logger.error(f"API error getting account balance: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return 0.0
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """
        Get trading information for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            
        Returns:
            Dictionary with symbol information
        """
        try:
            self._respect_rate_limit()
            exchange_info = self.client.get_exchange_info()
            
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            for sym_info in exchange_info["symbols"]:
                if sym_info["symbol"] == formatted_symbol:
                    return sym_info
            
            logger.warning(f"Symbol {symbol} not found in exchange info")
            return {}
            
        except BinanceAPIException as e:
            logger.error(f"API error getting symbol info: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting symbol info: {e}")
            return {}
    
    def calculate_position_size(self, symbol: str, price: float) -> Tuple[float, float]:
        """
        Calculate position size based on risk parameters.
        
        Args:
            symbol: Trading pair symbol
            price: Current price of the asset
            
        Returns:
            Tuple of (quantity, notional_value)
        """
        try:
            # Get account balance
            base_asset = "USDT"  # Assuming USDT is the base currency
            balance = self.get_account_balance(base_asset)
            
            # Calculate position size in base currency (e.g., USDT)
            position_value = balance * self.position_size_pct
            
            # Calculate quantity
            quantity = position_value / price
            
            # Get symbol information for precision
            symbol_info = self.get_symbol_info(symbol)
            
            if symbol_info:
                # Find lot size filter
                for filter_item in symbol_info.get("filters", []):
                    if filter_item["filterType"] == "LOT_SIZE":
                        min_qty = float(filter_item["minQty"])
                        max_qty = float(filter_item["maxQty"])
                        step_size = float(filter_item["stepSize"])
                        
                        # Ensure quantity respects step size
                        precision = len(str(step_size).rstrip('0').split('.')[-1])
                        quantity = round(quantity - (quantity % step_size), precision)
                        
                        # Ensure quantity is within bounds
                        quantity = max(min_qty, min(quantity, max_qty))
                        break
            
            # Calculate notional value
            notional_value = quantity * price
            
            logger.info(f"Calculated position size for {symbol}: " +
                       f"{quantity} units (≈{notional_value:.2f} {base_asset})")
            
            return quantity, notional_value
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.0, 0.0
    
    def place_market_order(
        self, 
        symbol: str, 
        side: OrderSide, 
        quantity: float
    ) -> Dict:
        """
        Place a market order.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            quantity: Order quantity
            
        Returns:
            Dictionary with order information
        """
        try:
            # Check if we've reached the maximum number of positions
            if (side == OrderSide.BUY and 
                len(self.open_positions) >= self.max_positions):
                logger.warning(f"Maximum number of positions ({self.max_positions}) reached. Cannot place BUY order.")
                return {}
            
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            # Ensure we don't exceed API rate limits
            self._respect_rate_limit()
            
            # Place the order
            order = self.client.create_order(
                symbol=formatted_symbol,
                side=side.value,
                type=OrderType.MARKET.value,
                quantity=quantity
            )
            
            # Extract the price from the order fills
            # For market orders, we need to calculate the average price
            if 'fills' in order and order['fills']:
                fills = order['fills']
                total_cost = sum(float(fill['price']) * float(fill['qty']) for fill in fills)
                total_qty = sum(float(fill['qty']) for fill in fills)
                avg_price = total_cost / total_qty if total_qty > 0 else 0
            else:
                # Fallback - get current price
                ticker = self.client.get_symbol_ticker(symbol=formatted_symbol)
                avg_price = float(ticker['price'])
            
            # Update position tracking
            if side == OrderSide.BUY:
                # Record the trade in history
                self.trade_history.record_position_open(
                    symbol=symbol,
                    quantity=float(order['executedQty']),
                    entry_price=avg_price,
                    order_id=str(order['orderId']),
                    timestamp=datetime.now().isoformat()
                )
                
                # Update internal tracking
                self.open_positions[symbol] = {
                    "quantity": float(order['executedQty']),
                    "entry_price": avg_price,
                    "current_price": avg_price,
                    "position_value": float(order['executedQty']) * avg_price,
                    "unrealized_pnl": 0.0,
                    "entry_time": datetime.now().isoformat(),
                    "order_id": str(order['orderId']),
                    "orders": {}
                }
                
                logger.info(f"Placed {side.value} market order for {quantity} {symbol}: {order['orderId']}")
                
                # Server-side SL/TP disabled – strategy generates exits
                
            elif side == OrderSide.SELL and symbol in self.open_positions:
                # Cancel any existing SL/TP orders before selling
                self._cancel_sl_tp_orders(symbol)
                
                # Calculate profit/loss
                position = self.open_positions[symbol]
                entry_price = position['entry_price']
                profit_loss = (avg_price - entry_price) * float(order['executedQty'])
                
                # Record the trade close in history
                self.trade_history.record_position_close(
                    symbol=symbol,
                    exit_price=avg_price,
                    exit_quantity=float(order['executedQty']),
                    order_id=str(order['orderId']),
                    profit_loss=profit_loss,
                    exit_reason='signal',  # Can be 'signal', 'stop_loss', or 'take_profit'
                    timestamp=datetime.now().isoformat()
                )
                
                # Remove from open positions on sell
                del self.open_positions[symbol]
                logger.info(f"Closed position for {symbol} with P/L: {profit_loss:.2f} USDT")
            
            return order
            
        except BinanceAPIException as e:
            logger.error(f"API error placing market order: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return {}
    
    def _place_sl_tp_orders(self, symbol: str) -> Tuple[Dict, List[Dict]]:
        """
        Place stop loss and graduated take profit orders for an open position.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Tuple of (stop_loss_order, [take_profit_orders])
        """
        try:
            # Get position details
            position = self.open_positions.get(symbol)
            if not position:
                logger.warning(f"No open position found for {symbol}")
                return {}, []
            
            entry_price = position["entry_price"]
            quantity = position["quantity"]
            
            # Calculate stop loss price
            sl_price = entry_price * (1 - self.stop_loss_pct)
            
            # Calculate take profit prices for each tier
            tp_tier1_price = entry_price * (1 + self.take_profit_tier1_pct)
            tp_tier2_price = entry_price * (1 + self.take_profit_tier2_pct)
            tp_tier3_price = entry_price * (1 + self.take_profit_tier3_pct)
            
            # Calculate quantities for each tier
            tier1_qty = round(quantity * self.take_profit_tier1_size_pct, 8)  # 33% of position
            tier2_qty = round(quantity * self.take_profit_tier2_size_pct, 8)  # 33% of position
            tier3_qty = round(quantity - tier1_qty - tier2_qty, 8)  # Remaining ~34%
            
            # Format prices according to symbol precision
            symbol_info = self.get_symbol_info(symbol)
            price_precision = 2  # Default
            
            if symbol_info:
                for filter_item in symbol_info.get("filters", []):
                    if filter_item["filterType"] == "PRICE_FILTER":
                        tick_size = float(filter_item["tickSize"])
                        price_precision = len(str(tick_size).rstrip('0').split('.')[-1])
                        break
            
            sl_price = round(sl_price, price_precision)
            tp_tier1_price = round(tp_tier1_price, price_precision)
            tp_tier2_price = round(tp_tier2_price, price_precision)
            tp_tier3_price = round(tp_tier3_price, price_precision)
            
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            # Place stop loss order
            self._respect_rate_limit()
            sl_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.STOP_LOSS.value,
                quantity=quantity,
                stopPrice=sl_price
                # No price parameter for market orders
            )
            
            # Place take profit orders for each tier
            tp_orders = []
            
            # Tier 1 take profit order
            self._respect_rate_limit()
            tp_tier1_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier1_qty,
                stopPrice=tp_tier1_price
                # No price parameter for market orders
            )
            tp_orders.append(tp_tier1_order)
            
            # Tier 2 take profit order
            self._respect_rate_limit()
            tp_tier2_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier2_qty,
                stopPrice=tp_tier2_price
                # No price parameter for market orders
            )
            tp_orders.append(tp_tier2_order)
            
            # Tier 3 take profit order
            self._respect_rate_limit()
            tp_tier3_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier3_qty,
                stopPrice=tp_tier3_price
                # No price parameter for market orders
            )
            tp_orders.append(tp_tier3_order)
            
            # Update position with SL/TP information
            self.open_positions[symbol].update({
                "sl_order_id": sl_order["orderId"],
                "tp_tier1_order_id": tp_tier1_order["orderId"],
                "tp_tier2_order_id": tp_tier2_order["orderId"],
                "tp_tier3_order_id": tp_tier3_order["orderId"],
                "sl_price": sl_price,
                "tp_tier1_price": tp_tier1_price,
                "tp_tier2_price": tp_tier2_price,
                "tp_tier3_price": tp_tier3_price,
                "tp_tier1_qty": tier1_qty,
                "tp_tier2_qty": tier2_qty,
                "tp_tier3_qty": tier3_qty,
                "profit_tiers": {
                    "tier1_hit": False,
                    "tier2_hit": False,
                    "tier3_hit": False
                }
            })
            
            logger.info(f"Placed SL/TP orders for {symbol}: " +
                      f"SL at {sl_price} (ID: {sl_order['orderId']}), " +
                      f"TP1 at {tp_tier1_price} (ID: {tp_tier1_order['orderId']}), " +
                      f"TP2 at {tp_tier2_price} (ID: {tp_tier2_order['orderId']}), " +
                      f"TP3 at {tp_tier3_price} (ID: {tp_tier3_order['orderId']})")
            
            return sl_order, tp_orders
            
        except BinanceAPIException as e:
            logger.error(f"API error placing SL/TP orders: {e}")
            return {}, {}
        except Exception as e:
            logger.error(f"Error placing SL/TP orders: {e}")
            return {}, {}

    def _cancel_sl_tp_orders(self, symbol: str) -> bool:
        """
        Cancel existing stop loss and take profit orders for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            True if successful, False otherwise
        """
        try:
            position = self.open_positions.get(symbol)
            if not position:
                return True
            
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            # List of order IDs to cancel
            order_ids_to_cancel = []
            
            # Collect SL/TP order IDs if they exist
            if "sl_order_id" in position:
                order_ids_to_cancel.append(position["sl_order_id"])
            if "tp_tier1_order_id" in position:
                order_ids_to_cancel.append(position["tp_tier1_order_id"])
            if "tp_tier2_order_id" in position:
                order_ids_to_cancel.append(position["tp_tier2_order_id"])
            if "tp_tier3_order_id" in position:
                order_ids_to_cancel.append(position["tp_tier3_order_id"])
            
            # Cancel each order
            canceled_count = 0
            for order_id in order_ids_to_cancel:
                try:
                    self._respect_rate_limit()
                    self.client.cancel_order(symbol=formatted_symbol, orderId=order_id)
                    canceled_count += 1
                    logger.info(f"Canceled order {order_id} for {symbol}")
                except BinanceAPIException as e:
                    # Order might already be filled or canceled
                    if e.code != -2011:  # Unknown order error code
                        logger.warning(f"Could not cancel order {order_id} for {symbol}: {e}")
                except Exception as e:
                    logger.warning(f"Error canceling order {order_id} for {symbol}: {e}")
            
            if canceled_count > 0:
                logger.info(f"Canceled {canceled_count} SL/TP orders for {symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error canceling SL/TP orders for {symbol}: {e}")
            return False
    
    def cancel_all_orders(self, symbol: str) -> bool:
        """
        Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            # Get all open orders for this symbol
            self._respect_rate_limit()
            open_orders = self.client.get_open_orders(symbol=formatted_symbol)
            
            if not open_orders:
                logger.info(f"No open orders to cancel for {symbol}")
                return True
            
            # Cancel each order individually
            canceled_count = 0
            for order in open_orders:
                try:
                    self._respect_rate_limit()
                    self.client.cancel_order(symbol=formatted_symbol, orderId=order['orderId'])
                    canceled_count += 1
                    logger.info(f"Canceled order {order['orderId']} for {symbol}")
                except BinanceAPIException as e:
                    logger.warning(f"Could not cancel order {order['orderId']} for {symbol}: {e}")
                except Exception as e:
                    logger.warning(f"Error canceling order {order['orderId']} for {symbol}: {e}")
            
            logger.info(f"Canceled {canceled_count}/{len(open_orders)} orders for {symbol}")
            return canceled_count > 0
            
        except BinanceAPIException as e:
            logger.error(f"API error canceling orders: {e}")
            return False
        except Exception as e:
            logger.error(f"Error canceling orders: {e}")
            return False
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open orders, optionally filtered by symbol.
        
        Args:
            symbol: Trading pair symbol (optional)
            
        Returns:
            List of open orders
        """
        try:
            self._respect_rate_limit()
            
            if symbol:
                # Format symbol (replace '/' if present)
                formatted_symbol = symbol.replace("/", "")
                orders = self.client.get_open_orders(symbol=formatted_symbol)
            else:
                orders = self.client.get_open_orders()
            
            return orders
            
        except BinanceAPIException as e:
            logger.error(f"API error getting open orders: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []
    
    def get_order_status(self, symbol: str, order_id: int) -> Dict:
        """
        Get the status of a specific order.
        
        Args:
            symbol: Trading pair symbol
            order_id: Order ID
            
        Returns:
            Dictionary with order information
        """
        try:
            # Format symbol (replace '/' if present)
            formatted_symbol = symbol.replace("/", "")
            
            self._respect_rate_limit()
            order = self.client.get_order(
                symbol=formatted_symbol,
                orderId=order_id
            )
            
            return order
            
        except BinanceAPIException as e:
            logger.error(f"API error getting order status: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return {}
    
    def load_open_positions(self):
        """
        Load existing open positions from the exchange.
        
        This method queries the exchange for current positions and updates
        the self.open_positions dictionary. It's called during initialization
        to handle cases where the bot restarts with existing open positions.
        Only positions for symbols configured in config.yml are tracked.
        
        If trade history data is available, it will be used for accurate entry prices.
        """
        logger.info("Loading existing positions from exchange...")
        try:
            # Get configured symbols from config
            configured_symbols = self.config.get('symbols', ['BTC/USDT', 'ETH/USDT'])
            # Create a set of base assets from configured symbols for faster lookups
            configured_assets = {symbol.split('/')[0] for symbol in configured_symbols}
            
            logger.info(f"Looking for positions for configured symbols: {configured_symbols}")
            
            # First check trade history for positions
            trade_history_positions = self.trade_history.get_open_positions()
            logger.info(f"Found {len(trade_history_positions)} positions in trade history")
            
            # Get account information with current positions
            self._respect_rate_limit()
            account_info = self.client.get_account()
            balances = account_info.get('balances', [])
            
            # Collect all non-zero balances for configured assets
            non_zero_balances = {}
            for balance in balances:
                asset = balance['asset']
                free = float(balance['free'])
                locked = float(balance['locked'])
                total = free + locked
                
                # Only consider assets with a non-zero balance that are in our configured symbols
                if total > 0 and asset in configured_assets:
                    non_zero_balances[asset] = total
            
            # Get current prices for these assets
            if non_zero_balances:
                self._respect_rate_limit()
                prices = self.client.get_all_tickers()
                price_dict = {item['symbol']: float(item['price']) for item in prices}
                
                # Update open positions dictionary
                for asset, quantity in non_zero_balances.items():
                    symbol = f"{asset}/USDT"  # Assume USDT as quote asset
                    formatted_symbol = f"{asset}USDT"
                    
                    # Only process if this is a configured symbol
                    if symbol in configured_symbols and formatted_symbol in price_dict:
                        current_price = price_dict[formatted_symbol]
                        
                        # Check if we have this position in trade history
                        if symbol in trade_history_positions:
                            # Use the data from trade history for accurate entry price
                            history_data = trade_history_positions[symbol]
                            entry_price = history_data['entry_price']
                            entry_time = history_data['entry_time']
                            order_id = history_data.get('order_id', 'unknown')
                            logger.info(f"Using trade history data for {symbol}: entry price {entry_price} from {entry_time}")
                        else:
                            # No history data, use current price as an estimate
                            entry_price = current_price
                            entry_time = datetime.now().isoformat()
                            order_id = 'unknown'
                            logger.info(f"No trade history for {symbol}, using current price {current_price} as entry price")
                            
                            # Since we detected a position but have no history, create one
                            self.trade_history.record_position_open(
                                symbol=symbol,
                                quantity=quantity,
                                entry_price=entry_price,
                                order_id=order_id,
                                timestamp=entry_time
                            )
                        
                        position_value = quantity * current_price
                        unrealized_pnl = (current_price - entry_price) * quantity
                        
                        # Add to open positions
                        self.open_positions[symbol] = {
                            "quantity": quantity,
                            "entry_price": entry_price,
                            "current_price": current_price,
                            "position_value": position_value,
                            "unrealized_pnl": unrealized_pnl,
                            "entry_time": entry_time,
                            "order_id": order_id,
                            "orders": {}  # Will store SL/TP order IDs
                        }
                        
                        logger.info(f"Loaded existing position for {symbol}: {quantity} @ {entry_price} " +
                                  f"(current: {current_price}, P/L: {unrealized_pnl:.2f} USDT)")
            
            if self.open_positions:
                logger.info(f"Loaded {len(self.open_positions)} existing positions for configured symbols")
            else:
                logger.info("No existing positions found for configured symbols")
                
        except BinanceAPIException as e:
            logger.error(f"API error loading positions: {e}")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")

    def check_daily_loss_cap(self) -> bool:
        """
        Check if the daily loss cap has been reached.
        
        Returns:
            True if loss cap is reached, False otherwise
        """
        # This would require tracking daily PnL and comparing with the cap
        # For MVP, we'll implement a simplified version
        return False
