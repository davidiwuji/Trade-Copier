import sys
import os
import argparse
import asyncio
from typing import List

# Force UTF-8 on Windows consoles to prevent cp1252 charmap encode errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.models import Signal
from src.config import config_mgr, ENV_PATH, CONFIG_PATH
from src.parser import SignalParser
from src.mt5_client import MT5Client, find_running_terminals
from src.telegram_listener import TelegramListener
from src.logger import (
    console,
    print_banner,
    print_signal_card,
    print_execution_results,
    print_filtered_message,
)
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm


def select_or_detect_terminal(args, app_config, interactive: bool = True):
    """
    Scans running MT5 terminal sessions and allows the user to interactively select which MT5 session to use.
    Returns: (target_path, target_login)
    """
    cli_path = getattr(args, "terminal", None)
    cli_login = getattr(args, "login", None)

    # If flags are provided via CLI, use them directly
    if cli_path and cli_login:
        return cli_path, cli_login

    running = find_running_terminals()

    if not running:
        console.print("[bold yellow][!] No active MT5 terminal instances were detected running.[/bold yellow]")
        console.print("Please open your MetaTrader 5 terminal on your desktop and log into your account.")
        if Confirm.ask("Would you like to re-scan for running terminals?", default=True):
            return select_or_detect_terminal(args, app_config, interactive=True)
        cfg_path = app_config.trading.target_path or config_mgr.mt5_path
        cfg_login = app_config.trading.target_login or config_mgr.mt5_login
        return cfg_path, cfg_login

    # If CLI explicitly passed a login, check if it matches a running terminal
    if cli_login:
        for inst in running:
            if inst.login == cli_login:
                return inst.path, inst.login

    # Always present interactive selection of running MT5 sessions
    console.print(f"\n[bold cyan]=== Select MT5 Session ({len(running)} active instance{'s' if len(running) > 1 else ''} detected) ===[/bold cyan]")
    table = Table(title="Available MT5 Sessions", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Login Account", style="bold green")
    table.add_column("Broker / Server", style="cyan")
    table.add_column("Balance", style="white")
    table.add_column("Algo Trading", style="magenta")
    table.add_column("Path", style="dim")

    for idx, inst in enumerate(running, start=1):
        login_str = str(inst.login) if inst.login else "Not Logged In"
        server_str = inst.server or "Unknown"
        bal_str = f"{inst.balance:.2f} {inst.currency}" if inst.balance is not None else "N/A"
        algo_str = "[green]Enabled[/green]" if inst.trade_allowed else "[red]Disabled[/red]"
        table.add_row(str(idx), login_str, server_str, bal_str, algo_str, inst.path)

    console.print(table)
    choice = Prompt.ask(
        "[bold magenta]Select the MT5 session to use[/bold magenta]",
        choices=[str(i) for i in range(1, len(running) + 1)],
        default="1",
    )
    chosen = running[int(choice) - 1]
    console.print(f"[bold green][OK] Selected Session #{choice}: Account #{chosen.login} ({chosen.server})[/bold green]\n")
    return chosen.path, chosen.login


def cmd_run(args):
    """Start the signal copier live listener."""
    print_banner()

    app_config = config_mgr.app_config
    channels = args.channels or app_config.channels

    if not channels:
        console.print("[bold red][!] No channels configured![/bold red]")
        console.print("Please add channels in [cyan]config.yaml[/cyan] or pass them via [yellow]--channels @channel1 @channel2[/yellow].")
        return

    # Check Telegram API credentials
    if not config_mgr.tg_api_id or not config_mgr.tg_api_hash:
        console.print("[bold red][!] Telegram credentials missing in .env[/bold red]")
        console.print("Run [bold cyan]python cli.py setup[/bold cyan] to configure your API ID and Hash.")
        return

    # Select / Auto-detect MT5 instance
    target_path, target_login = select_or_detect_terminal(args, app_config)

    # Initialize MT5
    console.print("\n[bold cyan][*] Initializing MetaTrader 5 connection...[/bold cyan]")
    mt5_client = MT5Client(app_config.trading, target_path=target_path, target_login=target_login)
    connected, info_msg = mt5_client.connect()

    mode_status = "[bold yellow]DRY-RUN (SIMULATION)[/bold yellow]" if app_config.trading.dry_run else "[bold red]LIVE EXECUTION[/bold red]"
    console.print(f"[*] MT5 Status: [bold green]{info_msg}[/bold green]")
    console.print(f"[*] Trading Mode: {mode_status}")
    console.print(f"[*] TP Strategy: [cyan]{app_config.trading.tp_strategy}[/cyan]")
    console.print(f"[*] Lot Sizing: [cyan]{app_config.trading.lot_mode} ({app_config.trading.fixed_lot} lots)[/cyan]")

    if not connected and not app_config.trading.dry_run:
        console.print("[bold red][!] Could not connect to MT5. Ensure MT5 is running on your system with 'Allow Algo Trading' turned ON.[/bold red]")
        if not Confirm.ask("Do you want to continue in DRY-RUN mode anyway?", default=True):
            return
        app_config.trading.dry_run = True

    # Signal handlers
    def on_signal_received(signal: Signal):
        print_signal_card(signal)
        console.print(f"[*] Routing signal to MT5 ({mode_status})...")
        results = mt5_client.execute_signal(signal)
        print_execution_results(results)

    def on_signal_filtered(channel: str, text: str, reason: str):
        print_filtered_message(channel, text, reason)

    # Initialize Telegram Listener
    listener = TelegramListener(
        channels=channels,
        on_signal=on_signal_received,
        on_filtered=on_signal_filtered,
        require_sl=app_config.trading.require_sl,
        duplicate_window=app_config.trading.duplicate_window_seconds,
    )

    console.print(f"\n[bold green][*] Connecting to Telegram and listening to {len(channels)} channels...[/bold green]")
    console.print("[dim]Press Ctrl+C to stop the copier at any time.\n[/dim]")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(listener.start_listening())
    except KeyboardInterrupt:
        console.print("\n[bold yellow][*] Stopping listener...[/bold yellow]")
    finally:
        mt5_client.disconnect()
        console.print("[bold green][*] Disconnected cleanly. Bye![/bold green]")


def cmd_test_parser(args):
    """Test signal parsing on custom text or interactively."""
    print_banner()
    console.print("[bold cyan]=== Telegram Signal Parser & Filter Tester ===[/bold cyan]\n")
    parser = SignalParser(require_sl=not args.ignore_sl)

    def evaluate_text(raw: str):
        signal, reason = parser.parse(raw, channel="TestChannel")
        if signal:
            print_signal_card(signal)
            console.print(f"[bold green][PASS] APPROVED AS TRADING SIGNAL[/bold green]: {reason}\n")
        else:
            console.print(f"[bold red][FILTERED][/bold red]: [yellow]{reason}[/yellow]\n")

    if args.text:
        evaluate_text(args.text)
        return

    console.print("Paste or type a telegram message to test (type [bold red]'exit'[/bold red] to quit):")
    while True:
        try:
            line = Prompt.ask("\n[bold magenta]Enter message[/bold magenta]")
            if line.strip().lower() in ["exit", "quit", "q"]:
                break
            evaluate_text(line)
        except (KeyboardInterrupt, EOFError):
            break


def cmd_test_mt5(args):
    """Test connection to MT5, check broker details and test order placement."""
    print_banner()
    console.print("[bold cyan]=== MetaTrader 5 Connectivity & Symbol Check ===[/bold cyan]\n")

    app_config = config_mgr.app_config
    target_path, target_login = select_or_detect_terminal(args, app_config)
    mt5_client = MT5Client(app_config.trading, target_path=target_path, target_login=target_login)
    connected, info_msg = mt5_client.connect()

    if not connected:
        console.print(f"[bold red][FAIL] Connection failed: {info_msg}[/bold red]")
        console.print("\n[yellow]Troubleshooting Tips:[/yellow]")
        console.print("1. Open MetaTrader 5 on your Windows desktop.")
        console.print("2. Ensure you are logged into your trading account.")
        console.print("3. In MT5: Tools -> Options -> Expert Advisors -> check 'Allow Algo Trading'.")
        return

    console.print(f"[bold green][OK] MT5 Connected successfully![/bold green]")
    acc = mt5_client.get_account_info()
    if acc:
        table = Table(title="MT5 Account Details", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="bold green")
        table.add_row("Login Account", str(acc.login))
        table.add_row("Server", str(acc.server))
        table.add_row("Balance", f"{acc.balance:.2f} {acc.currency}")
        table.add_row("Equity", f"{acc.equity:.2f} {acc.currency}")
        table.add_row("Leverage", f"1:{acc.leverage}")
        table.add_row("Algo Trading Enabled", str(acc.trade_expert))
        console.print(table)

    test_symbols = [args.symbol] if args.symbol else ["EURUSD", "XAUUSD", "GBPUSD", "US30"]
    console.print("\n[bold cyan]Checking Symbol Resolution & Ticks:[/bold cyan]")
    sym_table = Table(show_header=True)
    sym_table.add_column("Requested", style="yellow")
    sym_table.add_column("Broker Resolved", style="cyan")
    sym_table.add_column("Bid", style="green")
    sym_table.add_column("Ask", style="green")
    sym_table.add_column("Status", style="white")

    import MetaTrader5 as mt5
    for sym in test_symbols:
        resolved = mt5_client.resolve_symbol(sym)
        if resolved:
            tick = mt5.symbol_info_tick(resolved)
            bid_str = f"{tick.bid:.5f}" if tick else "N/A"
            ask_str = f"{tick.ask:.5f}" if tick else "N/A"
            sym_table.add_row(sym, resolved, bid_str, ask_str, "[green]Available[/green]")
        else:
            sym_table.add_row(sym, "Not Found", "-", "-", "[red]Missing[/red]")

    console.print(sym_table)
    mt5_client.disconnect()


def cmd_terminals(args):
    """Scan and list all active MT5 terminal instances, and optionally save a default target."""
    print_banner()
    console.print("[bold cyan]=== Active MetaTrader 5 Terminal Instances ===[/bold cyan]\n")

    running = find_running_terminals()
    if not running:
        console.print("[yellow][!] No running MT5 terminal64.exe instances found.[/yellow]")
        console.print("Ensure your MT5 application is open on the desktop.")
        return

    table = Table(title=f"Detected MT5 Instances ({len(running)} running)", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Login Account", style="bold green")
    table.add_column("Broker / Server", style="cyan")
    table.add_column("Balance", style="white")
    table.add_column("Algo Trading", style="magenta")
    table.add_column("Path", style="dim")
    table.add_column("PID", style="yellow")

    app_config = config_mgr.app_config
    target_path = app_config.trading.target_path or config_mgr.mt5_path
    target_login = app_config.trading.target_login or config_mgr.mt5_login

    for idx, inst in enumerate(running, start=1):
        login_str = str(inst.login) if inst.login else "Not Logged In"
        server_str = inst.server or "Unknown"
        bal_str = f"{inst.balance:.2f} {inst.currency}" if inst.balance is not None else "N/A"
        algo_str = "[green]Enabled[/green]" if inst.trade_allowed else "[red]Disabled[/red]"
        is_target = (inst.login == target_login) or (inst.path == target_path)
        tag = " [bold green](Default Target)[/bold green]" if is_target else ""
        table.add_row(str(idx), f"{login_str}{tag}", server_str, bal_str, algo_str, inst.path, str(inst.pid))

    console.print(table)

    if getattr(args, "set_target", False):
        choice = Prompt.ask(
            "\nSelect instance number to lock as permanent target in config.yaml",
            choices=[str(i) for i in range(1, len(running) + 1)],
            default="1",
        )
        selected = running[int(choice) - 1]
        app_config.trading.target_path = selected.path
        app_config.trading.target_login = selected.login
        config_mgr.save()
        console.print(f"[bold green][OK] Saved default target terminal: Account #{selected.login} at {selected.path}[/bold green]")
    else:
        console.print("\n[dim]Tips:[/dim]")
        console.print("  - To lock one instance as default: [cyan]python cli.py terminals --set-target[/cyan]")
        console.print("  - To launch copier targeting a specific account: [cyan]python cli.py run --login <ACCOUNT_NUMBER>[/cyan]")
        console.print("  - To launch copier targeting a specific path: [cyan]python cli.py run --terminal \"C:\\path\\terminal64.exe\"[/cyan]")


def cmd_list_channels(args):
    """Log in to Telegram and list all joined channels and groups with IDs."""
    print_banner()
    console.print("[bold cyan]=== Telegram Channels & Groups Finder ===[/bold cyan]\n")

    if not config_mgr.tg_api_id or not config_mgr.tg_api_hash:
        console.print("[bold red][!] Telegram credentials missing in .env[/bold red]")
        console.print("Run [bold cyan]python cli.py setup[/bold cyan] first.")
        return

    listener = TelegramListener(channels=[], on_signal=lambda s: None)

    async def list_routine():
        console.print("[*] Connecting to Telegram...")
        channels = await listener.list_available_channels()
        table = Table(title=f"Your Telegram Channels ({len(channels)} found)", show_header=True)
        table.add_column("Channel Title", style="cyan")
        table.add_column("Username / Handle", style="yellow")
        table.add_column("Channel ID", style="bold green")
        table.add_column("Type", style="dim")

        for ch in channels:
            u_name = f"@{ch['username']}" if ch['username'] else "(Private)"
            ch_type = "Channel" if ch['is_broadcast'] else "Group"
            table.add_row(ch['title'], u_name, str(ch['id']), ch_type)

        console.print(table)
        console.print("\n[dim]You can copy any Username or Channel ID directly into config.yaml[/dim]")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(list_routine())
    except KeyboardInterrupt:
        pass


def cmd_monitored_channels(args):
    """View all channels currently configured to be monitored by the copier."""
    print_banner()
    console.print("[bold cyan]=== Currently Monitored Telegram Channels ===[/bold cyan]\n")

    app_config = config_mgr.app_config
    channels = app_config.channels

    if not channels:
        console.print("[bold red][!] No channels are currently configured![/bold red]")
        console.print("Add channels in [cyan]config.yaml[/cyan] or run [bold cyan]python cli.py setup[/bold cyan].")
        return

    table = Table(title=f"Monitored Channels ({len(channels)} configured)", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Channel Target", style="bold yellow")
    table.add_column("Type / Format", style="cyan")
    table.add_column("Monitoring Status", style="green")

    for i, ch in enumerate(channels, 1):
        ch_str = str(ch).strip()
        if ch_str.startswith("@") or (isinstance(ch, str) and not ch_str.lstrip("-").isdigit()):
            ch_type = "Public Username / Handle" if ch_str.startswith("@") else "Title / Name"
        elif ch_str.lstrip("-").isdigit():
            ch_type = "Numeric Channel ID"
        else:
            ch_type = "Custom Identifier"
        table.add_row(str(i), ch_str, ch_type, "[bold green]Active[/bold green]")

    console.print(table)

    if getattr(args, "resolve", False):
        if not config_mgr.tg_api_id or not config_mgr.tg_api_hash:
            console.print("\n[yellow][!] To resolve live channel status, Telegram credentials must be configured in .env.[/yellow]")
        else:
            console.print("\n[*] Resolving channels with Telegram servers...")
            listener = TelegramListener(channels=channels, on_signal=lambda s: None)

            async def resolve_routine():
                resolved = await listener.resolve_channels()
                console.print(f"[bold green][OK] Successfully connected and resolved {len(resolved)} of {len(channels)} channel(s).[/bold green]")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(resolve_routine())
            except Exception as e:
                console.print(f"[bold red][!] Error during channel resolution: {e}[/bold red]")

    console.print("\n[dim]Tips:[/dim]")
    console.print("  - To add or remove channels, edit [cyan]config.yaml[/cyan]")
    console.print("  - To discover all channels your Telegram account is in, run: [bold cyan]python cli.py list-channels[/bold cyan]")
    if not getattr(args, "resolve", False):
        console.print("  - To test live resolution with Telegram servers, run: [bold cyan]python cli.py channels --resolve[/bold cyan]")


def cmd_setup(args):
    """Interactive wizard to configure Telegram credentials and settings."""
    print_banner()
    console.print("[bold cyan]=== Interactive Setup Wizard ===[/bold cyan]\n")

    console.print("To copy signals from Telegram, you need a Telegram API ID and API Hash.")
    console.print("1. Go to [bold cyan]https://my.telegram.org[/bold cyan]")
    console.print("2. Log in with your phone number and navigate to 'API development tools'.")
    console.print("3. Create an app (name it anything, e.g. 'SignalCopier') to get your api_id and api_hash.\n")

    curr_id = str(config_mgr.tg_api_id or "")
    curr_hash = config_mgr.tg_api_hash or ""
    curr_phone = config_mgr.tg_phone or ""

    api_id = Prompt.ask("Enter your Telegram API_ID", default=curr_id)
    api_hash = Prompt.ask("Enter your Telegram API_HASH", default=curr_hash)
    phone = Prompt.ask("Enter your Phone Number with country code (e.g. +1234567890)", default=curr_phone)

    # Write .env
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(f"TG_API_ID={api_id}\n")
        f.write(f"TG_API_HASH={api_hash}\n")
        f.write(f"TG_PHONE={phone}\n")

    console.print(f"\n[bold green][OK] Saved credentials to {ENV_PATH}[/bold green]")

    # Configure initial channels
    console.print("\n[bold cyan]Configuring Channels:[/bold cyan]")
    raw_channels = Prompt.ask(
        "Enter channel usernames or IDs separated by comma (or leave empty to edit config.yaml later)",
        default="",
    )
    if raw_channels.strip():
        ch_list = [c.strip() for c in raw_channels.split(",") if c.strip()]
        config_mgr.app_config.channels = ch_list
        config_mgr.save()
        console.print(f"[bold green][OK] Updated channels in {CONFIG_PATH}[/bold green]")

    console.print("\n[bold green]Setup completed successfully![/bold green]")
    console.print("Next steps:")
    console.print("  1. Run [cyan]python cli.py list-channels[/cyan] to view your channels.")
    console.print("  2. Run [cyan]python cli.py test-mt5[/cyan] to verify MT5 connection.")
    console.print("  3. Run [cyan]python cli.py run[/cyan] to start the copier!")


def main():
    parser = argparse.ArgumentParser(
        description="Telegram to MetaTrader 5 Signal Copier CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Start the live signal listener and copier")
    run_parser.add_argument(
        "--channels",
        nargs="+",
        help="Override channels to listen to (e.g. --channels @channel1 @channel2)",
    )
    run_parser.add_argument("--terminal", type=str, help="Specific MT5 terminal executable path to attach to")
    run_parser.add_argument("--login", type=int, help="Specific MT5 account login number to attach to")

    # Command: test-parser
    tp_parser = subparsers.add_parser("test-parser", help="Test signal extraction on custom messages")
    tp_parser.add_argument("--text", type=str, help="Single message text to test")
    tp_parser.add_argument("--ignore-sl", action="store_true", help="Allow signals without SL for testing")

    # Command: test-mt5
    mt5_parser = subparsers.add_parser("test-mt5", help="Check MT5 terminal connection and symbol ticks")
    mt5_parser.add_argument("--symbol", type=str, help="Specific symbol to check (e.g. XAUUSD)")
    mt5_parser.add_argument("--terminal", type=str, help="Specific MT5 terminal executable path to test")
    mt5_parser.add_argument("--login", type=int, help="Specific MT5 account login number to test")

    # Command: terminals (list and select running MT5 instances)
    term_parser = subparsers.add_parser("terminals", aliases=["instances"], help="List active MT5 terminal instances and configure target")
    term_parser.add_argument("--set-target", action="store_true", help="Interactively select and save an MT5 instance as default target")

    # Command: channels (view monitored channels)
    ch_parser = subparsers.add_parser("channels", aliases=["monitored"], help="View all channels currently configured to be monitored")
    ch_parser.add_argument("--resolve", action="store_true", help="Connect to Telegram and verify live resolution of channels")

    # Command: list-channels
    subparsers.add_parser("list-channels", help="List all Telegram channels/groups your account has joined")

    # Command: setup
    subparsers.add_parser("setup", help="Interactive setup wizard for API credentials and channels")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "run": cmd_run,
        "terminals": cmd_terminals,
        "instances": cmd_terminals,
        "channels": cmd_monitored_channels,
        "monitored": cmd_monitored_channels,
        "test-parser": cmd_test_parser,
        "test-mt5": cmd_test_mt5,
        "list-channels": cmd_list_channels,
        "setup": cmd_setup,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
