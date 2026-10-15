"""Stałe przetwarzania danych – jedno źródło prawdy dla całego modułu src.data.

Wartości progów i okresów pochodzą z docs/plan_czyszczenia_danych.md. Zmieniamy je tutaj,
nigdy w notebookach, żeby trening i predict.py liczyły dane identycznie.
"""
from pathlib import Path

# ---------------------------------------------------------------- ścieżki
ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "data" / "historical"
LIVE = ROOT / "data" / "live"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

# ---------------------------------------------------------------- stacje hydrologiczne
TARGET = "150190340"  # Kraków-Bielany – cel prognozy

# station_id -> (nazwa, rzeka, stacja w dół rzeki). Stacja w dół to najbliższy wodowskaz,
# do którego spływa woda; None = brak stacji poniżej w naszym zestawie.
STATIONS = {
    # Wisła
    "149180100": ("Skoczów", "Wisła", "149180210"),
    "149180210": ("Zabrzeg", "Wisła", "149180240"),
    "149180240": ("Goczałkowice", "Wisła", "149190060"),
    "149190060": ("Jawiszowice", "Wisła", "150190170"),
    "150190170": ("Pustynia", "Wisła", "150190260"),
    "150190260": ("Smolice", "Wisła", "150190340"),
    "150190340": ("Kraków-Bielany", "Wisła", None),
    # Soła – uchodzi do Wisły między Jawiszowicami a Pustynią
    "149190100": ("Żywiec", "Soła", "149190120"),
    "149190120": ("Czaniec-Kobiernice", "Soła", "150190160"),
    "150190160": ("Oświęcim", "Soła", "150190170"),
    # Przemsza – uchodzi do Wisły powyżej Pustyni
    "150190100": ("Niwka", "Biała Przemsza", "150190180"),
    "150190180": ("Jeleń", "Przemsza", "150190170"),
    # Skawa i Stryszawka – Skawa uchodzi do Wisły powyżej Smolic
    "149190260": ("Osielec", "Skawa", "149190210"),
    "149190200": ("Sucha Beskidzka", "Stryszawka", "149190210"),
    "149190210": ("Sucha Beskidzka", "Skawa", "149190180"),
    "149190180": ("Wadowice", "Skawa", "149190170"),
    "149190170": ("Zator", "Skawa", "150190260"),
    # Dopływy w rejonie Krakowa. Rudawa uchodzi w Krakowie – prawdopodobnie już poniżej
    # wodowskazu Bielany (do sprawdzenia w EDA); tu łączymy ją z Bielanami jako sąsiada.
    "149190270": ("Radziszów", "Skawinka", "150190340"),
    "150190310": ("Balice", "Rudawa", "150190340"),
}

# Stacje bez roli głównej cechy modelu (zostają w danych)
NOT_MAIN_FEATURE = {
    "149180210": "historia dopiero od 2010 r.",
    "149190120": "historia dopiero od 2013 r.",
    "149190200": "od czerwca 2026 r. brak nowych odczytów live",
}

# ---------------------------------------------------------------- punkty pogodowe
METEO_POINTS = ["krakow", "wadowice", "makow_podhalanski", "zywiec",
                "wisla_beskidy", "oswiecim", "katowice"]

# ---------------------------------------------------------------- okresy
HIST_START = "1980-11-01"   # początek roku hydrologicznego 1981 – od tego dnia są dane z Bielan
HIST_END = "2025-10-31"     # koniec archiwum IMGW
METEO_START = "1980-01-01"

# ---------------------------------------------------------------- definicja doby (OTWARTA DECYZJA NR 1)
# Czy dobowy stan IMGW to odczyt poranny, czy średnia z doby – nie wiadomo (opis formatu milczy).
# "06utc": stan = odczyt o 06 UTC, doba opadu = (D-1 06:00, D 06:00] UTC
# "mean":  stan = średnia z doby UTC, doba opadu = (D 00:00, D+1 00:00] UTC
DAILY_DEFINITION = "06utc"
DAY_END_HOUR = {"06utc": 6, "mean": 0}[DAILY_DEFINITION]
SNOW_DEPTH_HOUR = 6  # pokrywa śnieżna dobowa = wartość o 06 UTC

# ---------------------------------------------------------------- czyszczenie
MAX_GAP_DAYS = 3        # historia: interpolujemy luki ≤ 3 dni
MAX_GAP_HOURS = 3       # live: interpolujemy luki ≤ 3 h
STALE_HOURS = 3         # live: pomiar starszy od pobrania o > 3 h jest przestarzały
FLOW_MAX_AGE_HOURS = 24 # live: przepływ tylko, gdy młodszy niż 24 h

SPIKE_DAY_CM = 150          # skok dobowy uznawany za podejrzany
SPIKE_DAY_NEIGHBOR_CM = 50  # zmiana na sąsiedniej stacji, która potwierdza prawdziwe wezbranie
SPIKE_HOUR_CM = 50
SPIKE_HOUR_NEIGHBOR_CM = 15
RECORD_MARGIN_CM = 100      # stan > rekord stacji + 100 cm -> is_suspect
ZERO_SHIFT_CM = 30          # zmiana rocznego minimum sugerująca zmianę zera wodowskazu

# Zakresy fizyczne (wartości spoza -> is_suspect; także testy)
LEVEL_RANGE = (0, 1200)
PRECIP_MAX = 80.0
TEMP_RANGE = (-40.0, 45.0)
SOIL_RANGE = (0.0, 0.6)

# Strefy czasowe surowych plików (sprawdzone 15.10.2026, patrz plan)
TZ_IMGW_HYDRO = "UTC"
TZ_IMGW_WARNINGS = "Europe/Warsaw"

# Okno "obserwowanego" opadu z prognozy dla godzin bez ERA5. Zawsze bierzemy najnowszą prognozę,
# więc analizy sprzed 24–48 h używamy tylko tam, gdzie nie ma nowszej (początek zbierania danych).
OBSERVED_LEAD_H = (-48, 0)
