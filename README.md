# Crypton

A fully-automated crypto trading bot focused on mean-reversion using Bollinger Bands and RSI on Binance markets.

## Features

- Mean-reversion strategy with Bollinger Bands + RSI
- Backtesting capabilities using historical data
- Paper trading with Binance testnet
- Live trading with risk management
- Metrics and logging

## Tech Stack

- Python 3.12
- CCXT for exchange abstraction
- pandas and pandas-ta for data manipulation and indicators
- backtrader for backtesting
- Prometheus and Grafana for metrics

## Project Structure

```
crypton/
├── crypton/
│   ├── data/         # Data fetching and handling
│   ├── indicators/   # Technical indicators (BB, RSI, SMA)
│   ├── strategy/     # Trading strategy implementation
│   ├── execution/    # Order execution
│   ├── backtesting/  # Backtesting framework
│   └── utils/        # Utilities and helpers
├── tests/            # Unit and integration tests
├── docs/             # Documentation
├── pyproject.toml    # Project dependencies
└── .env.sample       # Environment variables template
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/crypton.git
cd crypton
```

2. Install the package in development mode:
```bash
pip install -e ".[dev]"
```

3. Copy `.env.sample` to `.env` and fill in your Binance API credentials:
```bash
cp .env.sample .env
# Edit .env with your credentials
```

## Usage

### Backtesting

```bash
python -m crypton.main backtest --config config.yml
```

### Paper Trading (Testnet)

```bash
python -m crypton.main trade --mode test --config config.yml
```

### Live Trading

```bash
python -m crypton.main trade --mode live --config config.yml
```

## Development

Set up pre-commit hooks:

```bash
pre-commit install
```

Run tests:

```bash
pytest
```

## License

MIT
