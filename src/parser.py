import re
from typing import Optional, List, Tuple
from src.models import Signal, OrderAction


# Known symbols and aliases
KNOWN_SYMBOLS = {
    # Metals
    "GOLD": "XAUUSD",
    "XAUUSD": "XAUUSD",
    "SILVER": "XAGUSD",
    "XAGUSD": "XAGUSD",
    # Indices
    "US30": "US30",
    "DJ30": "US30",
    "DJIA": "US30",
    "USA30": "US30",
    "WS30": "US30",
    "NAS100": "NAS100",
    "US100": "NAS100",
    "USTEC": "NAS100",
    "NASDAQ": "NAS100",
    "SPX500": "US500",
    "US500": "US500",
    "GER30": "GER40",
    "GER40": "GER40",
    "DAX": "GER40",
    "DE30": "GER40",
    "DE40": "GER40",
    "UK100": "UK100",
    # Commodities
    "OIL": "USOUSD",
    "WTI": "USOUSD",
    "BRENT": "UKOUSD",
    # Crypto
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
}

# Currency triplets for Forex regex
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]

# Noise / Recap / Marketing keywords that indicate this is NOT an entry signal
NON_SIGNAL_INDICATORS = [
    r"\bhit tp\b",
    r"\btp hit\b",
    r"\btp\d hit\b",
    r"\bsl hit\b",
    r"\bstop hit\b",
    r"\bpips\b.*\bgained\b",
    r"\bcongratulations\b",
    r"\bprofit booked\b",
    r"\bclose half\b",
    r"\bmove sl\b",
    r"\bbreak ?even\b",
    r"\brisk free\b",
    r"\bjoin (our|the)? ?vip\b",
    r"\bvip channel\b",
    r"\bdiscount\b",
    r"\brecap\b",
    r"\bweekly summary\b",
]


class SignalParser:
    def __init__(self, require_sl: bool = True):
        self.require_sl = require_sl

    def clean_text(self, text: str) -> str:
        """Strip markdown symbols, hashtags, normalize unicode dashes and whitespaces."""
        if not text:
            return ""
        # Normalize all unicode dashes/hyphens to ASCII '-'
        cleaned = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]", "-", text)
        # Strip bold/italic markdown characters and hashtags
        cleaned = re.sub(r"[\*\_`~#]", " ", cleaned)
        # Normalize multiple spaces and preserve linebreaks
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
        return "\n".join(line for line in lines if line)

    def is_non_signal(self, text: str) -> Tuple[bool, str]:
        """Detect whether a message is an announcement, trade update, or marketing noise."""
        lower = text.lower()
        for pattern in NON_SIGNAL_INDICATORS:
            if re.search(pattern, lower):
                return True, f"Matched update/recap pattern: '{pattern}'"
        return False, ""

    def extract_action(self, text: str) -> Optional[OrderAction]:
        """Extract order action (BUY, SELL, BUY LIMIT, SELL LIMIT, BUY STOP, SELL STOP)."""
        # First check pending orders
        pending_patterns = [
            (r"\bBUY\s+LIMIT\b", OrderAction.BUY_LIMIT),
            (r"\bSELL\s+LIMIT\b", OrderAction.SELL_LIMIT),
            (r"\bBUY\s+STOP\b", OrderAction.BUY_STOP),
            (r"\bSELL\s+STOP\b", OrderAction.SELL_STOP),
        ]
        for pattern, action in pending_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return action

        # Then check market orders
        # Match 'BUY NOW', 'SELL NOW', 'BUY', 'SELL', 'LONG', 'SHORT'
        # Ensure it's not preceded by 'DONT', 'NOT', 'HIT', 'WON', 'WHY'
        if re.search(r"(?<!don't\s)(?<!do not\s)(?<!why\s)(?<!hit\s)\b(?:BUY\s+NOW|BUY|LONG)\b", text, re.IGNORECASE):
            return OrderAction.BUY
        if re.search(r"(?<!don't\s)(?<!do not\s)(?<!why\s)(?<!hit\s)\b(?:SELL\s+NOW|SELL|SHORT)\b", text, re.IGNORECASE):
            return OrderAction.SELL

        return None

    def extract_symbol(self, text: str) -> Optional[str]:
        """Extract standard or known trading symbol."""
        # Check known words first (like GOLD, US30, NAS100, etc.)
        for alias, std_symbol in KNOWN_SYMBOLS.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, text, re.IGNORECASE):
                return std_symbol

        # Check standard Forex pairs (e.g. EUR/USD, EURUSD, GBPJPY)
        pair_pattern = r"\b(" + "|".join(CURRENCIES) + r")[ /]?(" + "|".join(CURRENCIES) + r")\b"
        match = re.search(pair_pattern, text, re.IGNORECASE)
        if match:
            base, quote = match.group(1).upper(), match.group(2).upper()
            if base != quote:
                return f"{base}{quote}"

        # General ticker pattern (e.g., XAUUSD, BTCUSD, US30, GER40)
        general_match = re.search(r"\b([A-Z]{3,6}(?:USD|EUR|GBP|JPY)?)\b", text)
        if general_match:
            candidate = general_match.group(1).upper()
            if candidate in KNOWN_SYMBOLS:
                return KNOWN_SYMBOLS[candidate]

        return None

    def extract_entry_price(self, text: str) -> Optional[float]:
        """Extract entry price if explicitly specified."""
        # Check range with optional Zone/Area/Level e.g. Entry Zone: 3994.03 - 3995.09
        range_match = re.search(
            r"(?:ENTRY|PRICE|@|NOW)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)\s*[-/]\s*([0-9]+\.?[0-9]*)",
            text,
            re.IGNORECASE,
        )
        if range_match:
            try:
                p1 = float(range_match.group(1))
                p2 = float(range_match.group(2))
                return round((p1 + p2) / 2.0, 5)
            except ValueError:
                pass

        patterns = [
            r"(?:ENTRY|PRICE|OPEN|AT|@)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)",
            r"(?:BUY|SELL|LIMIT|STOP)\s+(?:NOW\s+)?(?:@\s*)?([0-9]+\.?[0-9]*)",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if val > 0:
                        return val
                except ValueError:
                    continue

        return None

    def extract_stop_loss(self, text: str, action: Optional[OrderAction] = None) -> Optional[float]:
        """Extract Stop Loss (SL) price, handling single prices and zones/ranges."""
        # 1. Range / Zone e.g. SL Zone: 4000.98 - 4002.04
        range_pattern = r"(?:SL|S/L|STOP\s*LOSS|STOPLOSS|STOP|INVALIDATION)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)\s*[-/]\s*([0-9]+\.?[0-9]*)"
        range_match = re.search(range_pattern, text, re.IGNORECASE)
        if range_match:
            try:
                p1 = float(range_match.group(1))
                p2 = float(range_match.group(2))
                # For SELL: upper bound provides full zone protection; for BUY: lower bound
                if action and action.is_sell:
                    return max(p1, p2)
                elif action and action.is_buy:
                    return min(p1, p2)
                return max(p1, p2)
            except ValueError:
                pass

        # 2. Single price with optional Zone/Area
        single_pattern = r"(?:SL|S/L|STOP\s*LOSS|STOPLOSS|STOP|INVALIDATION)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)"
        match = re.search(single_pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return None

    def extract_take_profits(self, text: str, action: Optional[OrderAction] = None) -> List[float]:
        """Extract all Take Profit (TP) targets (TP1, TP2, TP3, or TP Zone)."""
        tps: List[float] = []

        # 1. Explicit numbered TPs e.g. TP1: 1.0950, TP 2 = 1.0980, Target 1: 2740
        numbered_patterns = re.findall(
            r"(?:TP\s*[0-9]|TAKE\s*PROFIT\s*[0-9]|TARGET\s*[0-9])(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)",
            text,
            re.IGNORECASE,
        )
        for num in numbered_patterns:
            try:
                val = float(num)
                if val not in tps and val > 0:
                    tps.append(val)
            except ValueError:
                continue

        if tps:
            return tps

        # 2. Check TP Zone / Range e.g. TP Zone: 3985.62 - 3986.68
        range_pattern = r"(?:TP|T/P|TAKE\s*PROFIT|TARGET)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)\s*[-/]\s*([0-9]+\.?[0-9]*)"
        range_match = re.search(range_pattern, text, re.IGNORECASE)
        if range_match:
            try:
                p1 = float(range_match.group(1))
                p2 = float(range_match.group(2))
                # Add closest target first based on trade direction
                if action and action.is_sell:
                    tps.append(max(p1, p2))
                    tps.append(min(p1, p2))
                elif action and action.is_buy:
                    tps.append(min(p1, p2))
                    tps.append(max(p1, p2))
                else:
                    tps.extend([p1, p2])
                return tps
            except ValueError:
                pass

        # 3. General TP / Take Profit / Target
        general_patterns = re.findall(
            r"(?:TP|T/P|TAKE\s*PROFIT|TARGET)(?:\s+(?:ZONE|AREA|LEVEL))?\s*[:=\-]?\s*([0-9]+\.?[0-9]*)",
            text,
            re.IGNORECASE,
        )
        for num in general_patterns:
            try:
                val = float(num)
                if val not in tps and val > 0:
                    tps.append(val)
            except ValueError:
                continue

        return tps

    def extract_lot(self, text: str) -> Optional[float]:
        """Extract suggested lot size if specified in signal."""
        match = re.search(r"(?:LOT|VOLUME|LOTS?)\s*[:=\-]?\s*([0-9]+\.?[0-9]*)", text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0.001 <= val <= 100.0:
                    return val
            except ValueError:
                pass
        return None

    def parse(self, text: str, channel: str = "") -> Tuple[Optional[Signal], str]:
        """
        Parses text to determine if it is an actionable trading signal.
        Returns: (Signal, reason_or_status)
        """
        if not text or len(text.strip()) < 5:
            return None, "Text too short to be a signal"

        cleaned = self.clean_text(text)

        # 1. Filter out announcements/updates/recaps/marketing
        is_junk, junk_reason = self.is_non_signal(cleaned)
        if is_junk:
            return None, f"Filtered: {junk_reason}"

        # 2. Extract Action
        action = self.extract_action(cleaned)
        if not action:
            return None, "Filtered: No valid trade action (BUY/SELL) found"

        # 3. Extract Symbol
        symbol = self.extract_symbol(cleaned)
        if not symbol:
            return None, "Filtered: No valid trading pair/symbol identified"

        # 4. Extract Stop Loss
        sl = self.extract_stop_loss(cleaned, action=action)
        if self.require_sl and sl is None:
            return None, "Filtered: Stop Loss (SL) is required but was not found"

        # 5. Extract Take Profits
        tps = self.extract_take_profits(cleaned, action=action)

        # 6. Extract Entry Price (optional for market orders)
        entry = self.extract_entry_price(cleaned)

        # 7. Extract Suggested Lot
        suggested_lot = self.extract_lot(cleaned)

        # 8. Basic sanity / logic check if both entry, SL, and TP exist
        if entry and sl:
            if action.is_buy and sl >= entry:
                return None, f"Filtered: Inconsistent BUY signal (SL {sl} >= Entry {entry})"
            if action.is_sell and sl <= entry:
                return None, f"Filtered: Inconsistent SELL signal (SL {sl} <= Entry {entry})"

        signal = Signal(
            symbol=symbol,
            action=action,
            entry_price=entry,
            stop_loss=sl,
            take_profits=tps,
            suggested_lot=suggested_lot,
            raw_text=text,
            channel=channel,
        )
        return signal, "Successfully parsed signal"
