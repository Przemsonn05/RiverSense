"""Historia: dobowe stany wody IMGW (hydro_daily.parquet) + zjawiska lodowe (ice_daily.parquet)."""
import pandas as pd

from . import config, utils


def load_raw():
    """Surowe tabele bez zmian (tylko typy kluczy)."""
    hydro = pd.read_parquet(config.HIST / "hydro_daily.parquet")
    hydro["station_id"] = hydro["station_id"].astype("string")
    ice_path = config.HIST / "ice_daily.parquet"
    ice = pd.read_parquet(ice_path) if ice_path.exists() else pd.DataFrame(
        columns=["date", "station_id", "ice_code"])
    ice["station_id"] = ice["station_id"].astype("string")
    return hydro, ice


def station_records():
    """Rekord stanu każdej stacji z archiwum (stations_found.csv)."""
    found = pd.read_csv(config.HIST / "stations_found.csv", dtype={"station_id": str})
    return found.set_index("station_id")["max_level_cm"].astype("float32")


def detect_zero_shifts(wide):
    """Kandydaci na zmianę zera wodowskazu: minimum roku hydrologicznego przesuwa się trwale
    o > config.ZERO_SHIFT_CM (mediana 3 lat po vs 3 lat przed). Do decyzji w raporcie –
    tu niczego nie korygujemy."""
    hydro_year = wide.index.year + (wide.index.month >= 11)
    yearly_min = wide.groupby(hydro_year).min()
    rows = []
    for sid in yearly_min.columns:
        s = yearly_min[sid].dropna()
        for i in range(3, len(s) - 2):
            before, after = s.iloc[i - 3:i].median(), s.iloc[i:i + 3].median()
            if abs(after - before) > config.ZERO_SHIFT_CM:
                rows.append({"station_id": sid, "hydro_year": int(s.index[i]),
                             "min_before_cm": before, "min_after_cm": after,
                             "shift_cm": after - before})
    out = pd.DataFrame(rows, columns=["station_id", "hydro_year", "min_before_cm",
                                      "min_after_cm", "shift_cm"])
    # z kolejnych lat tej samej zmiany zostawiamy rok z największym przesunięciem
    if not out.empty:
        out["block"] = (out.groupby("station_id")["hydro_year"].diff() != 1).cumsum()
        out = (out.loc[out.groupby("block")["shift_cm"].apply(lambda x: x.abs().idxmax())]
                  .drop(columns="block").reset_index(drop=True))
    return out


def process():
    """Kroki A.1–A.10 planu. Zwraca (levels_daily_hist, info)."""
    hydro, ice = load_raw()
    info = {}

    # A.2 lista stacji
    unknown = set(hydro["station_id"]) - set(config.STATIONS)
    missing = set(config.STATIONS) - set(hydro["station_id"])
    if unknown or missing:
        raise ValueError(f"Lista stacji: nieznane {unknown}, brakujące {missing}")

    # A.3–A.4 okres i pełny kalendarz
    hydro = hydro[(hydro["date"] >= config.HIST_START) & (hydro["date"] <= config.HIST_END)]
    hydro["date"] = hydro["date"].astype("datetime64[ns]")
    days = pd.date_range(config.HIST_START, config.HIST_END, freq="D")
    level = hydro.pivot(index="date", columns="station_id", values="level_cm").reindex(days)
    flow = hydro.pivot(index="date", columns="station_id", values="flow_m3s").reindex(days)
    level = level.reindex(columns=sorted(config.STATIONS))
    level.index.name = "date"
    flow = flow.reindex(columns=level.columns)
    info["missing_days_raw"] = level.isna().sum()

    # A.6 lód (brak wiersza = brak zjawisk)
    ice = ice[ice["ice_code"].notna()]
    ice["date"] = ice["date"].astype("datetime64[ns]")
    has_ice = (ice.assign(v=True).pivot_table(index="date", columns="station_id", values="v",
                                              aggfunc="any")
                  .reindex(index=days, columns=level.columns).notna())

    # A.5 zakres: < 0 cm lub > rekord + margines -> podejrzane
    records = station_records().reindex(level.columns)
    suspect = (level < config.LEVEL_RANGE[0]) | level.gt(records + config.RECORD_MARGIN_CM, axis=1)

    # A.7 pojedyncze skoki -> NaN (poza dniami z lodem, te tylko oznaczamy)
    spike = utils.flag_spikes(level, config.SPIKE_DAY_CM, config.SPIKE_DAY_NEIGHBOR_CM,
                              protect=has_ice)
    ice_jump = has_ice & (level.diff().abs() > config.SPIKE_DAY_CM)
    suspect |= ice_jump
    info["spikes"] = (level.where(spike).stack().rename("level_cm").reset_index())
    info["ice_jumps"] = int(ice_jump.values.sum())
    level = level.mask(spike)

    # A.8 zmiany zera wodowskazu – tylko wykrycie
    info["zero_shifts"] = detect_zero_shifts(level)

    # A.9 krótkie luki
    level, imputed = utils.interpolate_wide(level, config.MAX_GAP_DAYS)
    flow, _ = utils.interpolate_wide(flow, config.MAX_GAP_DAYS)  # A.10, bez osobnej flagi
    info["imputed_days"] = imputed.sum()
    info["missing_days_after"] = level.isna().sum()

    def long(wide, name):
        return wide.stack(future_stack=True).rename(name)

    out = pd.concat([long(level, "level_cm"), long(flow, "flow_m3s"), long(has_ice, "has_ice"),
                     long(imputed, "is_imputed"), long(suspect, "is_suspect"),
                     long(spike, "is_spike")], axis=1)
    out.index.names = ["date", "station_id"]
    out = out.reset_index().assign(source="hist")
    return out, info
