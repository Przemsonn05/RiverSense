"""Schematy tabel w data/processed/ i ich walidacja.

Kolumny czasu: `time_utc`, `issued_at`, `valid_at`, `opublikowano` – datetime64[ns, UTC];
`date` – doba bez strefy (doba UTC zgodna z config.DAILY_DEFINITION).
"""
import pandas as pd

UTC = "datetime64[ns, UTC]"
DAY = "datetime64[ns]"
F = "float32"
B = "bool"
S = "string"

SCHEMAS = {
    "stations": {
        "key": ["station_id"],
        "columns": {
            "station_id": S, "name": S, "river": S, "downstream_id": S,
            "river_km": F, "lat": F, "lon": F, "gauge_zero_m": F,
            "warning_cm": F, "alarm_cm": F, "record_cm": F,
            "is_target": B, "main_feature": B, "note": S,
            "hist_first": DAY, "hist_last": DAY, "live_last_utc": UTC,
        },
    },
    "levels_daily": {
        "key": ["station_id", "date"],
        "columns": {
            "station_id": S, "date": DAY, "level_cm": F, "flow_m3s": F, "has_ice": B,
            "is_imputed": B, "is_suspect": B, "is_spike": B, "source": S,
        },
    },
    "levels_hourly": {
        "key": ["station_id", "time_utc"],
        "columns": {
            "station_id": S, "time_utc": UTC, "level_cm": F, "flow_m3s": F, "has_ice": B,
            "is_imputed": B, "is_suspect": B, "is_spike": B, "source": S,
        },
    },
    "meteo_hourly": {
        "key": ["point", "time_utc"],
        "columns": {
            "point": S, "time_utc": UTC, "precip_mm": F, "rain_mm": F, "snowfall_cm": F,
            "snow_depth_cm": F, "temp_c": F, "soil_moist_m3m3": F, "is_suspect": B, "source": S,
        },
    },
    "meteo_daily": {
        "key": ["point", "date"],
        "columns": {
            "point": S, "date": DAY, "precip_mm": F, "rain_mm": F, "snowfall_cm": F,
            "snow_depth_cm": F, "temp_mean_c": F, "temp_min_c": F, "temp_max_c": F,
            "soil_moist_m3m3": F, "n_hours": "int16", "source": S,
        },
    },
    "forecast_archive": {
        "key": ["point", "issued_at", "valid_at"],
        "columns": {
            "point": S, "issued_at": UTC, "valid_at": UTC, "lead_h": "int16",
            "precip_mm": F, "rain_mm": F, "snowfall_cm": F, "snow_depth_cm": F,
            "temp_c": F, "soil_moist_m3m3": F, "soil_is_imputed": B,
        },
    },
    "forecast_latest": {
        "key": ["point", "valid_at"],
        "columns": {
            "point": S, "valid_at": UTC, "issued_at": UTC, "lead_h": "int16",
            "precip_mm": F, "rain_mm": F, "snowfall_cm": F, "snow_depth_cm": F,
            "temp_c": F, "soil_moist_m3m3": F,
        },
    },
    "synop_hourly": {
        "key": ["station_id", "time_utc"],
        "columns": {
            "station_id": S, "station": S, "time_utc": UTC, "temp_c": F, "wind_ms": F,
            "wind_dir_deg": F, "rel_humidity_pct": F, "precip_sum_mm": F, "pressure_hpa": F,
        },
    },
    "warnings": {
        "key": ["numer", "biuro", "opublikowano"],
        "columns": {
            "numer": S, "biuro": S, "opublikowano": UTC, "data_od": UTC, "data_do": UTC,
            "stopien": "Int8", "zdarzenie": S, "prawdopodobienstwo": F, "przebieg": S,
            "komentarz": S, "wojewodztwa": S, "obszary_opis": S, "kod_zlewni": S, "dotyczy_zlewni": B,
            "is_drought": B, "first_seen_utc": UTC,
        },
    },
}
SCHEMAS["levels_daily_wide"] = None  # tabela pomocnicza, kolumny zależą od stacji


def conform(df, name):
    """Ustawia kolejność kolumn i typy zgodnie ze schematem."""
    cols = SCHEMAS[name]["columns"]
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"{name}: brak kolumn {sorted(missing)}")
    df = df[list(cols)].copy()
    for col, dtype in cols.items():
        if df[col].dtype != dtype:
            df[col] = df[col].astype(dtype)
    return df.sort_values(SCHEMAS[name]["key"]).reset_index(drop=True)


def validate(df, name):
    """Lista problemów z tabelą (pusta = OK): kolumny, typy, unikalny klucz, rosnący czas."""
    spec = SCHEMAS[name]
    if spec is None:
        return []
    problems = []
    cols = spec["columns"]
    if list(df.columns) != list(cols):
        problems.append(f"{name}: kolumny {list(df.columns)} zamiast {list(cols)}")
        return problems
    for col, dtype in cols.items():
        if str(df[col].dtype) != dtype:
            problems.append(f"{name}.{col}: typ {df[col].dtype} zamiast {dtype}")
    dups = df.duplicated(spec["key"]).sum()
    if dups:
        problems.append(f"{name}: {dups} zduplikowanych kluczy {spec['key']}")
    if len(spec["key"]) == 2:  # (obiekt, czas) – czas rośnie w obrębie obiektu
        group, time = spec["key"][0], spec["key"][-1]
        ok = df.groupby(group, observed=True)[time].apply(lambda t: t.is_monotonic_increasing)
        if not ok.all():
            problems.append(f"{name}: czas nie rośnie w obrębie {group}: {list(ok[~ok].index)}")
    return problems
