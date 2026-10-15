"""Tabela stacji (stations.parquet): sieć rzeczna z config + archiwum + metadane live."""
import pandas as pd

from . import config, live_hydro


def latest_meta():
    """Ostatnie znane metadane stacji z live. stations_meta.csv jest zbierany od 15.10.2026;
    bez niego progi bierzemy z hydro.csv, a położenie i zero wodowskazu zostają puste."""
    path = config.LIVE / "stations_meta.csv"
    if path.exists():
        meta = pd.read_csv(path, dtype=str).sort_values("fetched_at")
    else:
        meta = live_hydro.load_raw().sort_values("fetched_at")
    meta = meta.drop_duplicates("station_id", keep="last").set_index("station_id")
    cols = ["river_km", "lat", "lon", "gauge_zero_m", "warning_cm", "alarm_cm"]
    return meta.reindex(columns=cols).apply(pd.to_numeric, errors="coerce")


def gauge_zero_changes():
    """Zmiany zera wodowskazu lub progów zarejestrowane w stations_meta.csv."""
    path = config.LIVE / "stations_meta.csv"
    if not path.exists():
        return pd.DataFrame(columns=["station_id", "fetched_at", "gauge_zero_m"])
    meta = pd.read_csv(path, dtype=str)
    changed = meta["station_id"].duplicated(keep=False)
    return meta[changed].sort_values(["station_id", "fetched_at"])


def build(live_last=None):
    """live_last: ostatni pomiar live na stację (info['last_measured'] z live_hydro.process)."""
    found = pd.read_csv(config.HIST / "stations_found.csv", dtype={"station_id": str},
                        parse_dates=["first", "last"]).set_index("station_id")
    meta = latest_meta()
    rows = []
    for sid, (name, river, down) in config.STATIONS.items():
        rows.append({
            "station_id": sid, "name": name, "river": river, "downstream_id": down,
            **meta.reindex([sid]).iloc[0].to_dict(),
            "record_cm": found.at[sid, "max_level_cm"],
            "is_target": sid == config.TARGET,
            "main_feature": sid not in config.NOT_MAIN_FEATURE,
            "note": config.NOT_MAIN_FEATURE.get(sid),
            "hist_first": found.at[sid, "first"], "hist_last": found.at[sid, "last"],
            "live_last_utc": live_last.get(sid) if live_last is not None else pd.NaT,
        })
    df = pd.DataFrame(rows)
    df["live_last_utc"] = pd.to_datetime(df["live_last_utc"], utc=True)
    return df
