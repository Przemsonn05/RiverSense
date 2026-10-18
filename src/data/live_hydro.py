"""Live: stany wody IMGW (hydro.csv) -> siatka godzinowa i wartości dobowe.

Czasy IMGW w hydro.csv są w UTC bez oznaczenia strefy (config.TZ_IMGW_HYDRO).
Godzina w siatce = koniec godziny: wartość o 15:00 to ostatni pomiar z (14:00, 15:00].
"""
import pandas as pd

from . import config, hist_hydro, utils


def load_raw():
    return pd.read_csv(config.LIVE / "hydro.csv", dtype=str)


def parse(raw):
    """Typy i czas UTC (kroki A.1–A.3, A.5–A.6)."""
    df = pd.DataFrame({
        "station_id": raw["station_id"].astype("string"),
        "measured_at": utils.to_utc(raw["measured_at"], config.TZ_IMGW_HYDRO),
        "fetched_at": utils.to_utc(raw["fetched_at"]),
        "level_cm": pd.to_numeric(raw["water_level_cm"], errors="coerce"),
        "flow_m3s": pd.to_numeric(raw["flow_m3s"], errors="coerce"),
        "flow_at": utils.to_utc(raw["flow_at"], config.TZ_IMGW_HYDRO),
    })
    # Kolumna lodu jest zbierana od 15.10.2026; starsze wiersze: brak informacji = brak lodu.
    # API zwraca ostatnie zaobserwowane zjawisko, nawet sprzed miesięcy – liczy się tylko świeże.
    ice = raw["ice_code"] if "ice_code" in raw else pd.Series(pd.NA, index=raw.index)
    ice_at = utils.to_utc(raw["ice_at"] if "ice_at" in raw else pd.Series(pd.NA, index=raw.index),
                          config.TZ_IMGW_HYDRO)
    fresh = (df["measured_at"] - ice_at) <= pd.Timedelta(hours=config.ICE_MAX_AGE_HOURS)
    df["has_ice"] = (pd.to_numeric(ice, errors="coerce").fillna(0) > 0) & fresh
    # Przepływ tylko świeży – IMGW aktualizuje go rzadko
    flow_age = df["fetched_at"] - df["flow_at"]
    df.loc[~(flow_age <= pd.Timedelta(hours=config.FLOW_MAX_AGE_HOURS)), "flow_m3s"] = float("nan")
    return df.drop_duplicates(["station_id", "measured_at"]).sort_values(["station_id", "measured_at"])


def process():
    """Kroki A.1–A.8 planu. Zwraca (levels_hourly_live, info)."""
    raw = load_raw()
    df = parse(raw)
    info = {"raw_rows": len(raw), "duplicates": len(raw) - len(df)}

    # A.4 przestarzałe odczyty
    lag = df["fetched_at"] - df["measured_at"]
    stale = lag > pd.Timedelta(hours=config.STALE_HOURS)
    info["stale_rows"] = df[stale].groupby("station_id").size()
    info["lag_median_h"] = (lag[~stale].dt.total_seconds() / 3600).median()
    df = df[~stale]

    # A.7 siatka godzinowa: ostatni pomiar w godzinie
    df["time_utc"] = df["measured_at"].dt.ceil("h")
    df = df.groupby(["station_id", "time_utc"], as_index=False).last()
    start = utils.to_utc(raw["fetched_at"]).min().floor("h")
    end = utils.to_utc(raw["fetched_at"]).max().floor("h")
    grid = utils.full_grid(df[["station_id", "time_utc", "level_cm", "flow_m3s", "has_ice"]],
                           "station_id", "time_utc", start, end, "h", keys=config.STATIONS)
    level = grid.pivot(index="time_utc", columns="station_id", values="level_cm")
    flow = grid.pivot(index="time_utc", columns="station_id", values="flow_m3s")
    has_ice = grid.pivot(index="time_utc", columns="station_id", values="has_ice").eq(True)
    info["missing_hours_raw"] = level.isna().sum()

    # A.8 skoki i zakresy
    spike = utils.flag_spikes(level, config.SPIKE_HOUR_CM, config.SPIKE_HOUR_NEIGHBOR_CM,
                              protect=has_ice)
    info["spikes"] = level.where(spike).stack().rename("level_cm").reset_index()
    level = level.mask(spike)
    records = hist_hydro.station_records().reindex(level.columns)
    suspect = (level < config.LEVEL_RANGE[0]) | level.gt(records + config.RECORD_MARGIN_CM, axis=1)

    # A.7 krótkie luki
    level, imputed = utils.interpolate_wide(level, config.MAX_GAP_HOURS)
    flow, _ = utils.interpolate_wide(flow, config.MAX_GAP_HOURS)
    info["imputed_hours"] = imputed.sum()
    info["missing_hours_after"] = level.isna().sum()

    def long(wide, name):
        return wide.stack(future_stack=True).rename(name)

    out = pd.concat([long(level, "level_cm"), long(flow, "flow_m3s"), long(has_ice, "has_ice"),
                     long(imputed, "is_imputed"), long(suspect, "is_suspect"),
                     long(spike, "is_spike")], axis=1)
    out.index.names = ["time_utc", "station_id"]
    out = out.reset_index().assign(source="live")
    info["last_measured"] = df.groupby("station_id")["measured_at"].max()
    return out, info


def aggregate_daily(hourly):
    """Wartość dobowa liczona tak jak (zakładamy) IMGW – config.DAILY_DEFINITION.
    '06utc': odczyt o 06 UTC; 'mean': średnia z doby UTC (co najmniej 18 godzin z danymi)."""
    flags = ["has_ice", "is_imputed", "is_suspect", "is_spike"]
    if config.DAILY_DEFINITION == "06utc":
        d = hourly[hourly["time_utc"].dt.hour == 6].copy()
        d["date"] = d["time_utc"].dt.floor("D").dt.tz_localize(None)
    else:
        h = hourly.assign(date=utils.day_label(hourly["time_utc"]))
        g = h.groupby(["station_id", "date"])
        d = g[["level_cm", "flow_m3s"]].mean().join(g[flags].any())
        d.loc[g["level_cm"].count() < 18, "level_cm"] = float("nan")
        d = d.reset_index()
    return d[["station_id", "date", "level_cm", "flow_m3s", *flags]].assign(source="live")
