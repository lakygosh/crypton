"""
Check for open positions and pending orders on Binance Testnet.
"""
import os
from dotenv import load_dotenv
from binance.client import Client

def main():
    load_dotenv()

    api_key    = os.getenv("BINANCE_TESTNET_API_KEY")  or os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_API_SECRET")

    if not (api_key and api_secret):
        print("ERROR: API credentials not found in environment variables")
        return

    client = Client(api_key, api_secret)
    client.API_URL = "https://testnet.binance.vision/api"

    try:
        print("=== CHECKING OPEN ORDERS ===")
        open_orders = client.get_open_orders()
        if open_orders:
            for order in open_orders:
                print(f"Symbol: {order['symbol']}")
                print(f"  Order ID: {order['orderId']}")
                print(f"  Side: {order['side']}")
                print(f"  Type: {order['type']}")
                print(f"  Quantity: {order['origQty']}")
                print(f"  Price: {order['price']}")
                print(f"  Status: {order['status']}")
                print(f"  Time: {order['time']}")
                print("-" * 40)
        else:
            print("No open orders found.")

        print("\n=== CHECKING ACCOUNT INFO ===")
        account = client.get_account()
        
        # Show balances with locked amounts
        print("Balances with locked amounts:")
        for balance in account['balances']:
            free_amt = float(balance['free'])
            locked_amt = float(balance['locked'])
            if free_amt > 0 or locked_amt > 0:
                print(f"{balance['asset']}: Free={free_amt}, Locked={locked_amt}")

        print(f"\nAccount Type: {account.get('accountType', 'N/A')}")
        print(f"Can Trade: {account.get('canTrade', 'N/A')}")
        print(f"Can Withdraw: {account.get('canWithdraw', 'N/A')}")
        print(f"Can Deposit: {account.get('canDeposit', 'N/A')}")

        # Check trading status for specific symbols
        print("\n=== CHECKING SYMBOL INFO ===")
        target_symbols = ["ETHUSDT", "BTCUSDT", "SUIUSDT"]
        for symbol in target_symbols:
            try:
                symbol_info = client.get_symbol_info(symbol)
                print(f"{symbol}: Status = {symbol_info['status']}")
            except Exception as e:
                print(f"{symbol}: Error getting info - {e}")

    except Exception as exc:
        print(f"ERROR: {exc}")

if __name__ == "__main__":
    main() 