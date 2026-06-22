# tests/run_tests.py
import sys
import os

# Add parent directory to sys.path so we can import modules correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_strategies import (
    test_trend_following_buy,
    test_scalping_squeeze,
    test_range_trading,
    test_carry_trade
)

if __name__ == "__main__":
    print("Executing Strategy Engine Unit Tests...")
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
        
    if passed:
        print("\nAll tests executed successfully!")
        sys.exit(0)
    else:
        print("\nSome tests failed. Review errors above.")
        sys.exit(1)
