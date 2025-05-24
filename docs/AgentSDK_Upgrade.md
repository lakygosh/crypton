# Uputstvo za korišćenje **OpenAI Agent SDK‑a** u projektu *crypton*

*(v1.0 — maj 2025)*

---

## 1. Uvod

OpenAI **Agent SDK** omogućava da kreiraš „razmišljajuće“ agente koji mogu primati poruke, koristiti sopstvene alate (funkcije) i vraćati odluke. U kontekstu *crypton* bota, agent služi da donese odluku **BUY / SELL / HOLD** ili da optimizuje parametre strategije.

## 2. Preduslovi

| Stavka                | Verzija / Napomena                 |
| --------------------- | ---------------------------------- |
| Python                | ≥ 3.12                             |
| openai                | ≥ 1.14 (sadrži Agent SDK)          |
| ccxt / python‑binance | Za izvršavanje naloga              |
| `OPENAI_API_KEY`      | Aktivni ključ sa dovoljnim kvotama |

```bash
pip install --upgrade openai ccxt python-binance "python-dotenv>=1.0"
```

## 3. Ključni pojmovi

| Pojam         | Opis                                                                                    |
| ------------- | --------------------------------------------------------------------------------------- |
| **Assistant** | Agent definisan promptom i listom alata (tools).                                        |
| **Tool**      | Python funkcija označena dekoratorom `@tool`; agent je može pozvati.                    |
| **Thread**    | Sesija poruka između tebe i agenta. Svaki `run()` vraća odgovor + eventualni tool‑call. |

## 4. Struktura direktorijuma (minimalno)

```
crypton/
 └─ agent/
     ├─ __init__.py
     ├─ tools.py        # buy, sell, hold, log
     └─ assistant.py    # definicija Assistant‑a
```

## 5. Kreiranje alata (`tools.py`)

```python
from openai import tool
import crypton.execution.binance_exec as exec

@tool
def place_buy(symbol: str, size_pct: float):
    """Market‑buy <size_pct>% equity na SYMBOL‑u."""
    return exec.place_order(symbol, "BUY", size_pct)

@tool
def place_sell(symbol: str, size_pct: float):
    """Market‑sell <size_pct>% equity na SYMBOL‑u."""
    return exec.place_order(symbol, "SELL", size_pct)

@tool
def hold():
    """Ne preduzimaj akciju."""
    return "HOLD"
```

## 6. Definisanje agenta (`assistant.py`)

```python
from openai import Assistant
from .tools import place_buy, place_sell, hold

assistant = Assistant(
    instructions="""
    You are a conservative crypto‑trading agent. Decide whether to BUY, SELL or HOLD.
    Use exactly one tool per decision and provide a short reasoning via hold() if no trade.
    """,
    model="gpt-4o",
    tools=[place_buy, place_sell, hold]
)

# helper

def decide(context: dict) -> str:
    thread = assistant.new_thread()
    user_msg = "\n".join(f"{k}: {v}" for k, v in context.items())
    result = thread.run(messages=[{"role": "user", "content": user_msg}])
    return result.content  # sadrži rezultat tool‑a
```

## 7. Slanje konteksta agentu

```python
context = {
    "symbol": "BTC/USDT",
    "price": 64700.12,
    "rsi": 28.5,
    "bb_lower": 64500,
    "bb_upper": 66000,
    "trend": "sideways",
    "volatility": "low",
    "rule_signal": "BUY"
}
print(decide(context))
```

## 8. Integracija u `mean_reversion.py`

1. Izračunaj standardni BB + RSI signal.
2. Napravi `context` i prosledi ga agentu.
3. Obavi trade samo ako agent pozove `place_buy` ili `place_sell`.
4. Loguj dobijeni odgovor radi audit‑traila.

## 9. Testiranje

* **Unit test**: mock `openai.Assistant` → potvrdi da se poziva tačan alat.
* **Backtest**: pokreni strategiju u dva moda (`ai.enabled = true/false`) i uporedi KPI‑eve.

## 10. Rukovanje greškama

| Scenario                      | Rešenje                                               |
| ----------------------------- | ----------------------------------------------------- |
| Latencija > 1 s               | Prelude‑timeout → fallback na rule‑based.             |
| `openai.error.RateLimitError` | Exponential back‑off (max 60 s) + Discord upozorenje. |
| Tool poziv bez parametara     | Validiraj ulaz u dekoratoru `@tool`.                  |

## 11. Sigurnost

* Čuvaj privatni Ed25519 ključ van repoa (`chmod 600`).
* `OPENAI_API_KEY` u Vault‑u ili `.env` (git‑ignored).
* Whitelistuj VPS IP na Binance‑u.

## 12. Produkciono okruženje

* Dodaj varijable u systemd service (`EnvironmentFile=/opt/crypton/.env`).
* Health‑check endpoint (`/healthz`) vraća „OK“ ako WS i Assistant rade.
* Prometheus metričke sonde: `ai_decision_seconds`, `ai_override_total`.

## 13. Debug & Observability

```shell
# Praćenje živih logova
journalctl -u crypton.service -f | jq '.msg'
```

* Dodaj `--verbose` flag da ispiše pun Assistant odgovor.

## 14. Česta pitanja (FAQ)

1. **Q:** Koliko košta poziv Agent SDK‑a?
   **A:** Naplaćuje se po tokenu kao standardni ChatCompletion.
2. **Q:** Koliko alata mogu registrovati?
   **A:** Teoretski 128, ali drži < 10 radi brzine.
3. **Q:** Mogu li imati više modela?
   **A:** Da, definiši više `Assistant` instanci (npr. `gpt-4o` za odluke, `o4-mini` za log‑rezime).

## 15. Sledeći koraci

* Fine‑tunuj prompt da smanjiš over‑trading.
* Dodaj tool `propose_params()` da agent šalje nove BB/RSI pragove → persistiraj i backtestuj.
* Eksperimentiši sa RL‑HF (reinforcement learning from human feedback) na rezultatima bota.

---