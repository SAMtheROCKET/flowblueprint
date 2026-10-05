"""Synthetic example: summarise heat events per weather station.

Used by FlowBlueprint's tests and README. It is parsed, never executed.
"""

import configparser
import json

import matplotlib.pyplot as plt
import pandas as pd

from station_utils import (flag_heat_events, load_station_readings,
                           repair_missing_values)

CONFIG_PATH = "settings.ini"


def read_settings(config_path: str) -> tuple[list[str], float, str]:
    """Read the station list, heat threshold and data folder."""
    config = configparser.ConfigParser()
    config.read(config_path)
    stations_list = config["run"]["stations"].split(",")
    return (stations_list, config.getfloat("run", "threshold"),
            config["run"]["folder"])


def summarise_station(flagged_df: pd.DataFrame, station_str: str) -> dict:
    """Compute the hot hours, peak and mean temperature of a station."""
    return {"station": station_str,
            "hot_hours": int(flagged_df.is_hot.sum()),
            "peak_c": float(flagged_df.temp_c.max()),
            "mean_c": float(flagged_df.temp_c.mean())}


def main() -> None:
    """Run the report."""
    stations_list, threshold_float, folder_str = read_settings(CONFIG_PATH)
    summaries_list = []
    for station_str in stations_list:
        readings_df = load_station_readings(station_str, folder_str)
        readings_df = repair_missing_values(readings_df)
        flagged_df, event_count_int = flag_heat_events(readings_df,
                                                       threshold_float)
        if event_count_int == 0:
            print(f"{station_str}: no heat events")
            continue
        summary_dict = summarise_station(flagged_df, station_str)
        summaries_list.append(summary_dict)
    summary_df = pd.DataFrame(summaries_list)
    summary_df.to_csv("heat_summary.csv", index=False)
    with open("heat_summary.json", "w") as handle:
        json.dump(summaries_list, handle)
    plt.bar(summary_df.station, summary_df.hot_hours)
    plt.title("Hot hours per station")
    plt.savefig("hot_hours.png")


if __name__ == "__main__":
    main()
