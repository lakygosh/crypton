"""
Notification helpers for the Crypton trading bot.

This module contains helper functions for sending notifications
across different channels like Discord and Slack.
"""
from typing import Optional, Dict
from crypton.utils.logger import DiscordNotifier, SlackNotifier, logger

# Global instances
discord = DiscordNotifier()
slack = SlackNotifier()

def notify_trade_execution(
    symbol: str, 
    side: str, 
    price: float, 
    quantity: float, 
    order_id: Optional[str] = None
):
    """
    Send trade execution notification to all configured channels.
    
    Args:
        symbol: Trading pair symbol
        side: Order side (BUY or SELL)
        price: Execution price
        quantity: Order quantity
        order_id: Order ID (optional)
    """
    logger.info(f"Executed {side} order for {symbol}: {quantity} @ {price}")
    
    # Send to Slack
    slack.notify_trade(
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        order_id=order_id
    )
    
    # Send to Discord
    discord.notify_trade(
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        order_id=order_id
    )

def notify_trade_completed(
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    profit: float,
    profit_pct: float
):
    """
    Send trade completion notification with profit/loss info.
    
    Args:
        symbol: Trading pair symbol
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        profit: Profit/loss amount
        profit_pct: Profit/loss percentage
    """
    logger.info(f"Trade completed for {symbol}: Profit=${profit:.2f} ({profit_pct:.2f}%)")
    
    # Send to Discord
    discord.notify_trade_completed(
        symbol=symbol,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        profit=profit,
        profit_pct=profit_pct
    )

def notify_error(error_message: str, details: Optional[str] = None):
    """
    Send error notification to all configured channels.
    
    Args:
        error_message: Error message
        details: Additional error details (optional)
    """
    logger.error(f"Error: {error_message}")
    
    # Send to Slack
    slack.notify_error(error_message, details)
    
    # Send to Discord
    discord.notify_error(error_message, details)
