"""
Script to sell BTC, ETH, and SUI to USDT on Binance Testnet.
"""
import os
import time
import math
from decimal import Decimal
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *
from loguru import logger

def main():
    # Load environment variables
    load_dotenv()
    
    # Get API credentials
    api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET")
    
    if not api_key or not api_secret:
        print("ERROR: API credentials not found in environment variables")
        return
    
    print(f"Using API key: {api_key[:5]}...{api_key[-5:]}")
    
    # Initialize Binance client for testnet
    client = Client(api_key=api_key, api_secret=api_secret)
    client.API_URL = 'https://testnet.binance.vision/api'
    
    # Symbols to sell
    symbols_to_sell = [
        {"symbol": "BTCUSDT", "asset": "BTC"},
        {"symbol": "ETHUSDT", "asset": "ETH"},
        {"symbol": "SUIUSDT", "asset": "SUI"}
    ]
    
    usdt_before = get_usdt_balance(client)
    print(f"USDT balance before selling: {usdt_before}")
    
    # Sell each cryptocurrency
    for crypto in symbols_to_sell:
        try:
            sell_all(client, crypto["symbol"], crypto["asset"])
        except Exception as e:
            print(f"Error selling {crypto['asset']}: {e}")
    
    # Wait a moment for orders to process
    print("Waiting for orders to process...")
    time.sleep(5)
    
    usdt_after = get_usdt_balance(client)
    print(f"USDT balance after selling: {usdt_after}")
    print(f"Gained approximately: {usdt_after - usdt_before} USDT")

def get_usdt_balance(client):
    """Get USDT balance from account."""
    account = client.get_account()
    for balance in account['balances']:
        if balance['asset'] == 'USDT':
            return float(balance['free'])
    return 0.0

def get_asset_balance(client, asset):
    """Get specific asset balance from account."""
    account = client.get_account()
    for balance in account['balances']:
        if balance['asset'] == asset:
            return float(balance['free'])
    return 0.0

def sell_all(client, symbol, asset):
    """Sell all of a specific asset for USDT."""
    # Get the balance
    balance = get_asset_balance(client, asset)
    
    if balance <= 0:
        print(f"No {asset} balance to sell")
        return
    
    print(f"Selling {balance} {asset}...")
    
    # Get symbol info to ensure valid quantity precision
    symbol_info = client.get_symbol_info(symbol)
    
    # Find the lot size filter
    lot_size = next((filter for filter in symbol_info['filters'] if filter['filterType'] == 'LOT_SIZE'), None)
    
    if lot_size:
        step_size = float(lot_size['stepSize'])
        # Calculate valid quantity based on step size
        precision = int(round(-1 * math.log10(step_size)))
        quantity = round_step_size(balance, step_size)
    else:
        # Fallback: just use 5 decimal places
        quantity = round(balance, 5)
    
    # Create a market sell order
    try:
        order = client.create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        
        print(f"Successfully placed order to sell {quantity} {asset}:")
        print(f"  Order ID: {order['orderId']}")
        print(f"  Status: {order['status']}")
        
        # Check fill details if available
        if 'fills' in order:
            total_value = sum(float(fill['price']) * float(fill['qty']) for fill in order['fills'])
            print(f"  Sold for approximately: {total_value} USDT")
        
        return order
    except Exception as e:
        print(f"Error creating sell order for {asset}: {e}")
        raise

def round_step_size(quantity, step_size):
    """Round a quantity to the nearest step size."""
    import math
    
    if step_size == 0:
        return quantity
        
    precision = int(round(-1 * math.log10(step_size)))
    quantity = math.floor(quantity * (10 ** precision)) / (10 ** precision)
    return quantity

if __name__ == "__main__":
    main()
