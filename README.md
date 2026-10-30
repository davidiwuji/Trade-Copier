# Telegram to MetaTrader 5 (MT5) Signal Copier CLI

An intelligent, production-ready CLI application that listens to your configured Telegram channels, filters out marketing, commentary, and non-signals, extracts actionable trade parameters (Symbol, Action, Entry, Stop Loss, Take Profits), and executes trades automatically on your open **MetaTrader 5** terminal.

---

## 🌟 Key Features

- **Automated Telegram Channel Listening**: Listens to public channels, private channels, or supergroups using Telethon.
- **Smart Signal Parsing & Filtering**:
  - Differentiates actionable trade signals from marketing announcements, results, recaps, and commentary.
  - Recognizes `BUY`, `SELL`, `BUY LIMIT`, `SELL LIMIT`, `BUY STOP`, `SELL STOP`.
  - Normalizes common asset aliases (`GOLD` -> `XAUUSD`, `US30` -> `US30m/DJ30`, `NAS100` -> `USTECm`, `OIL` -> `USOUSD`, etc.).
  - Extracts Entry (or market execution CMP), Stop Loss, and multiple Take Profits (`TP1`, `TP2`, `TP3`, ...).
  - Enforces sanity checks (e.g., checks that SL is on the correct side of the entry).
- **Direct MetaTrader 5 Native Integration**:
  - Automatically attaches to your already open and logged-in MT5 terminal on Windows.
  - **Smart Broker Symbol Auto-Resolution**: Automatically matches broker-specific symbol suffixes (e.g., `EURUSDm`, `XAUUSDm`, `EURUSD.pro`, `US30m`).
  - Adapts to broker execution filling modes (`IOC`, `FOK`, `RETURN`).
- **Flexible Lot Sizing & Risk Management**:
  - **Fixed Lot**: Configurable fixed volume per trade (e.g., `0.01`).
  - **Risk Percentage**: Computes lot size dynamically based on account equity and Stop Loss distance in points (e.g., risk 1% per trade).
  - Maximum lot cap safeguard (`max_lot`).
- **Multiple Take Profit Strategies**:
  - `first_only`: Opens a single position targeting TP1 (highest hit rate).
  - `split_lots`: Splits the calculated lot size equally across all parsed TPs.
  - `all_tps`: Places separate orders for each TP using the fixed lot size.
- **Safety Safeguards**:
  - **Dry-Run (Simulation Mode)**: Enabled by default so you can test parsing and parameter checks with live market data without risking real funds.
  - **Duplicate Signal Guardrail**: Ignores identical signals sent within a sliding time window (prevents duplicate orders from forwarded/reposted messages).
  - **Mandatory SL Filter**: Rejects signals without Stop Loss to protect your capital.

---

## 📂 Project Structure

```
tg-mt5-signal-copier/
├── cli.py                     # Main CLI command center
├── config.yaml                # Trading configuration, channels, and safeguards
├── .env                       # Telegram API credentials (API_ID, API_HASH, Phone)
├── .env.example               # Example credentials template
├── requirements.txt           # Python dependencies
├── src/
│   ├── config.py              # Configuration loader & environment manager
│   ├── models.py              # Pydantic data models for Signals and Orders
│   ├── parser.py              # Signal regex & rule-based filtering engine
│   ├── mt5_client.py          # MT5 bridge, broker symbol matcher, lot calculator
│   ├── telegram_listener.py   # Telethon async channel listener
│   ├── duplicate_filter.py    # Sliding-window anti-spam duplicate filter
│   └── logger.py              # Rich terminal cards, tables, and colored logs
└── tests/
    └── test_parser.py         # Unit tests for signal parser
```

---

## 🚀 Quick Start Guide

### 1. Requirements
- Windows 10/11
- MetaTrader 5 installed and open with **Allow Algo Trading** enabled (`Tools` -> `Options` -> `Expert Advisors` -> check *Allow Algo Trading*).
- Python 3.10+ (a virtual environment is already prepared at `.venv/`).

### 2. Activate Virtual Environment
In PowerShell:
```powershell
.\.venv\Scripts\activate
```

### 3. Step 1: Run the Interactive Setup Wizard
Run the setup command to configure your Telegram API credentials and channel list:
```powershell
python cli.py setup
```
> **How to get Telegram API credentials:**
> 1. Visit [https://my.telegram.org](https://my.telegram.org) and log in with your phone number.
> 2. Click on **API development tools**.
> 3. Create an application (App title: `SignalCopier`, Short name: `copier`).
> 4. Copy your `api_id` and `api_hash`.

### 4. Step 2: View Configured Monitored Channels & Discover Others
To view the channels the copier is currently set up to monitor:
```powershell
python cli.py channels
```
*(Add `--resolve` to verify connectivity and resolve IDs with Telegram servers: `python cli.py channels --resolve`)*

To search and discover all other channels, private groups, and supergroups your Telegram account has joined:
```powershell
python cli.py list-channels
```
This displays a table containing each channel's **Title**, **Username / Handle**, and **Channel ID** (e.g., `-1001234567890`).

### 5. Step 3: Test MT5 Connectivity
Verify MT5 connectivity, account balance, and broker symbol matching:
```powershell
python cli.py test-mt5
```

### 6. Step 4: Test Signal Parsing (Dry-run Sandbox)
You can test arbitrary Telegram signal messages interactively or with `--text`:
```powershell
# Test a valid Gold signal
python cli.py test-parser --text "GOLD BUY NOW @ 4005.00 SL 3995.00 TP1 4015.00 TP2 4025.00"

# Test a marketing message (should be rejected/filtered)
python cli.py test-parser --text "Congratulations to VIP members! GOLD HIT TP3 +150 pips! Join VIP today for 50% discount."

# Interactive test loop (type or paste messages live)
python cli.py test-parser
```

### 7. Step 5: Multi-Instance MT5 Selection
If you have multiple MT5 terminals running on your machine:
```powershell
# List all running MT5 terminals, accounts, and paths:
python cli.py terminals

# Interactively pick and lock an MT5 terminal as the permanent default:
python cli.py terminals --set-target

# Run the copier targeting a specific account number:
python cli.py run --login 81964092

# Run the copier targeting a specific terminal path:
python cli.py run --terminal "C:\Program Files\MetaTrader 5\terminal64.exe"
```
*(If multiple instances are running and none is preconfigured, the copier will display an interactive menu asking which terminal to connect to).*

### 8. Step 6: Start Live Signal Monitoring
To start monitoring your configured channels:
```powershell
python cli.py run
```
You can also override channels directly from the command line:
```powershell
python cli.py run --channels @MyForexSignals -1001987654321
```

---

## ⚙️ Configuration (`config.yaml`)

Edit `config.yaml` to customize your trading preferences:

```yaml
# Channels to monitor: usernames, links, or numeric IDs
channels:
  - "ForexSignalsVIP"
  - -1001234567890

trading:
  # Set to false to execute real orders with real money
  dry_run: true

  # Lot size mode: 'fixed' or 'risk_percent'
  lot_mode: "fixed"
  fixed_lot: 0.01
  risk_percent: 1.0  # % of equity risked based on SL distance
  max_lot: 0.50

  # Deviation in points (slippage tolerance)
  deviation: 30

  # Take Profit Strategy:
  #  - 'first_only': 1 order targeting TP1 (recommended)
  #  - 'split_lots': split lot size evenly across all TPs (e.g., 0.02 -> 0.01 TP1, 0.01 TP2)
  #  - 'all_tps': separate orders for each TP using fixed_lot
  tp_strategy: "first_only"

  # Safeguards
  require_sl: true
  duplicate_window_seconds: 300
  auto_detect_broker_suffix: true
```

---

## 🧪 Running Unit Tests
To run the signal parsing test suite:
```powershell
python -m unittest tests/test_parser.py
```
