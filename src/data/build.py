"""Budowa wszystkich tabel data/processed/ od zera.

    python -m src.data.build            # buduje, sprawdza, zapisuje tabele i raport jakości
    python -m src.data.build --check    # buduje i sprawdza, bez zapisu

Jeśli którakolwiek kontrola nie przejdzie, nic nie jest zapisywane.
"""
import sys
import time

import pandas as pd

from . import (combine, config, hist_hydro, hist_meteo, live_hydro, live_meteo,
               live_warnings, quality, schema, stations)


def build_tables(verbose=True):
    """Wszystkie kroki po kolei. Zwraca (tables, info) – info to statystyki do raportu."""
    t0 = time.time()

    def log(msg):
        if verbose:
            print(f"[{time.time() - t0:5.1f} s] {msg}")

    info = {}
    hist_levels, info["hist_hydro"] = hist_hydro.process()
    log(f"historia – stany wody: {len(hist_levels):,} wierszy")
    live_hourly, info["live_hydro"] = live_hydro.process()
    log(f"live – stany wody: {len(live_hourly):,} godzin")
    era5, info["hist_meteo"] = hist_meteo.process()
    log(f"historia – pogoda ERA5: {len(era5):,} godzin")
    forecast, info["forecast"] = live_meteo.process_forecasts()
    log(f"live – prognozy: {len(forecast):,} wierszy")
    synop, info["synop"] = live_meteo.process_synop()
    warnings, info["warnings"] = live_warnings.process()
    tables = assemble(hist_levels, live_hourly, era5, forecast, synop, warnings, info)
    log("tabele gotowe")
    return tables, info


def assemble(hist_levels, live_hourly, era5, forecast, synop, warnings, info):
    """Łączy wyniki kroków w tabele wynikowe i nadaje im schematy (schema.conform)."""
    meteo_h = combine.meteo_hourly(era5, live_meteo.observed_proxy(forecast))
    levels_d = combine.levels_daily(hist_levels, live_hydro.aggregate_daily(live_hourly))
    tables = {
        "stations": stations.build(info["live_hydro"]["last_measured"]),
        "levels_daily": levels_d,
        "levels_hourly": live_hourly,
        "meteo_hourly": meteo_h,
        "meteo_daily": hist_meteo.aggregate_daily(meteo_h),
        "forecast_archive": forecast,
        "forecast_latest": live_meteo.latest(forecast),
        "synop_hourly": synop,
        "warnings": warnings,
    }
    tables = {name: schema.conform(df, name) for name, df in tables.items()}
    tables["levels_daily_wide"] = combine.levels_daily_wide(tables["levels_daily"])
    return tables


def check_content(tables, require_fresh=False):
    """Kontrole treści (poza schematem). Zwraca listę problemów."""
    problems = []
    lv, st = tables["levels_daily"], tables["stations"]
    ok = lv[~lv["is_suspect"]]["level_cm"].dropna()
    if not ok.between(*config.LEVEL_RANGE).all():
        problems.append(f"levels_daily: stan poza zakresem {config.LEVEL_RANGE}")

    m = tables["meteo_hourly"]
    good = m[~m["is_suspect"]]
    if (good["precip_mm"] < 0).any() or (good["precip_mm"] > config.PRECIP_MAX).any():
        problems.append("meteo_hourly: opad poza zakresem")

    # pełne siatki
    days = pd.date_range(config.HIST_START, config.HIST_END, freq="D")
    n_hist = (lv["source"] == "hist").sum()
    if n_hist != len(days) * len(config.STATIONS):
        problems.append(f"levels_daily: niepełna siatka historii ({n_hist} wierszy)")
    hours = pd.date_range(config.METEO_START, m["time_utc"].max().tz_localize(None), freq="h")
    if len(m) != len(hours) * len(config.METEO_POINTS):
        problems.append("meteo_hourly: niepełna siatka godzinowa")

    # stacje i punkty w historii i live
    main = st.loc[st["main_feature"], "station_id"]
    for source in ["hist", "live"]:
        have = set(lv.loc[(lv["source"] == source) & lv["level_cm"].notna(), "station_id"])
        lacking = set(main) - have
        if lacking:
            problems.append(f"levels_daily: brak danych '{source}' dla stacji {sorted(lacking)}")
    for name in ["forecast_archive", "meteo_hourly"]:
        if set(tables[name]["point"]) != set(config.METEO_POINTS):
            problems.append(f"{name}: inny zestaw punktów pogody")

    # zdrowy rozsądek: maksimum Bielan w maju 2010
    b = lv[(lv["station_id"] == config.TARGET) & (lv["source"] == "hist")].set_index("date")["level_cm"]
    if not (850 <= b.max() <= 960 and b.idxmax().strftime("%Y-%m") == "2010-05"):
        problems.append(f"Bielany: maksimum {b.max()} cm w {b.idxmax():%Y-%m}, oczekiwane maj 2010")

    if require_fresh:  # używane przez predict.py
        last = st.set_index("station_id").at[config.TARGET, "live_last_utc"]
        if pd.Timestamp.now(tz="UTC") - last > pd.Timedelta(hours=config.STALE_HOURS):
            problems.append(f"Bielany: ostatni pomiar live {last} starszy niż {config.STALE_HOURS} h")
    return problems


def validate(tables, require_fresh=False):
    problems = [p for name, df in tables.items() for p in schema.validate(df, name)]
    return problems + check_content(tables, require_fresh)


def save(tables, info):
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(config.PROCESSED / f"{name}.parquet", index=False)
    return quality.write(tables, info)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    tables, info = build_tables()
    problems = validate(tables)
    if problems:
        print("\nKONTROLE NIE PRZESZŁY – nic nie zapisano:")
        print("\n".join(f"  - {p}" for p in problems))
        sys.exit(1)
    print("Kontrole: OK")
    if "--check" not in argv:
        report = save(tables, info)
        print(f"Zapisano {len(tables)} tabel w {config.PROCESSED} i raport {report}")


if __name__ == "__main__":
    main()
