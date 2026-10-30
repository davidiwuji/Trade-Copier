from datetime import datetime
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.models import Signal, ExecutionResult

console = Console()


def print_banner():
    banner = Text()
    banner.append("====================================================\n", style="bold cyan")
    banner.append("      TELEGRAM -> METATRADER 5 SIGNAL COPIER       \n", style="bold white on blue")
    banner.append("====================================================", style="bold cyan")
    console.print(banner)


def print_signal_card(signal: Signal):
    table = Table(title="[bold green]New Trading Signal Detected[/bold green]", show_header=True, header_style="bold magenta")
    table.add_column("Channel", style="cyan")
    table.add_column("Symbol", style="bold yellow")
    table.add_column("Action", style="bold")
    table.add_column("Entry", style="white")
    table.add_column("Stop Loss", style="red")
    table.add_column("Take Profit(s)", style="green")

    action_style = "bold green" if signal.action.is_buy else "bold red"
    entry_str = f"{signal.entry_price:.5f}" if signal.entry_price else "MARKET (CMP)"
    sl_str = f"{signal.stop_loss:.5f}" if signal.stop_loss else "None"
    tps_str = ", ".join(f"{tp:.5f}" for tp in signal.take_profits) if signal.take_profits else "None"

    table.add_row(
        signal.channel or "Unknown",
        signal.symbol,
        f"[{action_style}]{signal.action.value}[/{action_style}]",
        entry_str,
        sl_str,
        tps_str,
    )
    console.print(table)


def print_execution_results(results: List[ExecutionResult]):
    for res in results:
        mode_tag = "[SIMULATED]" if res.simulated else "[LIVE]"
        if res.success:
            panel_content = (
                f"[bold green]SUCCESS {mode_tag}[/bold green]\n"
                f"Ticket: #{res.ticket}\n"
                f"Symbol: {res.symbol} | Action: {res.action} | Lot: {res.lot}\n"
                f"Execution Price: {res.price:.5f}\n"
                f"SL: {res.sl or 'None'} | TP: {res.tp or 'None'}\n"
                f"Comment: {res.comment}"
            )
            console.print(Panel(panel_content, border_style="green"))
        else:
            panel_content = (
                f"[bold red]EXECUTION FAILED {mode_tag}[/bold red]\n"
                f"Symbol: {res.symbol} | Action: {res.action}\n"
                f"Error: {res.error or 'Unknown error'}\n"
                f"RetCode: {res.retcode}"
            )
            console.print(Panel(panel_content, border_style="red"))


def print_filtered_message(channel: str, text: str, reason: str):
    preview = text.replace("\n", " ")[:60] + "..." if len(text) > 60 else text.replace("\n", " ")
    console.print(f"[dim yellow][Filtered][/dim yellow] [cyan][{channel}][/cyan] [dim]{reason}[/dim] -> \"{preview}\"")
