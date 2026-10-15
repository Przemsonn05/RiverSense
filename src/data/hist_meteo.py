"""Historia: pogoda godzinowa ERA5 / ERA5-Land (meteo_hourly_<punkt>.parquet) i agregacja dobowa.

Znacznik czasu oznacza KONIEC godziny: opad o 01:00 to suma z 00:00–01:00.
"""
import pandas as pd

from . import config, utils

RENAME = {
    "precipitation": "precip_mm",
    "rain": "rain_mm",
    "snowfall": "snowfall_cm",       # Open-Meteo podaje opad śniegu w cm
    "snow_depth": "snow_depth_cm",   # po przeliczeniu z m
    "temperature_2m": "temp_c",
    "soil_moisture_0_to_7cm": "soil_moist_m3m3",
}
VALUES = list(RENAME.values())


def standardize(df):
    """Wspólne dla ERA5 i prognoz: nazwy, jednostki, zakresy fizyczne -> is_suspect."""
    df = df.rename(columns=RENAME)
    df["snow_depth_cm"] = df["snow_depth_cm"] * 100  # m -> cm
    for col in ["precip_mm", "rain_mm", "snowfall_cm"]:
        df[col] = df[col].clip(lower=0)  # ujemny opad (artefakt modelu) -> 0
    df["is_suspect"] = suspect(df)
    return df


def suspect(df):
    """Wartości poza zakresami fizycznymi (config) -> True."""
    return (utils.range_suspect(df["precip_mm"], high=config.PRECIP_MAX)
            | utils.range_suspect(df["temp_c"], *config.TEMP_RANGE)
            | utils.range_suspect(df["soil_moist_m3m3"], *config.SOIL_RANGE))


def load_raw():
    frames = []
    for point in config.METEO_POINTS:
        df = pd.read_parquet(config.HIST / f"meteo_hourly_{point}.parquet")
        frames.append(df.assign(point=point))
    return pd.concat(frames, ignore_index=True)


def process():
    """Kroki B.1–B.4 planu. Zwraca (meteo_hourly_era5, info)."""
    df = load_raw()
    df["time_utc"] = utils.to_utc(df["time_utc"])
    df = standardize(df)
    end = df["time_utc"].max()
    n_raw = len(df)
    df = utils.full_grid(df, "point", "time_utc", config.METEO_START, end, "h")
    df["is_suspect"] = df["is_suspect"].eq(True)
    info = {
        "era5_end": end,
        "missing_hours": len(df) - n_raw,
        "nan_values": int(df[VALUES].isna().sum().sum()),
        "suspect_hours": int(df["is_suspect"].sum()),
    }
    return df[["point", "time_utc", *VALUES, "is_suspect"]].assign(source="era5"), info


def aggregate_daily(hourly):
    """Doby wg config.DAILY_DEFINITION (utils.day_label). Sumy i średnie tylko z pełnych dób
    (24 godziny z danymi), inaczej NaN; pokrywa śnieżna = wartość o config.SNOW_DEPTH_HOUR UTC."""
    df = hourly.assign(date=utils.day_label(hourly["time_utc"]),
                       from_forecast=hourly["source"] == "forecast")
    g = df.groupby(["point", "date"])
    daily = pd.DataFrame({
        "precip_mm": g["precip_mm"].sum(min_count=24),
        "rain_mm": g["rain_mm"].sum(min_count=24),
        "snowfall_cm": g["snowfall_cm"].sum(min_count=24),
        "temp_mean_c": g["temp_c"].mean(),
        "temp_min_c": g["temp_c"].min(),
        "temp_max_c": g["temp_c"].max(),
        "soil_moist_m3m3": g["soil_moist_m3m3"].mean(),
        "n_hours": g["precip_mm"].count(),
        # 'forecast', jeśli choć jedna godzina doby pochodzi z prognozy
        "from_forecast": g["from_forecast"].any(),
    })
    daily["source"] = daily.pop("from_forecast").map({True: "forecast", False: "era5"})
    full = daily["n_hours"] == 24
    daily.loc[~full, ["temp_mean_c", "temp_min_c", "temp_max_c", "soil_moist_m3m3"]] = float("nan")

    snow = df[df["time_utc"].dt.hour == config.SNOW_DEPTH_HOUR]
    snow = snow.assign(date=snow["time_utc"].dt.floor("D").dt.tz_localize(None))
    daily = daily.join(snow.set_index(["point", "date"])["snow_depth_cm"])
    return daily.reset_index()
