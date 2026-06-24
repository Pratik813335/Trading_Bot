# tests/test_optimizer.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from engine.analysis_orchestrator import AnalysisOrchestrator
from storage.signal_repository_v2 import JsonlSignalRepository
from core.risk import build_trade_plan
from engine.signal_engine_v2 import SignalEngineV2
from engine.models import SyncStatus, StructureState

class MockRepository:
    def __init__(self, history):
        self.history = history
    def read_recent(self, limit=30):
        return self.history[:limit]

def test_auto_tune_parameters():
    # Setup temp state
    opt_file = Path("storage/optimizer_state.json")
    if opt_file.exists():
        try:
            opt_file.unlink()
        except Exception:
            pass
            
    # Mock trade history (low win rate: 3 losses, 0 wins)
    history = [
        {"symbol": "EURUSD", "outcome": "SL_HIT", "logged_at": "2026-06-25T00:00:00Z"},
        {"symbol": "EURUSD", "outcome": "SL_HIT", "logged_at": "2026-06-25T00:01:00Z"},
        {"symbol": "EURUSD", "outcome": "SL_HIT", "logged_at": "2026-06-25T00:02:00Z"},
    ]
    
    mock_repo = MockRepository(history)
    
    # Initialize orchestrator partially
    orchestrator = AnalysisOrchestrator(
        market_feed=None,
        indicator_engine=None,
        structure_engine=None,
        zone_engine=None,
        signal_engine=None,
        renderer=None,
        signal_repository=mock_repo
    )
    
    # Run tuner
    orchestrator.auto_tune_parameters("EURUSD")
    
    assert opt_file.exists(), "Tuner did not create optimizer_state.json"
    offsets = json.loads(opt_file.read_text(encoding="utf-8"))
    
    # Verify offsets are tuned up (capital protection active)
    assert offsets.get("min_score_offset", 0.0) > 0.0, "min_score_offset should be adjusted up"
    assert offsets.get("sl_atr_offset", 0.0) > 0.0, "sl_atr_offset should be adjusted up"
    
    # Verify risk plan applies the offsets
    zones = []
    nearest_zone = lambda a, b, c, below=True: None
    atr_val = 0.0010
    
    # Calculate SL with dynamic multiplier
    stop_loss_1, tp_1, rr_1 = build_trade_plan("BUY", 1.1000, atr_val, zones, {}, nearest_zone)
    
    # Reset offsets to zero
    opt_file.write_text(json.dumps({"min_score_offset": 0.0, "sl_atr_offset": 0.0}), encoding="utf-8")
    stop_loss_2, tp_2, rr_2 = build_trade_plan("BUY", 1.1000, atr_val, zones, {}, nearest_zone)
    
    # Tuned SL should be wider (more pips away from entry, meaning lower value on BUY)
    assert stop_loss_1 < stop_loss_2, f"Tuned SL {stop_loss_1} should be lower (wider) than baseline SL {stop_loss_2}"
    
    # Clean up
    if opt_file.exists():
        try:
            opt_file.unlink()
        except Exception:
            pass

if __name__ == "__main__":
    print("Executing Optimizer Unit Tests...")
    try:
        test_auto_tune_parameters()
        print("  [PASS] test_auto_tune_parameters")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [FAIL] test_auto_tune_parameters: {e}")
        raise e
