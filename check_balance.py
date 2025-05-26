"""
Simple script to check your Binance Testnet account balance.
"""
import os
from decimal import Decimal
from dotenv import load_dotenv
from binance.client import Client
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
    
    try:
        # Get account information
        print("Fetching account information...")
        account = client.get_account()
        
        # Print account status
        print(f"\nAccount Status: {account['accountType']}")
        print(f"Can Trade: {account['canTrade']}")
        print(f"Can Withdraw: {account['canWithdraw']}")
        print(f"Can Deposit: {account['canDeposit']}")
        
        # Print balances
        print("\n=== BALANCES ===")
        print("Asset\t\tFree\t\tLocked")
        print("-" * 40)
        
        # Filter and sort balances that have non-zero amounts
        balances = sorted(
            [b for b in account['balances'] if float(b['free']) > 0 or float(b['locked']) > 0],
            key=lambda x: float(x['free']) + float(x['locked']),
            reverse=True
        )
        
        # Print them nicely formatted
        for balance in balances:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])
            print(f"{asset.ljust(8)}\t{str(free).ljust(16)}{locked}")
        
        # Get current prices for the assets with USDT
        print("\n=== ESTIMATED VALUES IN USDT ===")
        total_value = 0.0
        
        for balance in balances:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])
            total = free + locked
            
            # Skip USDT itself
            if asset == 'USDT':
                total_value += total
                print(f"{asset}: {total} USDT")
                continue
                
            # Skip assets with very small balances
            if total < 0.00001:
                continue
                
            try:
                # Try to get the price in USDT
                symbol = f"{asset}USDT"
                ticker = client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                value = total * price
                total_value += value
                print(f"{asset}: {total} × {price} = {value:.2f} USDT")
            except:
                # If that fails, just show the asset without USD value
                print(f"{asset}: {total} (price unavailable)")
        
        print(f"\nTotal Estimated Value: {total_value:.2f} USDT")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()
