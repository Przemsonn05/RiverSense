"""Łączenie historii i live we wspólne tabele. Przez lukę 11.2025–10.2026 nigdy nie
interpolujemy: historia i live są przetwarzane osobno i tylko zestawiane, kolumna `source`."""
import pandas as pd

from . import config, utils


def levels_daily(hist, live_daily):
    return pd.concat([hist, live_daily], ignore_index=True)


def levels_daily_wide(levels):
    """Układ data × stacja (kolumny lvl_<station_id>) – wygodny do EDA i modelu."""
    wide = levels.pivot(index="date", columns="station_id", values="level_cm")
    wide.columns = [f"lvl_{c}" for c in wide.columns]
    return wide.astype("float32").reset_index()


def meteo_hourly(era5, proxy):
    """ERA5 do końca dostępności, potem analiza z prognozy; godziny bez żadnego źródła = NaN."""
    end = era5["time_utc"].max()
    df = pd.concat([era5, proxy[proxy["time_utc"] > end]], ignore_index=True)
    df = utils.full_grid(df, "point", "time_utc", config.METEO_START, df["time_utc"].max(), "h")
    df["is_suspect"] = df["is_suspect"].eq(True)
    return df
