"""
Logging utilities for the Crypton trading bot.

This module configures structured logging via Loguru and provides
utilities for Slack webhook notifications.
"""
import json
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Union

import requests
from loguru import logger

from crypton.utils.config import load_config


_LOGGER_INITIALIZED = False

def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = True,
    debug_mode: bool = False
) -> None:
    """
    Configure and set up the Loguru logger.
    
    Args:
        log_level: Logging level (default: INFO)
        log_file: Path to log file (optional)
        json_format: Whether to use JSON format for structured logging
    """
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return
    # Remove default logger
    logger.remove()
    _LOGGER_INITIALIZED = True
    
    # Get log level from environment if not provided
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO")
    
    # Override log level if debug_mode is enabled
    if debug_mode:
        log_level = "DEBUG"
        logger.info(f"Debug mode enabled, setting log level to {log_level}")
    
    # Temporarily force non-JSON format for debugging
    current_json_format = False
    
    # Define format based on preference
    if current_json_format:
        log_format = lambda record: json.dumps({
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["name"],
            "function": record["function"],
            "line": record["line"]
        }) + "\n"
    else:
        log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    
    # Add console logger
    logger.add(
        sys.stderr,
        format=log_format,
        level=log_level,
        colorize=not current_json_format
    )
    
    # Add file logger if specified
    if log_file:
        logger.add(
            log_file,
            format=log_format,
            level=log_level,
            rotation="10 MB",
            retention="7 days"
        )
    
    logger.info(f"Logger initialized with level={log_level}, json_format={current_json_format}, debug_mode={debug_mode}")


class SlackNotifier:
    """
    Slack notification utility for sending alerts and updates.
    
    Supports sending trade notifications, error alerts, and daily reports
    via Slack webhook.
    """
    
    def __init__(self, webhook_url: Optional[str] = None, enabled: bool = True):
        """
        Initialize the Slack notifier.
        
        Args:
            webhook_url: Slack webhook URL
            enabled: Whether notifications are enabled
        """
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK")
        self.enabled = enabled and bool(self.webhook_url)
        
        if self.enabled:
            logger.info("Slack notifications enabled")
        else:
            logger.info("Slack notifications disabled")
    
    def send_message(
        self, 
        message: str, 
        attachments: Optional[list] = None,
        color: str = "#36a64f"  # Default to green
    ) -> bool:
        """
        Send a message to Slack.
        
        Args:
            message: Message text
            attachments: List of attachment dictionaries (optional)
            color: Color for the attachment (default: green)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled, not sending message")
            return False
        
        try:
            # Prepare payload
            payload = {
                "text": message,
                "username": "Crypton Bot",
                "icon_emoji": ":robot_face:"
            }
            
            # Add attachments if provided
            if attachments:
                payload["attachments"] = attachments
            
            # Send request
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                logger.debug(f"Slack notification sent: {message}")
                return True
            else:
                logger.warning(f"Failed to send Slack notification: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    def notify_trade(
        self, 
        symbol: str, 
        side: str, 
        price: float, 
        quantity: float,
        order_id: Optional[str] = None
    ) -> bool:
        """
        Send trade notification.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            price: Execution price
            quantity: Order quantity
            order_id: Order ID (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Determine color and emoji based on side
        if side.upper() == "BUY":
            color = "#36a64f"  # Green
            emoji = ":chart_with_upwards_trend:"
        else:
            color = "#e01e5a"  # Red
            emoji = ":chart_with_downwards_trend:"
        
        # Format message
        message = f"{emoji} *{side.upper()} Order Executed*"
        
        # Prepare attachment
        attachment = {
            "color": color,
            "fields": [
                {
                    "title": "Symbol",
                    "value": symbol,
                    "short": True
                },
                {
                    "title": "Price",
                    "value": f"${price:.2f}",
                    "short": True
                },
                {
                    "title": "Quantity",
                    "value": f"{quantity:.6f}",
                    "short": True
                },
                {
                    "title": "Total",
                    "value": f"${price * quantity:.2f}",
                    "short": True
                }
            ],
            "footer": f"Order ID: {order_id}" if order_id else None,
            "ts": int(datetime.now().timestamp())
        }
        
        return self.send_message(message, [attachment], color)


class DiscordNotifier:
    """
    Discord notification utility for sending alerts and updates.
    
    Supports sending trade notifications, error alerts, and profit reports
    via Discord webhook.
    """
    
    def __init__(self, webhook_url: Optional[str] = None, enabled: bool = True):
        """
        Initialize the Discord notifier.
        
        Args:
            webhook_url: Discord webhook URL
            enabled: Whether notifications are enabled
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK")
        self.enabled = enabled and bool(self.webhook_url)
        
        if self.enabled:
            logger.info("Discord notifications enabled")
        else:
            logger.info("Discord notifications disabled")
    
    def send_message(self, content: str, embeds: Optional[list] = None) -> bool:
        """
        Send a message to Discord.
        
        Args:
            content: Message text
            embeds: List of embed dictionaries (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.debug("Discord notifications disabled, not sending message")
            return False
        
        try:
            # Prepare payload
            payload = {
                "content": content,
                "username": "Crypton Bot"
            }
            
            # Add embeds if provided
            if embeds:
                payload["embeds"] = embeds
            
            # Send request
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 204:
                logger.debug(f"Discord notification sent: {content}")
                return True
            else:
                logger.warning(f"Failed to send Discord notification: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
    
    def notify_trade(self, symbol: str, side: str, price: float, quantity: float, order_id: Optional[str] = None) -> bool:
        """
        Send trade notification.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY or SELL)
            price: Execution price
            quantity: Order quantity
            order_id: Order ID (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Determine color and emoji based on side
        if side.upper() == "BUY":
            color = 0x36a64f  # Green in decimal
            title = "🟢 BUY Order Executed"
        else:
            color = 0xe01e5a  # Red in decimal
            title = "🔴 SELL Order Executed"
        
        # Prepare embed
        embed = {
            "title": title,
            "color": color,
            "fields": [
                {
                    "name": "Symbol",
                    "value": symbol,
                    "inline": True
                },
                {
                    "name": "Price",
                    "value": f"${price:.2f}",
                    "inline": True
                },
                {
                    "name": "Quantity",
                    "value": f"{quantity:.6f}",
                    "inline": True
                },
                {
                    "name": "Total",
                    "value": f"${price * quantity:.2f}",
                    "inline": True
                }
            ],
            "footer": {
                "text": f"Order ID: {order_id}" if order_id else "Crypton Trading Bot"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return self.send_message(f"New {side.upper()} order for {symbol}", [embed])
    
    def notify_trade_completed(self, symbol: str, entry_price: float, exit_price: float, quantity: float, profit: float, profit_pct: float) -> bool:
        """
        Send trade completion notification with profit/loss info.
        
        Args:
            symbol: Trading pair symbol
            entry_price: Entry price
            exit_price: Exit price
            quantity: Trade quantity
            profit: Profit/loss amount
            profit_pct: Profit/loss percentage
            
        Returns:
            True if successful, False otherwise
        """
        # Determine color based on profit/loss
        if profit >= 0:
            color = 0x36a64f  # Green in decimal
            title = "✅ TRADE COMPLETED - PROFIT"
        else:
            color = 0xe01e5a  # Red in decimal
            title = "❌ TRADE COMPLETED - LOSS"
        
        # Prepare embed
        embed = {
            "title": title,
            "color": color,
            "fields": [
                {
                    "name": "Symbol",
                    "value": symbol,
                    "inline": True
                },
                {
                    "name": "Entry Price",
                    "value": f"${entry_price:.2f}",
                    "inline": True
                },
                {
                    "name": "Exit Price",
                    "value": f"${exit_price:.2f}",
                    "inline": True
                },
                {
                    "name": "Quantity",
                    "value": f"{quantity:.6f}",
                    "inline": True
                },
                {
                    "name": "Profit/Loss",
                    "value": f"${profit:.2f} ({profit_pct:.2f}%)",
                    "inline": True
                }
            ],
            "footer": {
                "text": "Crypton Trading Bot"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return self.send_message(f"Trade completed for {symbol} with {profit:.2f}$ {'profit' if profit >= 0 else 'loss'}", [embed])
    
    def notify_error(self, error_message: str, details: Optional[str] = None) -> bool:
        """
        Send error notification.
        
        Args:
            error_message: Error message
            details: Additional error details (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Prepare embed
        embed = {
            "title": "⚠️ Error Alert",
            "color": 0xe01e5a,  # Red in decimal
            "fields": [
                {
                    "name": "Error",
                    "value": error_message
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        # Add details if provided
        if details:
            embed["fields"].append({
                "name": "Details",
                "value": details
            })
        
        return self.send_message("Error encountered", [embed])
    
    def notify_error(self, error_message: str, details: Optional[str] = None) -> bool:
        """
        Send error notification.
        
        Args:
            error_message: Error message
            details: Additional error details (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Format message
        message = f":warning: *Error Alert*"
        
        # Prepare attachment
        attachment = {
            "color": "#e01e5a",  # Red
            "fields": [
                {
                    "title": "Error",
                    "value": error_message
                }
            ],
            "ts": int(datetime.now().timestamp())
        }
        
        # Add details if provided
        if details:
            attachment["fields"].append({
                "title": "Details",
                "value": details
            })
        
        return self.send_message(message, [attachment], "#e01e5a")
    
    def send_daily_report(
        self,
        total_trades: int,
        profit_loss: float,
        win_rate: float,
        metrics: Optional[Dict] = None
    ) -> bool:
        """
        Send daily performance report.
        
        Args:
            total_trades: Number of trades executed
            profit_loss: Total profit/loss amount
            win_rate: Percentage of winning trades
            metrics: Additional metrics dictionary (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Determine color based on profit/loss
        color = "#36a64f" if profit_loss >= 0 else "#e01e5a"
        
        # Format message
        message = f":bar_chart: *Daily Performance Report*"
        
        # Prepare attachment
        attachment = {
            "color": color,
            "fields": [
                {
                    "title": "Date",
                    "value": datetime.now().strftime("%Y-%m-%d"),
                    "short": True
                },
                {
                    "title": "Total Trades",
                    "value": str(total_trades),
                    "short": True
                },
                {
                    "title": "Profit/Loss",
                    "value": f"${profit_loss:.2f}",
                    "short": True
                },
                {
                    "title": "Win Rate",
                    "value": f"{win_rate:.1f}%",
                    "short": True
                }
            ],
            "ts": int(datetime.now().timestamp())
        }
        
        # Add additional metrics if provided
        if metrics:
            for key, value in metrics.items():
                # Format the value based on type
                if isinstance(value, float):
                    formatted_value = f"{value:.2f}"
                else:
                    formatted_value = str(value)
                
                attachment["fields"].append({
                    "title": key.replace("_", " ").title(),
                    "value": formatted_value,
                    "short": True
                })
        
        return self.send_message(message, [attachment], color)
