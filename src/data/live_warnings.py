"""Live: ostrzeżenia hydrologiczne IMGW (warnings_hydro.csv).

Czasy ostrzeżeń są w czasie polskim (config.TZ_IMGW_WARNINGS), w przeciwieństwie do stanów wody.
"""
import pandas as pd

from . import config, utils


def process():
    """Kroki D.1–D.3 planu. Zwraca (warnings, info); filtr zlewni: df[df.dotyczy_zlewni]."""
    raw = pd.read_csv(config.LIVE / "warnings_hydro.csv", dtype=str)
    df = raw.copy()
    for col in ["opublikowano", "data_od"]:
        df[col] = utils.to_utc(df[col], config.TZ_IMGW_WARNINGS)
    # 9999-12-31 = ostrzeżenie bez ustalonego końca -> NaT
    open_end = df["data_do"].str.startswith("9999")
    df["data_do"] = utils.to_utc(df["data_do"].where(~open_end), config.TZ_IMGW_WARNINGS)
    df["first_seen_utc"] = utils.to_utc(df["fetched_at"])
    df["stopien"] = pd.to_numeric(df["stopien"], errors="coerce")
    df["prawdopodobienstwo"] = pd.to_numeric(df["prawdopodobienstwo"], errors="coerce")
    df["dotyczy_zlewni"] = df["dotyczy_zlewni"].str.lower().eq("true")
    # stopień −1 = ostrzeżenie przed suszą hydrologiczną, nie odwołanie
    df["is_drought"] = (df["stopien"] == -1) | df["zdarzenie"].str.contains("Susza", na=False)
    info = {
        "rows": len(df),
        "basin": int(df["dotyczy_zlewni"].sum()),
        "drought": int(df["is_drought"].sum()),
        "flood_basin": df.loc[df["dotyczy_zlewni"] & ~df["is_drought"],
                              ["opublikowano", "stopien", "zdarzenie", "obszary_opis"]],
    }
    return df, info
