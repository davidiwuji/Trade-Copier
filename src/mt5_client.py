import math
from typing import Optional, List, Dict, Any, Tuple
import MetaTrader5 as mt5

from src.models import Signal, OrderAction, ExecutionResult, TradingConfig, TerminalInstance
from src.config import config_mgr


def find_running_terminals() -> List[TerminalInstance]:
    """Scans all active terminal64.exe processes and gathers their account and path info."""
    import psutil
    terminals: List[TerminalInstance] = []
    seen_paths = set()

    for p in psutil.process_iter(['name', 'exe']):
        try:
            pname = (p.name() or "").lower()
            if pname == 'terminal64.exe':
                exe_path = p.exe()
                if not exe_path or exe_path in seen_paths:
                    continue
                seen_paths.add(exe_path)

                inst = TerminalInstance(pid=p.pid, path=exe_path)
                try:
                    if mt5.initialize(path=exe_path):
                        acc = mt5.account_info()
                        term = mt5.terminal_info()
                        if acc:
                            inst.login = acc.login
                            inst.server = acc.server
                            inst.balance = acc.balance
                            inst.currency = acc.currency
                            inst.company = acc.company
                            inst.trade_allowed = acc.trade_expert
                        mt5.shutdown()
                except Exception:
                    pass

                terminals.append(inst)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return terminals


class MT5Client:
    def __init__(
        self,
        config: TradingConfig,
        target_path: Optional[str] = None,
        target_login: Optional[int] = None,
    ):
        self.config = config
        self.target_path = target_path or config.target_path or config_mgr.mt5_path
        self.target_login = target_login or config.target_login or config_mgr.mt5_login
        self._connected = False
        self._cached_broker_symbols: Dict[str, str] = {}

    def connect(self) -> Tuple[bool, str]:
        """Initialize connection to MetaTrader 5 terminal."""
        mt5_path = self.target_path
        mt5_login = self.target_login
        mt5_password = config_mgr.mt5_password
        mt5_server = config_mgr.mt5_server

        init_kwargs = {}
        if mt5_path:
            init_kwargs["path"] = mt5_path
        # mt5.initialize requires password and server when login is supplied programmatically
        if mt5_login and mt5_password and mt5_server:
            init_kwargs["login"] = mt5_login
            init_kwargs["password"] = mt5_password
            init_kwargs["server"] = mt5_server

        if init_kwargs:
            initialized = mt5.initialize(**init_kwargs)
        else:
            # Connect directly to the active MT5 program running on the system
            initialized = mt5.initialize()

        if not initialized:
            err = mt5.last_error()
            self._connected = False
            return False, f"MT5 initialization failed: {err}. Ensure MT5 is running and logged in."

        account = mt5.account_info()
        # If target login was requested, verify we attached to the right account
        if mt5_login and account and account.login != mt5_login:
            mt5.shutdown()
            self._connected = False
            return False, f"Connected to account #{account.login}, but target login is #{mt5_login}."

        self._connected = True
        self._cache_symbols()
        acc_str = f"Account #{account.login} ({account.server}) - Balance: {account.balance:.2f} {account.currency}" if account else "Connected"
        if mt5_path:
            acc_str += f" [Path: {mt5_path}]"
        return True, acc_str

    def disconnect(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected and mt5.terminal_info() is not None

    def get_account_info(self) -> Optional[Any]:
        if not self._connected:
            return None
        return mt5.account_info()

    def get_terminal_info(self) -> Optional[Any]:
        if not self._connected:
            return None
        return mt5.terminal_info()

    def _cache_symbols(self) -> None:
        """Cache all available symbols in the broker to quickly match suffixes/prefixes."""
        try:
            symbols = mt5.symbols_get()
            if symbols:
                self._cached_broker_symbols = {s.name.upper(): s.name for s in symbols}
        except Exception:
            self._cached_broker_symbols = {}

    def resolve_symbol(self, requested_symbol: str) -> Optional[str]:
        """
        Resolves requested symbol (e.g. GOLD, XAUUSD, EURUSD, US30) to the broker's specific symbol
        (e.g. XAUUSDm, US30m, USTECm) using broker symbol caching and alias mappings.
        """
        req = requested_symbol.upper().strip()

        if not self._cached_broker_symbols:
            self._cache_symbols()

        # Helper to check broker candidates
        def find_broker_match(candidate: str) -> Optional[str]:
            # Exact
            if candidate in self._cached_broker_symbols:
                return self._cached_broker_symbols[candidate]
            # Prefix/suffix (e.g. US30 -> US30m, EURUSD -> EURUSDm)
            if self.config.auto_detect_broker_suffix:
                prefix_matches = []
                for b_upper, b_exact in self._cached_broker_symbols.items():
                    if b_upper.startswith(candidate) or b_upper.endswith(candidate):
                        # Calculate extra length to prefer shorter suffixes (e.g. US30m over US30_x10m)
                        extra_len = abs(len(b_upper) - len(candidate))
                        prefix_matches.append((extra_len, b_exact))
                if prefix_matches:
                    prefix_matches.sort(key=lambda x: x[0])
                    return prefix_matches[0][1]
            return None

        # 1. Try direct candidate match
        match = find_broker_match(req)
        if match:
            mt5.symbol_select(match, True)
            return match

        # 2. Try mapped alias (e.g. GOLD -> XAUUSD, US30 -> DJ30, NAS100 -> USTEC)
        candidates = []
        if req in self.config.symbol_mappings:
            candidates.append(self.config.symbol_mappings[req].upper())

        # Common cross-broker equivalencies
        common_equivalents = {
            "GOLD": ["XAUUSD", "GOLD"],
            "SILVER": ["XAGUSD", "SILVER"],
            "US30": ["US30", "DJ30", "USA30", "WS30", "DJIA"],
            "DJ30": ["US30", "DJ30", "USA30", "WS30"],
            "NAS100": ["USTEC", "US100", "NAS100", "NDX"],
            "USTEC": ["NAS100", "USTEC", "US100"],
            "SPX500": ["US500", "SPX500", "SP500"],
            "US500": ["SPX500", "US500", "SP500"],
            "GER30": ["DE30", "GER30", "DE40", "GER40"],
            "GER40": ["DE40", "DE30", "GER40", "GER30"],
            "DE30": ["GER30", "DE30", "DE40"],
            "DE40": ["GER40", "DE40", "DE30"],
            "OIL": ["USOUSD", "WTI", "OIL", "USOIL", "CL"],
            "BRENT": ["UKOUSD", "BRENT", "UKOIL"],
            "BTC": ["BTCUSD", "BTCUSDT"],
            "ETH": ["ETHUSD", "ETHUSDT"],
        }
        if req in common_equivalents:
            candidates.extend(common_equivalents[req])

        for c in candidates:
            match = find_broker_match(c)
            if match:
                mt5.symbol_select(match, True)
                return match

        # Fallback to direct symbol_info
        s_info = mt5.symbol_info(req)
        if s_info:
            mt5.symbol_select(req, True)
            return req

        return None

    def _calculate_lot_size(self, symbol_info: Any, sl_price: Optional[float], entry_price: float) -> float:
        """Calculate appropriate lot size based on config mode and symbol limits."""
        lot = self.config.fixed_lot

        if self.config.lot_mode == "risk_percent" and sl_price and sl_price != entry_price:
            account = self.get_account_info()
            if account and account.equity > 0:
                risk_amount = (account.equity * (self.config.risk_percent / 100.0))
                price_delta = abs(entry_price - sl_price)
                points_at_risk = price_delta / symbol_info.point
                tick_value = symbol_info.trade_tick_value or 1.0
                tick_size = symbol_info.trade_tick_size or symbol_info.point
                loss_per_lot = (points_at_risk * symbol_info.point / tick_size) * tick_value
                if loss_per_lot > 0:
                    calculated_lot = risk_amount / loss_per_lot
                    lot = calculated_lot

        # Constrain to broker symbol limits and max_lot config
        lot = max(symbol_info.volume_min, min(lot, symbol_info.volume_max, self.config.max_lot))

        # Round to volume_step
        step = symbol_info.volume_step
        if step > 0:
            lot = math.floor(lot / step) * step
            # Format decimals properly based on step
            decimals = max(0, -int(math.floor(math.log10(step))))
            lot = round(lot, decimals)

        return lot

    def _determine_filling_mode(self, symbol_info: Any) -> int:
        """Determines compatible execution filling mode for the symbol."""
        modes = symbol_info.filling_mode
        # modes bitmask: 1 = FOK, 2 = IOC, 0/other = RETURN
        if modes & 2:  # ORDER_FILLING_IOC
            return mt5.ORDER_FILLING_IOC
        elif modes & 1:  # ORDER_FILLING_FOK
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def execute_signal(self, signal: Signal) -> List[ExecutionResult]:
        """
        Executes a parsed Signal on MT5 according to the configured TP strategy.
        Supports both live execution and safe simulation/dry-run mode.
        """
        if not self._connected:
            return [ExecutionResult(
                success=False,
                symbol=signal.symbol,
                action=signal.action.value,
                lot=0.0,
                price=0.0,
                comment=self.config.order_comment,
                error="MT5 is not connected. Cannot execute trade."
            )]

        # 1. Resolve Broker Symbol
        broker_symbol = self.resolve_symbol(signal.symbol)
        if not broker_symbol:
            return [ExecutionResult(
                success=False,
                symbol=signal.symbol,
                action=signal.action.value,
                lot=0.0,
                price=0.0,
                comment=self.config.order_comment,
                error=f"Symbol '{signal.symbol}' not found on your broker."
            )]

        symbol_info = mt5.symbol_info(broker_symbol)
        if not symbol_info:
            return [ExecutionResult(
                success=False,
                symbol=broker_symbol,
                action=signal.action.value,
                lot=0.0,
                price=0.0,
                comment=self.config.order_comment,
                error=f"Could not retrieve symbol info for '{broker_symbol}'."
            )]

        if not symbol_info.visible:
            mt5.symbol_select(broker_symbol, True)

        # 2. Determine base execution price & MT5 order type
        tick = mt5.symbol_info_tick(broker_symbol)
        if not tick and not self.config.dry_run:
            return [ExecutionResult(
                success=False,
                symbol=broker_symbol,
                action=signal.action.value,
                lot=0.0,
                price=0.0,
                comment=self.config.order_comment,
                error=f"Failed to get live market tick for '{broker_symbol}'."
            )]

        ask = tick.ask if tick else (signal.entry_price or 1.0)
        bid = tick.bid if tick else (signal.entry_price or 1.0)

        # Map OrderAction to MT5 constants
        if signal.action == OrderAction.BUY:
            mt5_action = mt5.TRADE_ACTION_DEAL
            order_type = mt5.ORDER_TYPE_BUY
            exec_price = ask
        elif signal.action == OrderAction.SELL:
            mt5_action = mt5.TRADE_ACTION_DEAL
            order_type = mt5.ORDER_TYPE_SELL
            exec_price = bid
        elif signal.action == OrderAction.BUY_LIMIT:
            mt5_action = mt5.TRADE_ACTION_PENDING
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
            exec_price = signal.entry_price or ask
        elif signal.action == OrderAction.SELL_LIMIT:
            mt5_action = mt5.TRADE_ACTION_PENDING
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
            exec_price = signal.entry_price or bid
        elif signal.action == OrderAction.BUY_STOP:
            mt5_action = mt5.TRADE_ACTION_PENDING
            order_type = mt5.ORDER_TYPE_BUY_STOP
            exec_price = signal.entry_price or ask
        elif signal.action == OrderAction.SELL_STOP:
            mt5_action = mt5.TRADE_ACTION_PENDING
            order_type = mt5.ORDER_TYPE_SELL_STOP
            exec_price = signal.entry_price or bid
        else:
            return [ExecutionResult(
                success=False,
                symbol=broker_symbol,
                action=signal.action.value,
                lot=0.0,
                price=0.0,
                comment=self.config.order_comment,
                error=f"Unsupported action '{signal.action.value}'."
            )]

        # 3. Calculate Lot Size
        total_lot = self._calculate_lot_size(symbol_info, signal.stop_loss, exec_price)

        # 4. Determine TP targets and order distribution
        # Options: first_only, split_lots, all_tps
        tps = signal.take_profits or [None]
        orders_plan: List[Tuple[float, Optional[float]]] = []

        if self.config.tp_strategy == "first_only" or not signal.take_profits:
            orders_plan.append((total_lot, signal.primary_tp))
        elif self.config.tp_strategy == "split_lots":
            num_tps = len(signal.take_profits)
            raw_lot_per_tp = total_lot / num_tps
            step = symbol_info.volume_step
            min_lot = symbol_info.volume_min
            lot_per_tp = max(min_lot, math.floor(raw_lot_per_tp / step) * step if step > 0 else raw_lot_per_tp)
            for tp in signal.take_profits:
                orders_plan.append((lot_per_tp, tp))
        elif self.config.tp_strategy == "all_tps":
            for tp in signal.take_profits:
                orders_plan.append((total_lot, tp))
        else:
            orders_plan.append((total_lot, signal.primary_tp))

        filling_mode = self._determine_filling_mode(symbol_info)
        results: List[ExecutionResult] = []

        # 5. Place each order
        for idx, (lot, tp_val) in enumerate(orders_plan, start=1):
            comment = f"{self.config.order_comment}-TP{idx}" if len(orders_plan) > 1 else self.config.order_comment

            request = {
                "action": mt5_action,
                "symbol": broker_symbol,
                "volume": lot,
                "type": order_type,
                "price": exec_price,
                "sl": signal.stop_loss or 0.0,
                "tp": tp_val or 0.0,
                "deviation": self.config.deviation,
                "magic": self.config.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            # DRY RUN / SIMULATION MODE
            if self.config.dry_run:
                # Validate order parameters against broker check without placing live order
                check_res = mt5.order_check(request) if self.is_connected() else None
                check_msg = f"Check code: {check_res.retcode}" if check_res else "Dry-run verified"
                results.append(ExecutionResult(
                    success=True,
                    ticket=9999000 + idx,
                    symbol=broker_symbol,
                    action=signal.action.value,
                    lot=lot,
                    price=exec_price,
                    sl=signal.stop_loss,
                    tp=tp_val,
                    retcode=0,
                    comment=comment,
                    simulated=True,
                    error=None,
                ))
                continue

            # LIVE ORDER SEND
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                results.append(ExecutionResult(
                    success=True,
                    ticket=res.order,
                    symbol=broker_symbol,
                    action=signal.action.value,
                    lot=res.volume,
                    price=res.price,
                    sl=signal.stop_loss,
                    tp=tp_val,
                    retcode=res.retcode,
                    comment=comment,
                    simulated=False,
                ))
            else:
                retcode = res.retcode if res else -1
                last_err = mt5.last_error()
                comment_err = res.comment if res else str(last_err)
                results.append(ExecutionResult(
                    success=False,
                    ticket=None,
                    symbol=broker_symbol,
                    action=signal.action.value,
                    lot=lot,
                    price=exec_price,
                    sl=signal.stop_loss,
                    tp=tp_val,
                    retcode=retcode,
                    comment=comment,
                    error=f"Order failed (retcode {retcode}): {comment_err}",
                    simulated=False,
                ))

        return results

    def close_position(self, ticket: int) -> Tuple[bool, str]:
        """Closes an open position by ticket number."""
        if not self._connected:
            return False, "MT5 not connected"

        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False, f"Position #{ticket} not found"

        p = pos[0]
        symbol = p.symbol
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return False, f"Could not retrieve symbol info for {symbol}"

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return False, f"Could not retrieve tick for {symbol}"

        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if is_buy else tick.ask
        filling_mode = self._determine_filling_mode(symbol_info)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": p.volume,
            "type": close_type,
            "price": close_price,
            "deviation": self.config.deviation,
            "magic": self.config.magic_number,
            "comment": "Close-Signal",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            return True, f"Position #{ticket} closed at {res.price}"
        return False, f"Failed to close position: {res.comment if res else mt5.last_error()}"
