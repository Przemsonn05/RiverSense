"""
Zbieranie danych "na żywo" co godzinę: stany wody IMGW + pogoda IMGW + prognoza opadu Open-Meteo.
Każde uruchomienie dopisuje nowe wiersze do plików CSV w data/live/ i usuwa duplikaty.

Uruchomienie lokalne:   pip install requests pandas && python collect.py
Automatycznie:          .github/workflows/collect.yml (GitHub Actions, co godzinę)
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/live")
OUT.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Stacje hydrologiczne IMGW: Kraków-Bielany (cel) + zlewnia powyżej Krakowa.
# Uzupełnijcie brakujące (Skawa, Skawinka, Smolice) z lista_stacji_hydro.csv.
HYDRO_STATIONS = {
    "150190340": "Kraków-Bielany (Wisła)",
    "149180210": "Zabrzeg (Wisła)",
    "149190060": "Jawiszowice (Wisła)",
    "150190170": "Pustynia (Wisła)",
    "150190160": "Oświęcim (Soła)",
    "149190120": "Czaniec (Soła)",
    "149190100": "Żywiec (Soła)",
    "150190100": "Niwka (Biała Przemsza)",
    "150190310": "Balice (Rudawa)",
}

# Stacje synoptyczne IMGW (opad, temperatura) – sprawdźcie ID w /api/data/synop
SYNOP_STATIONS = {"12566": "Kraków-Balice", "12600": "Bielsko-Biała", "12625": "Zakopane"}

# Punkty w zlewni do prognozy opadu z Open-Meteo
METEO_POINTS = {
    "krakow": (50.06, 19.94),
    "wadowice": (49.88, 19.49),
    "zywiec": (49.69, 19.19),
    "bielsko": (49.82, 19.04),
}


def get(url, **params):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def append(df: pd.DataFrame, name: str, keys: list[str]):
    """Dopisz do CSV i usuń duplikaty (ten sam pomiar pobrany dwa razy)."""
    path = OUT / f"{name}.csv"
    if path.exists():
        df = pd.concat([pd.read_csv(path, dtype=str), df.astype(str)])
    df = df.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    df.to_csv(path, index=False)
    print(f"{name}: {len(df)} wierszy")


def collect_hydro():
    rows = []
    for sid, label in HYDRO_STATIONS.items():
        try:
            rec = get(f"https://danepubliczne.imgw.pl/api/data/hydro/id/{sid}")[0]
            rows.append({
                "station_id": sid,
                "station": label,
                "measured_at": rec["stan_wody_data_pomiaru"],  # czas lokalny IMGW
                "water_level_cm": rec["stan_wody"],
                "flow_m3s": rec["przeplyw"],
                "flow_at": rec["przeplyw_data"],
                "warning_cm": rec["stan_ostrzegawczy"],
                "alarm_cm": rec["stan_alarmowy"],
                "fetched_at": NOW,
            })
        except Exception as e:  # jedna padnięta stacja nie zatrzymuje reszty
            print(f"hydro {sid}: błąd {e}")
    if rows:
        append(pd.DataFrame(rows), "hydro", ["station_id", "measured_at"])


def collect_synop():
    try:
        data = get("https://danepubliczne.imgw.pl/api/data/synop")
    except Exception as e:
        print(f"synop: błąd {e}")
        return
    rows = [
        {**rec, "fetched_at": NOW}
        for rec in data
        if rec["id_stacji"] in SYNOP_STATIONS
    ]
    if rows:
        append(pd.DataFrame(rows), "synop", ["id_stacji", "data_pomiaru", "godzina_pomiaru"])


def collect_forecast():
    """Zapisujemy też prognozę z chwili pobrania – potrzebna, żeby uczyć model
    na prognozach, które były znane w danym momencie (bez 'zaglądania w przyszłość')."""
    frames = []
    for name, (lat, lon) in METEO_POINTS.items():
        try:
            d = get(
                "https://api.open-meteo.com/v1/forecast",
                latitude=lat, longitude=lon, timezone="UTC",
                hourly="precipitation,rain,snowfall,snow_depth,temperature_2m,soil_moisture_0_to_1cm",
                past_days=1, forecast_days=3,
            )
            df = pd.DataFrame(d["hourly"]).rename(columns={"time": "valid_at"})
            df.insert(0, "point", name)
            df.insert(1, "issued_at", NOW[:13] + ":00Z")  # godzina pobrania prognozy
            frames.append(df)
        except Exception as e:
            print(f"open-meteo {name}: błąd {e}")
    if frames:
        append(pd.concat(frames), "forecast", ["point", "issued_at", "valid_at"])


if __name__ == "__main__":
    collect_hydro()
    collect_synop()
    collect_forecast()
