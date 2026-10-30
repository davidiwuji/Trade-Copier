import unittest
from src.parser import SignalParser
from src.models import OrderAction


class TestSignalParser(unittest.TestCase):
    def setUp(self):
        self.parser = SignalParser(require_sl=True)

    def test_standard_gold_signal(self):
        msg = """
        🔥 GOLD BUY NOW @ 2742.50
        SL: 2735.00
        TP1: 2748.00
        TP2: 2755.00
        TP3: 2765.00
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNotNone(signal, f"Failed: {reason}")
        self.assertEqual(signal.symbol, "XAUUSD")
        self.assertEqual(signal.action, OrderAction.BUY)
        self.assertAlmostEqual(signal.entry_price, 2742.50)
        self.assertAlmostEqual(signal.stop_loss, 2735.00)
        self.assertEqual(len(signal.take_profits), 3)
        self.assertEqual(signal.take_profits[0], 2748.00)

    def test_forex_limit_order(self):
        msg = """
        EUR/USD SELL LIMIT @ 1.0880
        STOP LOSS: 1.0920
        TAKE PROFIT: 1.0820
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNotNone(signal, f"Failed: {reason}")
        self.assertEqual(signal.symbol, "EURUSD")
        self.assertEqual(signal.action, OrderAction.SELL_LIMIT)
        self.assertAlmostEqual(signal.entry_price, 1.0880)
        self.assertAlmostEqual(signal.stop_loss, 1.0920)
        self.assertEqual(signal.take_profits, [1.0820])

    def test_crypto_signal(self):
        msg = """
        🔴 SELL BTCUSD
        Entry: 68500
        SL: 69500
        TP: 66000
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNotNone(signal, f"Failed: {reason}")
        self.assertEqual(signal.symbol, "BTCUSD")
        self.assertEqual(signal.action, OrderAction.SELL)
        self.assertEqual(signal.stop_loss, 69500.0)
        self.assertEqual(signal.take_profits, [66000.0])

    def test_indices_signal(self):
        msg = """
        US30 BUY 42400
        SL: 42200
        TP: 42750
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNotNone(signal, f"Failed: {reason}")
        self.assertEqual(signal.symbol, "US30")
        self.assertEqual(signal.action, OrderAction.BUY)
        self.assertEqual(signal.stop_loss, 42200.0)

    def test_filter_marketing_message(self):
        msg = """
        🚀 Congratulations VIP members! GOLD HIT TP3 +150 PIPS!
        Join our VIP channel today for a 50% discount!
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNone(signal)
        self.assertIn("Filtered", reason)

    def test_filter_trade_management_update(self):
        msg = "Close half of your EURUSD position and move SL to entry breakeven."
        signal, reason = self.parser.parse(msg)
        self.assertIsNone(signal)
        self.assertIn("Filtered", reason)

    def test_filter_general_market_commentary(self):
        msg = "Good morning! EURUSD looks very bullish on the 4H chart today, keep an eye out."
        signal, reason = self.parser.parse(msg)
        self.assertIsNone(signal)
        self.assertIn("Filtered", reason)

    def test_filter_missing_stop_loss(self):
        msg = "BUY GBPUSD @ 1.3050 TP: 1.3150"
        signal, reason = self.parser.parse(msg)
        self.assertIsNone(signal)
        self.assertIn("Stop Loss (SL) is required", reason)

    def test_filter_inconsistent_signal(self):
        # Buy signal where SL is greater than Entry price
        msg = "BUY EURUSD @ 1.0800 SL: 1.0850 TP: 1.0900"
        signal, reason = self.parser.parse(msg)
        self.assertIsNone(signal)
        self.assertIn("Inconsistent BUY signal", reason)

    def test_ai_signals_zone_format(self):
        msg = """
        NEW POSITION OPENED
        🔴 #SELL #XAUUSD
        📍 Entry Zone: 3994.03–3995.09
        🛡️ #SL Zone: 4000.98–4002.04
        🎯 #TP Zone: 3985.62–3986.68
        🚀 Lot: 0.07
        ⚖️ R:R = 1:1.21
        🕐 11:00 (GMT+2)
        """
        signal, reason = self.parser.parse(msg)
        self.assertIsNotNone(signal, f"Failed: {reason}")
        self.assertEqual(signal.symbol, "XAUUSD")
        self.assertEqual(signal.action, OrderAction.SELL)
        self.assertAlmostEqual(signal.entry_price, 3994.56)
        self.assertAlmostEqual(signal.stop_loss, 4002.04)
        self.assertEqual(signal.take_profits, [3986.68, 3985.62])
        self.assertAlmostEqual(signal.suggested_lot, 0.07)


if __name__ == "__main__":
    unittest.main()
