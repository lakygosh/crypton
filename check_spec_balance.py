"""
Check Testnet balance only for BTC, ETH, SUI and USDT.
"""
import os
from dotenv import load_dotenv
from binance.client import Client

TARGET_ASSETS = {"BTC", "ETH", "SUI", "USDT"}   # <-- dodali smo USDT

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
        account = client.get_account()
        balances = {b["asset"]: b for b in account["balances"] if b["asset"] in TARGET_ASSETS}

        print("\n=== BALANCES (BTC / ETH / SUI / USDT) ===")
        print("Asset\tFree\t\tLocked")
        print("-" * 36)
        for asset in TARGET_ASSETS:
            bal = balances.get(asset, {"free": "0", "locked": "0"})
            print(f"{asset}\t{bal['free']}\t{bal['locked']}")

        print("\n=== ESTIMATED VALUE IN USDT ===")
        total_value = 0.0
        for asset in TARGET_ASSETS:
            bal = balances.get(asset)
            if not bal:
                continue
            qty = float(bal["free"]) + float(bal["locked"])
            if qty == 0:
                continue

            if asset == "USDT":
                total_value += qty
                print(f"{asset}: {qty} USDT")
                continue

            try:
                price  = float(client.get_symbol_ticker(symbol=f"{asset}USDT")["price"])
                value  = qty * price
                total_value += value
                print(f"{asset}: {qty} × {price} = {value:.2f} USDT")
            except Exception:
                print(f"{asset}: {qty} (price unavailable)")

        print(f"\nTotal Estimated Value (BTC/ETH/SUI/USDT): {total_value:.2f} USDT")

    except Exception as exc:
        print(f"ERROR: {exc}")

if __name__ == "__main__":
    main()
