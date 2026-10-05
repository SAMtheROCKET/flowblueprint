"""Helpers for the synthetic weather-station example (never executed)."""

import pandas as pd


def load_station_readings(station_str: str, folder_str: str) -> pd.DataFrame:
    """Load the hourly readings of one station from its Parquet file."""
    return pd.read_parquet(f"{folder_str}/{station_str}.parquet")


def repair_missing_values(readings_df: pd.DataFrame) -> pd.DataFrame:
    """Fill short gaps in temperature and humidity by interpolation."""
    return readings_df.interpolate(limit=3)


def flag_heat_events(readings_df: pd.DataFrame,
                     threshold_float: float) -> tuple[pd.DataFrame, int]:
    """Mark hours above the heat threshold and count the events."""
    flagged_df = readings_df.assign(is_hot=readings_df.temp_c
                                    > threshold_float)
    return flagged_df, int(flagged_df.is_hot.sum())
