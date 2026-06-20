from config import INITIAL_BALANCE, RISK_PER_TRADE

class Trader:

    def __init__(self):
        self.balance = INITIAL_BALANCE

    def position_size(self, entry, sl):
        if entry == sl:
            return 0

        risk = self.balance * RISK_PER_TRADE
        return round(risk / abs(entry - sl), 2)

    def execute(self, signal, entry, sl, tp):
        qty = self.position_size(entry, sl)

        print("\n=== TRADE EXECUTED ===")
        print("Type:", signal)
        print("Entry:", entry)
        print("SL:", sl)
        print("TP:", tp)
        print("Qty:", qty)
