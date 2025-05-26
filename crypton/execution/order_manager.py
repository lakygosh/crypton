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
        
        # Open positions tracking
        self.open_positions: Dict[str, Dict] = {}
        
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
            
            self._respect_rate_limit()
            order = self.client.create_order(
                symbol=formatted_symbol,
                side=side.value,
                type=OrderType.MARKET.value,
                quantity=quantity
            )
            
            logger.info(f"Placed {side.value} market order for {quantity} {symbol}: {order['orderId']}")
            
            # Update open positions
            if side == OrderSide.BUY and order.get("status") in [OrderStatus.FILLED.value, OrderStatus.PARTIALLY_FILLED.value]:
                self.open_positions[symbol] = {
                    "order_id": order["orderId"],
                    "quantity": float(order["executedQty"]),
                    "entry_price": float(order["fills"][0]["price"]) if order.get("fills") else 0.0,
                    "entry_time": datetime.now(),
                    "side": side.value
                }
                
                # Place stop loss and take profit orders
                self._place_sl_tp_orders(symbol)
            
            # Remove from open positions if selling
            if side == OrderSide.SELL and symbol in self.open_positions:
                del self.open_positions[symbol]
            
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
                stopPrice=sl_price,
                price=sl_price  # Limit price
            )
            
            # Place take profit orders for each tier
            tp_orders = []
            
            # Tier 1 take profit order (33% at 2%)
            self._respect_rate_limit()
            tp_tier1_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier1_qty,
                stopPrice=tp_tier1_price,
                price=tp_tier1_price  # Limit price
            )
            tp_orders.append(tp_tier1_order)
            
            # Tier 2 take profit order (33% at 3%)
            self._respect_rate_limit()
            tp_tier2_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier2_qty,
                stopPrice=tp_tier2_price,
                price=tp_tier2_price  # Limit price
            )
            tp_orders.append(tp_tier2_order)
            
            # Tier 3 take profit order (34% at 4%)
            self._respect_rate_limit()
            tp_tier3_order = self.client.create_order(
                symbol=formatted_symbol,
                side=OrderSide.SELL.value,
                type=OrderType.TAKE_PROFIT.value,
                quantity=tier3_qty,
                stopPrice=tp_tier3_price,
                price=tp_tier3_price  # Limit price
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
            
            self._respect_rate_limit()
            result = self.client.cancel_all_orders(symbol=formatted_symbol)
            
            logger.info(f"Canceled all orders for {symbol}")
            return True
            
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
    
    def check_daily_loss_cap(self) -> bool:
        """
        Check if the daily loss cap has been reached.
        
        Returns:
            True if loss cap is reached, False otherwise
        """
        # This would require tracking daily PnL and comparing with the cap
        # For MVP, we'll implement a simplified version
        return False
