"""Raport jakości danych reports/data_quality.md (+ reports/missing_by_year.csv do mapy ciepła w EDA)."""
import pandas as pd

from . import config, stations, utils


def missing_by_year(levels):
    """% brakujących dni stanu wody na stację i rok hydrologiczny (przed interpolacją = po niej
    bez is_imputed)."""
    hist = levels[levels["source"] == "hist"]
    missing = hist["level_cm"].isna() | hist["is_imputed"]
    year = hist["date"].dt.year + (hist["date"].dt.month >= 11)
    return (missing.groupby([hist["station_id"], year]).mean().mul(100).round(1)
                   .unstack().rename_axis(index="station_id", columns="hydro_year"))


def station_summary(tables):
    levels, st = tables["levels_daily"], tables["stations"].set_index("station_id")
    hist = levels[levels["source"] == "hist"]
    rows = []
    for sid, g in hist.groupby("station_id"):
        s = g.set_index("date")["level_cm"]
        gap, gap_start = utils.longest_gap(s)
        rows.append({
            "stacja": f"{st.at[sid, 'name']} ({st.at[sid, 'river']})", "station_id": sid,
            "main": "tak" if st.at[sid, "main_feature"] else "nie",
            "braki %": round(100 * s.isna().mean(), 1),
            "najdłuższa luka [dni]": gap,
            "od": gap_start.date() if gap_start is not None else "",
            "uzupełnione": int(g["is_imputed"].sum()),
            "skoki usunięte": int(g["is_spike"].sum()),
            "podejrzane": int(g["is_suspect"].sum()),
            "dni z lodem": int(g["has_ice"].sum()),
        })
    return pd.DataFrame(rows)


def md(df, index=False):
    """Tabela markdown bez dodatkowych zależności (pandas.to_markdown wymaga tabulate)."""
    if not len(df):
        return "_brak_"
    if index:
        df = df.reset_index()
    cells = [[str(c) for c in df.columns]] + [["" if pd.isna(v) else str(v) for v in row]
                                              for row in df.itertuples(index=False)]
    lines = ["| " + " | ".join(r) + " |" for r in cells]
    lines.insert(1, "|" + "---|" * len(df.columns))
    return "\n".join(lines)


def write(tables, info, path=None):
    path = path or config.REPORTS / "data_quality.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    missing_by_year(tables["levels_daily"]).to_csv(path.parent / "missing_by_year.csv")

    hh, lh, fc = info["hist_hydro"], info["live_hydro"], info["forecast"]
    meteo = tables["meteo_hourly"]
    gap = meteo[meteo["precip_mm"].isna() & (meteo["time_utc"] > info["hist_meteo"]["era5_end"])]
    live_missing = pd.DataFrame({"brak godzin (surowe)": lh["missing_hours_raw"],
                                 "brak po uzupełnieniu": lh["missing_hours_after"],
                                 "uzupełnione": lh["imputed_hours"]})
    summary = pd.DataFrame([{"tabela": k, "wiersze": len(v)} for k, v in tables.items()])

    text = f"""# Raport jakości danych

Wygenerowano: {pd.Timestamp.now(tz="UTC"):%Y-%m-%d %H:%M} UTC · `python -m src.data.build`
Definicja doby: `{config.DAILY_DEFINITION}` (otwarta decyzja nr 1, `config.DAILY_DEFINITION`)

## Tabele

{md(summary)}

## Stany wody – historia ({config.HIST_START} – {config.HIST_END})

{md(station_summary(tables))}

Braki na stację i rok hydrologiczny: `reports/missing_by_year.csv` (mapa ciepła w EDA).
Skoki przy lodzie oznaczone jako podejrzane (nieusunięte): {hh["ice_jumps"]}.

**Usunięte skoki (błędy odczytu)**

{md(hh["spikes"])}

**Kandydaci na zmianę zera wodowskazu** – trwała zmiana minimum rocznego o > {config.ZERO_SHIFT_CM} cm.
Niczego nie korygujemy automatycznie; decyzja zespołu (korekta przesunięciem, ucięcie okresu
albo naturalna zmiana koryta / praca zbiornika).

{md(hh["zero_shifts"].round(1))}

## Stany wody – live

- Wiersze surowe: {lh["raw_rows"]}, duplikaty: {lh["duplicates"]}, mediana opóźnienia pomiaru: {lh["lag_median_h"]:.2f} h
- Przestarzałe odczyty (> {config.STALE_HOURS} h, odrzucone): {lh["stale_rows"].to_dict() or "brak"}
- Usunięte skoki godzinowe: {len(lh["spikes"])}

{md(live_missing, index=True)}

Zmiany zera wodowskazu / progów w `stations_meta.csv`:

{md(stations.gauge_zero_changes())}

## Pogoda

- ERA5 do: {info["hist_meteo"]["era5_end"]}, brakujące godziny w ERA5: {info["hist_meteo"]["missing_hours"]}, wartości podejrzane: {info["hist_meteo"]["suspect_hours"]}
- Prognozy: {fc["issues"]} wydań ({fc["first_issue"]} – {fc["last_issue"]}), pominięte godziny wydań: {fc["missing_issues"]}, lead_h {fc["lead_range_h"]}
- Wilgotność gleby w prognozach: braki {fc["soil_missing"]}, uzupełnione {fc["soil_imputed"]}
- Godziny bez ERA5 i bez analizy z prognozy (po końcu ERA5): {gap["time_utc"].nunique()}{f" ({gap['time_utc'].min()} – {gap['time_utc'].max()})" if len(gap) else ""}

## Ostrzeżenia IMGW

- Wszystkie: {info["warnings"]["rows"]}, dla zlewni: {info["warnings"]["basin"]}, susza: {info["warnings"]["drought"]}

Ostrzeżenia powodziowe dla zlewni:

{md(info["warnings"]["flood_basin"])}
"""
    path.write_text(text, encoding="utf-8")
    return path
