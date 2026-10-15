"""
Jednorazowe pobranie danych historycznych do treningu modelu.

1) IMGW – dobowe stany wody, przepływy i temperatura wody (archiwum od 1951 r.)
   dla Krakowa-Bielan i stacji w zlewni powyżej Krakowa.
2) Open-Meteo (reanaliza ERA5 + ERA5-Land) – godzinowy opad, deszcz, śnieg, grubość pokrywy śnieżnej, temperatura,
   wilgotność gleby dla punktów w zlewni (od 1980 r.).

Wynik (razem ok. 20–60 MB, format Parquet):
    data/historical/hydro_daily.parquet       – stany i przepływy dobowe, wszystkie stacje
    data/historical/stations_found.csv        – jakie stacje znaleziono i za jakie lata
    data/historical/ice_daily.parquet         – zjawiska lodowe i zarastanie (tylko dni ze zjawiskiem)
    data/historical/meteo_hourly_<punkt>.parquet – pogoda godzinowa, osobny plik na punkt

Skrypt można przerwać i uruchomić ponownie – pobrane już kawałki są w data/cache/
i nie będą pobierane drugi raz. Pogoda jest aktualizowana przyrostowo: pełne lata zostają
z istniejących plików meteo_hourly_*, pobierany jest tylko ostatni rok.

Uruchomienie:  pip install requests pandas pyarrow && python fetch_historical.py
"""
import io
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/historical")
CACHE = Path("data/cache")  # surowe pliki pośrednie – NIE commitujemy (patrz .gitignore)
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

IMGW_DAILY = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/dobowe/"

# Stacje po kodzie IMGW – ten sam zestaw co HYDRO_STATIONS w collect.py.
# Tylko po kodzie: wybór po nazwie łapał też inne stacje o tej samej nazwie (np. jezioro Jeleń).
STATION_CODES = {
    # Wisła
    "149180100",  # Skoczów
    "149180240",  # Goczałkowice
    "149180210",  # Zabrzeg
    "149190060",  # Jawiszowice
    "150190170",  # Pustynia
    "150190260",  # Smolice
    "150190340",  # Kraków-Bielany – CEL PROGNOZY
    # Soła
    "149190100",  # Żywiec
    "149190120",  # Czaniec-Kobiernice
    "150190160",  # Oświęcim
    # Skawa i Stryszawka
    "149190210",  # Sucha Beskidzka (Skawa)
    "149190200",  # Sucha Beskidzka (Stryszawka)
    "149190260",  # Osielec
    "149190180",  # Wadowice
    "149190170",  # Zator
    # Przemsza
    "150190100",  # Niwka (Biała Przemsza)
    "150190180",  # Jeleń (Przemsza)
    # Dopływy w rejonie Krakowa
    "149190270",  # Radziszów (Skawinka)
    "150190310",  # Balice (Rudawa)
}

# Punkty pogodowe w zlewni Wisły powyżej Krakowa
METEO_POINTS = {
    "krakow": (50.06, 19.94),
    "wadowice": (49.88, 19.49),          # Skawa
    "makow_podhalanski": (49.73, 19.68),  # górna Skawa
    "zywiec": (49.69, 19.19),             # Soła
    "wisla_beskidy": (49.65, 18.86),      # źródła Wisły
    "oswiecim": (50.04, 19.22),
    "katowice": (50.26, 19.02),           # Przemsza
}
METEO_VARS = "precipitation,rain,snowfall,temperature_2m,soil_moisture_0_to_7cm"
SNOW_VARS = "snow_depth"  # grubość pokrywy śnieżnej [m], z ERA5-Land – ważna dla wezbrań roztopowych
METEO_START_YEAR = 1980

session = requests.Session()
session.headers["User-Agent"] = "student-flood-forecast-project"


def http_get(url, params=None, tries=6):
    """GET z ponawianiem: przy limicie zapytań (429) lub błędzie serwera czeka i próbuje ponownie."""
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=120)
            if r.status_code == 429:
                wait = 65 * (attempt + 1)
                print(f"  limit zapytań – czekam {wait} s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            wait = 10 * (attempt + 1)
            print(f"  błąd {e} – ponawiam za {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"Nie udało się pobrać {url}")


# ---------------------------------------------------------------- IMGW dobowe

def list_zip_urls(url):
    """Przeszukuje katalog archiwum IMGW (i podkatalogi lat) i zwraca listę plików ZIP."""
    html = http_get(url).text
    hrefs = re.findall(r'href="([^"?#]+)"', html)
    zips = [url + h for h in hrefs if h.lower().endswith(".zip")]
    for h in hrefs:
        if re.fullmatch(r"\d{4}/", h):
            zips += list_zip_urls(url + h)
    return sorted(set(zips))


CODZ_COLUMNS = ["station_id", "station", "river", "hydro_year", "hydro_month",
                "day", "level_cm", "flow_m3s", "water_temp_c", "month"]
# zjaw_*: zjawiska lodowe i zarastanie (opis: ZJAW_publiczne_format.txt w archiwum).
# Wiersze są tylko dla dni, w których wystąpiło zjawisko; brak miesiąca kalendarzowego.
ZJAW_COLUMNS = ["station_id", "station", "river", "hydro_year", "hydro_month",
                "day", "ice_thickness_cm", "ice_code", "ice_pct", "overgrowth_code"]


def parse_imgw_csv(raw: bytes, columns=CODZ_COLUMNS) -> pd.DataFrame:
    """Plik dobowy IMGW: bez nagłówka, kolumny jak w `columns` (CODZ_COLUMNS: stany i przepływy,
    ZJAW_COLUMNS: zjawiska lodowe).
    Zwykle cp1250 i separator ',', ale IMGW wydał lata hydrologiczne 2023–2024 inaczej
    (patrz UWAGA.txt w archiwum) – obsługujemy wszystkie trzy warianty:
      2023: UTF-8 z BOM, separator ';'
      2024: cp1250, ale cały wiersz w cudzysłowie: "149180020,CHAŁUPKI,...,""2024"",..."
      reszta: cp1250, separator ','"""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    df = pd.read_csv(io.StringIO(text), header=None, sep=sep, quotechar='"',
                     dtype=str, skipinitialspace=True, on_bad_lines="skip")
    if df.shape[1] == 1:
        # Wariant 2024: cały wiersz był jednym polem w cudzysłowie – parsujemy jego treść
        df = pd.read_csv(io.StringIO("\n".join(df[0].dropna())), header=None, sep=",",
                         quotechar='"', dtype=str, skipinitialspace=True, on_bad_lines="skip")
    if df.shape[1] < len(columns):
        return pd.DataFrame()
    df = df.iloc[:, :len(columns)]
    df.columns = columns
    return df.apply(lambda s: s.str.strip())


def fetch_imgw_files(prefix, columns, urls):
    """Pobiera pliki ZIP archiwum o danym prefiksie (codz / zjaw), zostawia tylko nasze stacje.
    Każdy plik trafia do cache, więc ponowne uruchomienie nie pobiera go drugi raz."""
    urls = [u for u in urls if u.split("/")[-1].lower().startswith(prefix)]
    print(f"IMGW {prefix}: {len(urls)} plików ZIP")
    frames = []
    for i, url in enumerate(urls, 1):
        part = CACHE / ("imgw_" + url.split("/")[-1].replace(".zip", ".parquet"))
        if part.exists():
            frames.append(pd.read_parquet(part))
            continue
        print(f"  [{i}/{len(urls)}] {url.split('/')[-1]}")
        zf = zipfile.ZipFile(io.BytesIO(http_get(url).content))
        dfs = [parse_imgw_csv(zf.read(n), columns)
               for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))]
        df = pd.concat(dfs) if dfs else pd.DataFrame()
        if not df.empty:
            df = df[df["station_id"].isin(STATION_CODES)]
        df.to_parquet(part, index=False)
        frames.append(df)
        time.sleep(0.5)  # grzecznie wobec serwera IMGW
    return pd.concat(frames, ignore_index=True)


def fetch_imgw_daily(urls):
    print("IMGW: stany wody dobowe")
    # codz_* to stany i przepływy; zjaw_* (zjawiska lodowe) mają inny układ kolumn – fetch_imgw_ice()
    df = fetch_imgw_files("codz", CODZ_COLUMNS, urls)
    for col in ["hydro_year", "day", "month", "level_cm", "flow_m3s", "water_temp_c"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Rok hydrologiczny zaczyna się 1 listopada: listopad i grudzień należą do roku kalendarzowego wcześniej
    year = df["hydro_year"] - (df["month"] >= 11).astype(int)
    df["date"] = pd.to_datetime(dict(year=year, month=df["month"], day=df["day"]), errors="coerce")

    # Kody braków danych IMGW
    df.loc[df["level_cm"] >= 9999, "level_cm"] = pd.NA
    df.loc[df["flow_m3s"] >= 99999, "flow_m3s"] = pd.NA
    df.loc[df["water_temp_c"] >= 99, "water_temp_c"] = pd.NA

    df = (df.dropna(subset=["date"])
            [["date", "station_id", "station", "river", "level_cm", "flow_m3s", "water_temp_c"]]
            .drop_duplicates(["station_id", "date"])
            .sort_values(["station_id", "date"]))
    df["level_cm"] = df["level_cm"].astype("float32")
    df["flow_m3s"] = df["flow_m3s"].astype("float32")
    df["water_temp_c"] = df["water_temp_c"].astype("float32")
    df.to_parquet(OUT / "hydro_daily.parquet", index=False)

    summary = (df.groupby(["station_id", "station", "river"])
                 .agg(first=("date", "min"), last=("date", "max"),
                      days=("level_cm", "count"), max_level_cm=("level_cm", "max"))
                 .reset_index())
    summary.to_csv(OUT / "stations_found.csv", index=False)
    print(f"IMGW: zapisano {len(df):,} wierszy dla {len(summary)} stacji")
    print(summary.to_string(index=False))


def fetch_imgw_ice(urls):
    """Zjawiska lodowe (śryż, kra, pokrywa, zatory). Lód podnosi stan wody bez wzrostu przepływu,
    więc przy czyszczeniu zimowe skoki stanu trzeba odróżnić od błędów odczytu.
    Brak wiersza w danym dniu = brak zjawisk na stacji."""
    print("IMGW: zjawiska lodowe")
    df = fetch_imgw_files("zjaw", ZJAW_COLUMNS, urls)
    for col in ["hydro_year", "hydro_month", "day", "ice_thickness_cm", "ice_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Brak miesiąca kalendarzowego – liczymy go ze wskaźnika miesiąca hydro (1 = listopad)
    month = (df["hydro_month"] + 9) % 12 + 1
    year = df["hydro_year"] - (month >= 11).astype(int)
    df["date"] = pd.to_datetime(dict(year=year, month=month, day=df["day"]), errors="coerce")

    # Grubość lodu: 999 = brak pomiaru; procent zapisany jako mnożnik ×10 (3 = 30%)
    df.loc[df["ice_thickness_cm"] >= 999, "ice_thickness_cm"] = pd.NA
    df["ice_pct"] = df["ice_pct"] * 10
    for col in ["ice_code", "overgrowth_code"]:
        df[col] = df[col].replace("", pd.NA).astype("string")

    df = (df.dropna(subset=["date"])
            [["date", "station_id", "ice_code", "ice_pct", "ice_thickness_cm", "overgrowth_code"]]
            .drop_duplicates(["station_id", "date"])
            .sort_values(["station_id", "date"]))
    df["date"] = df["date"].astype("datetime64[us]")  # jak w hydro_daily
    df["ice_pct"] = df["ice_pct"].astype("float32")
    df["ice_thickness_cm"] = df["ice_thickness_cm"].astype("float32")
    df.to_parquet(OUT / "ice_daily.parquet", index=False)
    print(f"IMGW: zapisano {len(df):,} dni ze zjawiskami lodowymi lub zarastaniem")


# ---------------------------------------------------------------- Open-Meteo godzinowe

def fetch_meteo_year(name, lat, lon, year, hourly, model, tag):
    """Jeden rok danych godzinowych dla punktu; wynik w cache, więc nie pobieramy drugi raz.
    Wyjątek: rok pobrany niepełny (bieżący) pobieramy ponownie – inaczej cache zatrzymałby
    dane na dniu pierwszego pobrania."""
    part = CACHE / f"{tag}_{name}_{year}.parquet"
    if part.exists() and pd.read_parquet(part)["time"].max() < f"{year}-12-31T23:00":
        part.unlink()
    if not part.exists():
        end = min(pd.Timestamp(f"{year}-12-31"), pd.Timestamp.now() - pd.Timedelta(days=6))
        end = end.strftime("%Y-%m-%d")
        print(f"  Open-Meteo {tag} {name} {year}")
        d = http_get("https://archive-api.open-meteo.com/v1/archive", params=dict(
            latitude=lat, longitude=lon, start_date=f"{year}-01-01", end_date=end,
            hourly=hourly, models=model, timezone="UTC",
        )).json()
        pd.DataFrame(d["hourly"]).to_parquet(part, index=False)
        time.sleep(3)  # darmowy limit Open-Meteo: ok. 600 zapytań/min, 5000/h (ważonych)
    return pd.read_parquet(part)


def fetch_meteo_hourly():
    """Aktualizacja przyrostowa: lata pełne bierzemy z istniejącego pliku w data/historical/,
    a pobieramy tylko ostatni (niepełny) rok i nowsze. Dzięki temu ponowne uruchomienie trwa
    minutę zamiast godziny i dociąga ERA5 dla okresu zbierania danych live."""
    last_year = pd.Timestamp.now(tz="UTC").year
    for name, (lat, lon) in METEO_POINTS.items():
        frames, start = [], METEO_START_YEAR
        existing = OUT / f"meteo_hourly_{name}.parquet"
        if existing.exists():
            old = pd.read_parquet(existing)
            start = old["time_utc"].max().year  # ten rok może być niepełny – pobieramy go od nowa
            frames.append(old[old["time_utc"] < f"{start}-01-01"]
                          .rename(columns={"time_utc": "time"}))
        for year in range(start, last_year + 1):
            weather = fetch_meteo_year(name, lat, lon, year, METEO_VARS, "era5", "meteo")
            # Pokrywa śnieżna jest tylko w ERA5-Land (0,1°) – osobne zapytanie, łączymy po czasie
            snow = fetch_meteo_year(name, lat, lon, year, SNOW_VARS, "era5_land", "snow")
            year_df = weather.merge(snow, on="time", how="left")
            frames.append(year_df.assign(time=pd.to_datetime(year_df["time"])))
        df = pd.concat(frames, ignore_index=True).rename(columns={"time": "time_utc"})
        df["time_utc"] = pd.to_datetime(df["time_utc"]).astype("datetime64[us]")
        df = df.drop_duplicates("time_utc").sort_values("time_utc")
        num = df.columns.drop("time_utc")
        df[num] = df[num].astype("float32")
        df.to_parquet(OUT / f"meteo_hourly_{name}.parquet", index=False)
        print(f"Open-Meteo {name}: {len(df):,} godzin, {df['time_utc'].min()} – {df['time_utc'].max()}")


if __name__ == "__main__":
    print("IMGW: szukam plików archiwum dobowego…")
    imgw_urls = list_zip_urls(IMGW_DAILY)
    fetch_imgw_daily(imgw_urls)
    fetch_imgw_ice(imgw_urls)
    fetch_meteo_hourly()
    total = sum(p.stat().st_size for p in OUT.glob("*")) / 1e6
    print(f"\nGotowe. Rozmiar data/historical: {total:.1f} MB")