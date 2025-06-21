"""
Cancel all open orders on Binance Testnet to free up locked balances.
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
        print("=== CHECKING OPEN ORDERS BEFORE CANCELLATION ===")
        open_orders = client.get_open_orders()
        if open_orders:
            print(f"Found {len(open_orders)} open orders:")
            for order in open_orders:
                print(f"  {order['symbol']}: {order['side']} {order['type']} - Qty: {order['origQty']} - Price: {order.get('price', 'N/A')} - Stop: {order.get('stopPrice', 'N/A')} - ID: {order['orderId']}")
        else:
            print("No open orders found.")
            return

        print("\n=== CANCELLING ALL ORDERS ===")
        
        # Cancel each order individually
        for order in open_orders:
            try:
                result = client.cancel_order(
                    symbol=order['symbol'],
                    orderId=order['orderId']
                )
                print(f"✓ Canceled order {order['orderId']} for {order['symbol']} ({order['side']} {order['type']})")
                    
            except Exception as e:
                print(f"✗ Error canceling order {order['orderId']} for {order['symbol']}: {e}")

        print("\n=== CHECKING OPEN ORDERS AFTER CANCELLATION ===")
        remaining_orders = client.get_open_orders()
        if remaining_orders:
            print(f"⚠ Warning: {len(remaining_orders)} orders still open:")
            for order in remaining_orders:
                print(f"  {order['symbol']}: {order['side']} {order['type']} - ID: {order['orderId']}")
        else:
            print("✓ All orders successfully canceled!")

        print("\n=== CHECKING BALANCES AFTER CANCELLATION ===")
        account = client.get_account()
        target_assets = {"BTC", "ETH", "SUI", "USDT"}
        
        print("Asset\tFree\t\tLocked")
        print("-" * 32)
        for balance in account['balances']:
            if balance['asset'] in target_assets:
                free_amt = float(balance['free'])
                locked_amt = float(balance['locked'])
                if free_amt > 0 or locked_amt > 0:
                    print(f"{balance['asset']}\t{free_amt}\t{locked_amt}")

    except Exception as exc:
        print(f"ERROR: {exc}")

if __name__ == "__main__":
    main() 