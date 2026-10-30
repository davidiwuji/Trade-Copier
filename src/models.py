from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field


class OrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY LIMIT"
    SELL_LIMIT = "SELL LIMIT"
    BUY_STOP = "BUY STOP"
    SELL_STOP = "SELL STOP"

    @property
    def is_pending(self) -> bool:
        return "LIMIT" in self.value or "STOP" in self.value

    @property
    def is_buy(self) -> bool:
        return "BUY" in self.value

    @property
    def is_sell(self) -> bool:
        return "SELL" in self.value


class Signal(BaseModel):
    symbol: str
    action: OrderAction
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profits: List[float] = Field(default_factory=list)
    suggested_lot: Optional[float] = None
    raw_text: str = ""
    channel: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    notes: Optional[str] = None

    @property
    def primary_tp(self) -> Optional[float]:
        return self.take_profits[0] if self.take_profits else None

    def summary(self) -> str:
        entry_str = f"@{self.entry_price:.5f}" if self.entry_price else "@CMP"
        sl_str = f"SL: {self.stop_loss:.5f}" if self.stop_loss else "SL: None"
        tps_str = "TPs: [" + ", ".join(f"{tp:.5f}" for tp in self.take_profits) + "]" if self.take_profits else "TP: None"
        return f"{self.symbol} | {self.action.value} {entry_str} | {sl_str} | {tps_str}"


class ExecutionResult(BaseModel):
    success: bool
    ticket: Optional[int] = None
    symbol: str
    action: str
    lot: float
    price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    retcode: int = 0
    comment: str = ""
    error: Optional[str] = None
    simulated: bool = False


class TerminalInstance(BaseModel):
    pid: int
    path: str
    login: Optional[int] = None
    server: Optional[str] = None
    balance: Optional[float] = None
    currency: Optional[str] = None
    company: Optional[str] = None
    trade_allowed: bool = True


class TradingConfig(BaseModel):
    dry_run: bool = True
    lot_mode: str = "fixed"
    fixed_lot: float = 0.01
    risk_percent: float = 1.0
    max_lot: float = 0.50
    deviation: int = 30
    magic_number: int = 882026
    order_comment: str = "TG-Signal"
    tp_strategy: str = "first_only"
    require_sl: bool = True
    duplicate_window_seconds: int = 300
    auto_detect_broker_suffix: bool = True
    target_path: Optional[str] = None
    target_login: Optional[int] = None
    symbol_mappings: Dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):
    channels: List[Union[str, int]] = Field(default_factory=list)
    trading: TradingConfig = Field(default_factory=TradingConfig)
