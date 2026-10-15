"""Live: prognozy Open-Meteo (forecast_RRRR-MM.csv) i obserwacje synoptyczne IMGW (synop.csv)."""
import pandas as pd

from . import config, hist_meteo, utils

FORECAST_COLUMNS = ["point", "issued_at", "valid_at", "precipitation", "rain", "snowfall",
                    "snow_depth", "temperature_2m", "soil_moisture_0_to_7cm"]


def load_forecasts():
    files = sorted(config.LIVE.glob("forecast_*.csv"))
    if not files:
        raise FileNotFoundError(f"Brak plików forecast_*.csv w {config.LIVE}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def process_forecasts():
    """Kroki B.1–B.5 planu. Zwraca (forecast_archive, info)."""
    raw = load_forecasts()
    # B.3 kontrola zawartości
    if list(raw.columns) != FORECAST_COLUMNS:
        raise ValueError(f"forecast: kolumny {list(raw.columns)} zamiast {FORECAST_COLUMNS}")
    if set(raw["point"]) != set(config.METEO_POINTS):
        raise ValueError(f"forecast: punkty {sorted(set(raw['point']))}")

    df = raw.copy()
    df["point"] = df["point"].astype("string")
    df["issued_at"] = utils.to_utc(df["issued_at"])
    df["valid_at"] = utils.to_utc(df["valid_at"])
    df = df.drop_duplicates(["point", "issued_at", "valid_at"])
    df = hist_meteo.standardize(df).drop(columns="is_suspect")
    df["lead_h"] = ((df["valid_at"] - df["issued_at"]) / pd.Timedelta(hours=1)).astype("int16")

    # B.5 wilgotność gleby: interpolacja tylko w obrębie jednej prognozy
    df = df.sort_values(["point", "issued_at", "valid_at"])
    missing = df["soil_moist_m3m3"].isna()
    df["soil_moist_m3m3"] = (df.groupby(["point", "issued_at"])["soil_moist_m3m3"]
                               .transform(lambda s: s.interpolate(limit_area="inside")))
    df["soil_is_imputed"] = missing & df["soil_moist_m3m3"].notna()

    info = {
        "issues": df["issued_at"].nunique(),
        "first_issue": df["issued_at"].min(),
        "last_issue": df["issued_at"].max(),
        "lead_range_h": (int(df["lead_h"].min()), int(df["lead_h"].max())),
        "soil_missing": int(missing.sum()),
        "soil_imputed": int(df["soil_is_imputed"].sum()),
        # godziny bez prognozy (pominięte uruchomienia collect.py)
        "missing_issues": int(len(pd.date_range(df["issued_at"].min(), df["issued_at"].max(), freq="h"))
                              - df["issued_at"].nunique()),
    }
    return df.reset_index(drop=True), info


def latest(archive, min_lead=1, max_lead=None):
    """Dla każdego (point, valid_at) wiersz z najnowszej prognozy o lead_h w [min_lead, max_lead].
    min_lead=1: prognoza wydana przed daną godziną (to, co model naprawdę wiedział)."""
    sel = archive["lead_h"] >= min_lead
    if max_lead is not None:
        sel &= archive["lead_h"] <= max_lead
    df = archive[sel].sort_values("issued_at")
    return df.drop_duplicates(["point", "valid_at"], keep="last").reset_index(drop=True)


def observed_proxy(archive):
    """B.7: 'obserwowana' pogoda dla godzin bez ERA5 – analiza z najnowszej prognozy
    (lead_h od −24 do 0)."""
    lo, hi = config.OBSERVED_LEAD_H
    df = latest(archive, min_lead=lo, max_lead=hi)
    df = df.rename(columns={"valid_at": "time_utc"})
    df["is_suspect"] = hist_meteo.suspect(df)
    return df[["point", "time_utc", *hist_meteo.VALUES, "is_suspect"]].assign(source="forecast")


# ---------------------------------------------------------------- synop

SYNOP_RENAME = {
    "id_stacji": "station_id", "stacja": "station", "temperatura": "temp_c",
    "predkosc_wiatru": "wind_ms", "kierunek_wiatru": "wind_dir_deg",
    "wilgotnosc_wzgledna": "rel_humidity_pct", "suma_opadu": "precip_sum_mm", "cisnienie": "pressure_hpa",
}


def process_synop():
    """Kroki C.1–C.3 planu. Godziny synoptyczne IMGW są w UTC.
    suma_opadu -> precip_sum_mm: suma z okresu synoptycznego, NIE opad godzinowy."""
    raw = pd.read_csv(config.LIVE / "synop.csv", dtype=str)
    df = raw.rename(columns=SYNOP_RENAME)
    t = pd.to_datetime(df["data_pomiaru"]) + pd.to_timedelta(pd.to_numeric(df["godzina_pomiaru"]), unit="h")
    df["time_utc"] = utils.to_utc(t)
    for col in ["temp_c", "wind_ms", "wind_dir_deg", "rel_humidity_pct", "precip_sum_mm", "pressure_hpa"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates(["station_id", "time_utc"], keep="last")
    return df, {"rows": len(df), "stations": sorted(df["station"].unique())}
