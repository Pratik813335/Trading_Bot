# tests/run_tests.py
import sys
import os

# Add parent directory to sys.path so we can import modules correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_strategies import (
    test_trend_following_buy,
    test_scalping_squeeze,
    test_range_trading,
    test_carry_trade,
    test_order_block_detection,
    test_structure_aware_sl,
    test_choch_scoring
)
from tests.test_signal_pipeline import (
    test_feed_quality_rejects_stale_data,
    test_feed_quality_rejects_missing_candles,
    test_feed_quality_rejects_large_gap_count,
    test_feed_quality_rejects_high_latency
)

if __name__ == "__main__":
    print("Executing Trading Bot Unit Tests...")
    passed = True
    
    try:
        test_trend_following_buy()
        print("  [PASS] test_trend_following_buy")
    except Exception as e:
        print(f"  [FAIL] test_trend_following_buy: {e}")
        passed = False
        
    try:
        test_scalping_squeeze()
        print("  [PASS] test_scalping_squeeze")
    except Exception as e:
        print(f"  [FAIL] test_scalping_squeeze: {e}")
        passed = False
        
    try:
        test_range_trading()
        print("  [PASS] test_range_trading")
    except Exception as e:
        print(f"  [FAIL] test_range_trading: {e}")
        passed = False
        
    try:
        test_carry_trade()
        print("  [PASS] test_carry_trade")
    except Exception as e:
        print(f"  [FAIL] test_carry_trade: {e}")
        passed = False

    try:
        test_order_block_detection()
        print("  [PASS] test_order_block_detection")
    except Exception as e:
        print(f"  [FAIL] test_order_block_detection: {e}")
        passed = False

    try:
        test_structure_aware_sl()
        print("  [PASS] test_structure_aware_sl")
    except Exception as e:
        print(f"  [FAIL] test_structure_aware_sl: {e}")
        passed = False

    try:
        test_choch_scoring()
        print("  [PASS] test_choch_scoring")
    except Exception as e:
        print(f"  [FAIL] test_choch_scoring: {e}")
        passed = False

    # Pipeline Feed Quality Tests
    print("\nExecuting Pipeline/Feed Quality Tests...")
    try:
        test_feed_quality_rejects_stale_data()
        print("  [PASS] test_feed_quality_rejects_stale_data")
    except Exception as e:
        print(f"  [FAIL] test_feed_quality_rejects_stale_data: {e}")
        passed = False

    try:
        test_feed_quality_rejects_missing_candles()
        print("  [PASS] test_feed_quality_rejects_missing_candles")
    except Exception as e:
        print(f"  [FAIL] test_feed_quality_rejects_missing_candles: {e}")
        passed = False

    try:
        test_feed_quality_rejects_large_gap_count()
        print("  [PASS] test_feed_quality_rejects_large_gap_count")
    except Exception as e:
        print(f"  [FAIL] test_feed_quality_rejects_large_gap_count: {e}")
        passed = False

    try:
        test_feed_quality_rejects_high_latency()
        print("  [PASS] test_feed_quality_rejects_high_latency")
    except Exception as e:
        print(f"  [FAIL] test_feed_quality_rejects_high_latency: {e}")
        passed = False
        
    if passed:
        print("\nAll tests executed successfully!")
        sys.exit(0)
    else:
        print("\nSome tests failed. Review errors above.")
        sys.exit(1)
