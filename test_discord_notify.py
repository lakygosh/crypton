import os
from dotenv import load_dotenv
from crypton.utils.logger import DiscordNotifier

# Učitaj .env varijable
load_dotenv()

# Inicijalizuj DiscordNotifier
webhook = os.getenv("DISCORD_WEBHOOK")
notifier = DiscordNotifier(webhook_url=webhook)

if __name__ == "__main__":
    test_message = "✅ Ovo je test poruka sa Crypton trading bota!"
    try:
        notifier.send_message(test_message)
        print("Test poruka je poslata na Discord!")
    except Exception as e:
        print(f"Greška pri slanju poruke: {e}")
