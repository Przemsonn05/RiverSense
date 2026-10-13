"""
Zbieranie danych "na żywo" co godzinę: stany wody IMGW + pogoda IMGW + prognoza opadu Open-Meteo
+ oficjalne ostrzeżenia hydrologiczne IMGW.
Każde uruchomienie dopisuje nowe wiersze do plików CSV w data/live/ i usuwa duplikaty.

Uruchomienie lokalne:   pip install requests pandas && python collect.py
Automatycznie:          .github/workflows/collect.yml (GitHub Actions, co godzinę)
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/live")
OUT.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Stacje hydrologiczne IMGW: Kraków-Bielany (cel) + zlewnia powyżej Krakowa.
# Ten sam zestaw co w danych historycznych (data/historical/stations_found.csv),
# żeby każda cecha modelu dała się policzyć także na danych live.
HYDRO_STATIONS = {
    # Wisła – od źródeł do Krakowa
    "149180100": "Skoczów (Wisła)",
    "149180240": "Goczałkowice (Wisła)",
    "149180210": "Zabrzeg (Wisła)",
    "149190060": "Jawiszowice (Wisła)",
    "150190170": "Pustynia (Wisła)",
    "150190260": "Smolice (Wisła)",
    "150190340": "Kraków-Bielany (Wisła)",  # CEL PROGNOZY
    # Soła
    "149190100": "Żywiec (Soła)",
    "149190120": "Czaniec (Soła)",
    "150190160": "Oświęcim (Soła)",
    # Skawa i jej dopływ Stryszawka
    "149190210": "Sucha Beskidzka (Skawa)",
    "149190200": "Sucha Beskidzka (Stryszawka)",
    "149190260": "Osielec (Skawa)",
    "149190180": "Wadowice (Skawa)",
    "149190170": "Zator (Skawa)",
    # Przemsza
    "150190100": "Niwka (Biała Przemsza)",
    "150190180": "Jeleń (Przemsza)",
    # Dopływy w rejonie Krakowa
    "149190270": "Radziszów (Skawinka)",
    "150190310": "Balice (Rudawa)",
}

# Stacje synoptyczne IMGW (opad, temperatura) – sprawdźcie ID w /api/data/synop
SYNOP_STATIONS = {"12566": "Kraków-Balice", "12600": "Bielsko-Biała", "12625": "Zakopane"}

# Punkty w zlewni do prognozy pogody z Open-Meteo – te same co w danych historycznych
# (fetch_historical.py → METEO_POINTS), żeby nazwy i współrzędne się zgadzały.
METEO_POINTS = {
    "krakow": (50.06, 19.94),
    "wadowice": (49.88, 19.49),           # Skawa
    "makow_podhalanski": (49.73, 19.68),  # górna Skawa
    "zywiec": (49.69, 19.19),             # Soła
    "wisla_beskidy": (49.65, 18.86),      # źródła Wisły
    "oswiecim": (50.04, 19.22),
    "katowice": (50.26, 19.02),           # Przemsza
}

# Zmienne prognozy – nazwy jak w danych historycznych.
FORECAST_VARS = "precipitation,rain,snowfall,snow_depth,temperature_2m"
# Wilgotność gleby 0–7 cm (jak w historii z ERA5) jest tylko w modelu ECMWF,
# więc pobieramy ją osobnym zapytaniem i dołączamy po czasie.
SOIL_VAR = "soil_moisture_0_to_7cm"

# Województwa, w których leży zlewnia Wisły powyżej Krakowa – filtr ostrzeżeń IMGW
WOJ_ZLEWNI = {"małopolskie", "śląskie"}


def get(url, tries=4, **params):
    """GET z ponawianiem: serwery GitHuba dzielą IP, więc Open-Meteo potrafi zwrócić 429
    (limit zapytań) – wtedy czekamy i próbujemy ponownie, zamiast tracić godzinę danych."""
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            status = getattr(e.response, "status_code", None)
            if attempt == tries - 1 or (status is not None and status < 500 and status != 429):
                raise
            wait = 20 * (attempt + 1)
            print(f"  {url}: {e} – ponawiam za {wait} s")
            time.sleep(wait)


def append(df: pd.DataFrame, name: str, keys: list[str], keep: str = "last"):
    """Dopisz do CSV i usuń duplikaty (ten sam pomiar pobrany dwa razy)."""
    path = OUT / f"{name}.csv"
    if path.exists():
        df = pd.concat([pd.read_csv(path, dtype=str), df.astype(str)])
    df = df.drop_duplicates(subset=keys, keep=keep).sort_values(keys)
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
    na prognozach, które były znane w danym momencie (bez 'zaglądania w przyszłość').
    Wszystkie punkty idą w jednym zapytaniu (Open-Meteo przyjmuje listę współrzędnych),
    żeby nie wpadać w limit zapytań. Osobny plik na każdy miesiąc (forecast_RRRR-MM.csv),
    bo jeden plik urósłby do ~50 MB w półtora miesiąca."""
    names = list(METEO_POINTS)
    coords = dict(
        latitude=",".join(str(lat) for lat, _ in METEO_POINTS.values()),
        longitude=",".join(str(lon) for _, lon in METEO_POINTS.values()),
        timezone="UTC", past_days=1, forecast_days=3,
    )
    try:
        weather = get("https://api.open-meteo.com/v1/forecast", hourly=FORECAST_VARS, **coords)
    except Exception as e:
        print(f"open-meteo: błąd {e}")
        return
    # Wilgotność gleby 0–7 cm z ECMWF; przy błędzie zostaje pusta kolumna, reszta się zapisuje
    try:
        soil = get("https://api.open-meteo.com/v1/ecmwf", hourly=SOIL_VAR, **coords)
    except Exception as e:
        print(f"open-meteo ecmwf: błąd {e}")
        soil = [None] * len(names)

    frames = []
    for name, d, s in zip(names, weather, soil):
        df = pd.DataFrame(d["hourly"]).rename(columns={"time": "valid_at"})
        if s is not None:
            df = df.merge(pd.DataFrame(s["hourly"]).rename(columns={"time": "valid_at"}),
                          on="valid_at", how="left")
        else:
            df[SOIL_VAR] = pd.NA
        df.insert(0, "point", name)
        df.insert(1, "issued_at", NOW[:13] + ":00Z")  # godzina pobrania prognozy
        frames.append(df)
    append(pd.concat(frames), f"forecast_{NOW[:7]}", ["point", "issued_at", "valid_at"])


def collect_warnings():
    """Oficjalne ostrzeżenia hydrologiczne IMGW dla całej Polski.
    Jeden wiersz na ostrzeżenie; 'fetched_at' = kiedy pierwszy raz je zobaczyliśmy.
    Kolumna 'dotyczy_zlewni' oznacza ostrzeżenia dla woj. małopolskiego / śląskiego
    (zlewnia Wisły powyżej Krakowa) – tych używamy do porównania z ostrzeżeniami z naszego modelu.
    Dopasowanie po dokładnej nazwie województwa: szukanie tekstu 'śląsk' łapało też dolnośląskie,
    a 'wisł' – Wisłok, Wisłokę i Wisłę poniżej Krakowa."""
    try:
        data = get("https://danepubliczne.imgw.pl/api/data/warningshydro")
    except Exception as e:
        print(f"ostrzeżenia: błąd {e}")
        return
    rows = []
    for w in data:
        obszary = w.get("obszary") or []
        woj = {str(o.get("wojewodztwo", "")).strip().lower() for o in obszary}
        wojewodztwa = "; ".join(sorted(woj))
        opisy = "; ".join(str(o.get("opis", "")) for o in obszary)
        zlewnie = "; ".join(sorted({str(k) for o in obszary for k in (o.get("kod_zlewni") or [])}))
        rows.append({
            "numer": w.get("numer"),
            "biuro": w.get("biuro"),
            "opublikowano": w.get("opublikowano"),
            "stopien": w.get("stopień"),
            "zdarzenie": w.get("zdarzenie"),
            "data_od": w.get("data_od"),
            "data_do": w.get("data_do"),
            "prawdopodobienstwo": w.get("prawdopodobienstwo"),
            "przebieg": w.get("przebieg"),
            "komentarz": w.get("komentarz"),
            "wojewodztwa": wojewodztwa,
            "obszary_opis": opisy,
            "kod_zlewni": zlewnie,
            "dotyczy_zlewni": bool(woj & WOJ_ZLEWNI),
            "fetched_at": NOW,
        })
    if rows:
        append(pd.DataFrame(rows), "warnings_hydro", ["numer", "biuro", "opublikowano"], keep="first")
    else:
        print("ostrzeżenia: brak aktywnych ostrzeżeń")


if __name__ == "__main__":
    collect_hydro()
    collect_synop()
    collect_forecast()
    collect_warnings()