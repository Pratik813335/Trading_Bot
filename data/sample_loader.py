from pathlib import Path

import pandas as pd

from config import DATA_CSV_PATH


def load_sample_data(path=None, fallback_reason=None):
    sample_path = Path(path or DATA_CSV_PATH)
    if not sample_path.exists():
        return None

    df = pd.read_csv(sample_path)
    if "timestamp" not in df.columns:
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        else:
            df.insert(0, "timestamp", pd.RangeIndex(start=0, stop=len(df), step=1))
    if "volume" not in df.columns:
        df["volume"] = 0
    df.attrs["data_source"] = "sample_data"
    if fallback_reason:
        df.attrs["fallback_reason"] = fallback_reason
    return df
