# RiverSense
A Machine Learning-Based System for River Water Level Prediction Using Hydrological and Weather Data

Celem projektu jest prognoza stanu wody na Wiśle w Krakowie (wodowskaz Kraków-Bielany)
na 1–3 dni do przodu oraz generowanie ostrzeżeń przy przekroczeniu stanu ostrzegawczego (370 cm)
i alarmowego (520 cm). Model korzysta ze stanów wody na stacjach w górze rzeki i z opadów w zlewni.

Ten plik opisuje dane zebrane w projekcie: skąd pochodzą, za co odpowiadają i do czego służą.

## Stan projektu

- Dane historyczne: pobrane i zweryfikowane (stany wody od 1950 r., pogoda od 1980 r.).
- Dane live: zbierane automatycznie co godzinę od 12.10.2026 (GitHub Actions).
- Do zrobienia: przygotowanie cech, model, ewaluacja na danych live.

## Dane historyczne i dane live: po co są

| | Dane historyczne (`data/historical/`) | Dane live (`data/live/`) |
|---|---|---|
| Rola | trening i walidacja modelu | test w warunkach rzeczywistych, działanie systemu na bieżąco |
| Okres | stany wody 1950 – 31.10.2025, pogoda 1980 – obecnie (opóźnienie ok. 6 dni) | od 12.10.2026, przybywa co godzinę |
| Rozdzielczość | stany wody dobowe, pogoda godzinowa | godzinowa |
| Pogoda | faktyczna (reanaliza ERA5) | prognoza z chwili pobrania (Open-Meteo) |

Dane historyczne obejmują kilkadziesiąt lat i wiele wezbrań, w tym powódź z września 2024 r.
Stan ostrzegawczy w Krakowie był przekroczony w 158 dniach, a alarmowy w 38. Tylko na takich
danych model może nauczyć się zachowania rzeki przy wysokiej wodzie.

Dane live są potrzebne, bo w historii znamy faktyczny opad, a w praktyce model dostanie tylko
prognozę opadu. Zapisujemy prognozy dokładnie w takiej postaci, w jakiej były dostępne w danej
chwili, co pozwala uczciwie ocenić model. Kilka tygodni danych live nie wystarczy do treningu
(jedna pora roku, zwykle bez wezbrań), ale wystarczy do testu.

Planowany podział: trening 1983–2014, walidacja 2015–2025, test na danych live wraz
z porównaniem z oficjalnymi ostrzeżeniami IMGW.

## Opis plików

### `data/historical/hydro_daily.parquet`: stany wody, dobowe

Źródło: archiwum IMGW (danepubliczne.imgw.pl). 19 stacji, jeden wiersz na stację i dobę.

| Kolumna | Opis |
|---|---|
| `date` | doba |
| `station_id` | kod stacji IMGW (tabela stacji niżej) |
| `level_cm` | stan wody [cm]: główna zmienna projektu, cecha i cel prognozy |
| `flow_m3s` | przepływ [m³/s]: dla Krakowa tylko ok. 2% dni, nieużywany |
| `water_temp_c` | temperatura wody [°C]: nieużywana |

Kraków-Bielany ma dane od listopada 1980 r. z 4 brakującymi dniami. Przed 1980 r. wiele stacji
nie ma pomiarów w archiwum IMGW, dlatego do modelu używamy danych od 1983 r.

### `data/historical/meteo_hourly_<punkt>.parquet`: pogoda, godzinowa

Źródło: Open-Meteo, reanaliza ERA5 i ERA5-Land. 7 plików, po jednym na punkt w zlewni, bez braków.

| Kolumna | Opis |
|---|---|
| `time_utc` | godzina (UTC) |
| `precipitation` | opad całkowity [mm]: najważniejsza zmienna pogodowa |
| `rain`, `snowfall` | deszcz [mm] i śnieg [cm]: składniki `precipitation` |
| `temperature_2m` | temperatura powietrza [°C] |
| `soil_moisture_0_to_7cm` | wilgotność gleby [m³/m³]: wpływa na spływ po opadzie |
| `snow_depth` | pokrywa śnieżna [m]: istotna przy roztopach |

`data/historical/stations_found.csv` zawiera spis stacji z zakresem dat i maksymalnym stanem.

### `data/live/hydro.csv`: bieżące stany wody

Źródło: API IMGW. Te same stacje co w danych historycznych.

| Kolumna | Opis |
|---|---|
| `station_id` | kod stacji IMGW |
| `measured_at` | czas pomiaru, czas lokalny (Europe/Warsaw), nie UTC |
| `water_level_cm` | stan wody [cm], odpowiednik `level_cm` |
| `warning_cm`, `alarm_cm` | stan ostrzegawczy i alarmowy stacji: progi do ostrzeżeń, nie cechy modelu |
| `flow_m3s`, `flow_at`, `fetched_at` | pomocnicze, nieużywane w modelu |

### `data/live/forecast_RRRR-MM.csv`: prognozy pogody

Źródło: Open-Meteo (wilgotność gleby z modelu ECMWF). Co godzinę zapisywana jest prognoza
na 3 dni dla tych samych 7 punktów co w historii. Każdy miesiąc ma osobny plik.

| Kolumna | Opis |
|---|---|
| `point` | punkt pogodowy, te same nazwy co w `meteo_hourly_<punkt>` |
| `issued_at` | kiedy prognoza była znana (UTC) |
| `valid_at` | godzina, której dotyczy prognoza (UTC) |
| pozostałe | te same zmienne i jednostki co w danych historycznych |

Przy prognozie wykonywanej w chwili T wolno używać tylko wierszy z `issued_at <= T`.

### `data/live/warnings_hydro.csv`: ostrzeżenia hydrologiczne IMGW

Wszystkie aktywne ostrzeżenia IMGW w Polsce. Kolumna `dotyczy_zlewni` oznacza ostrzeżenia
dla woj. małopolskiego i śląskiego. Plik służy wyłącznie do porównania ostrzeżeń naszego
modelu z ostrzeżeniami IMGW.

### `data/live/synop.csv`: obserwacje synoptyczne IMGW

Temperatura, wiatr, wilgotność, ciśnienie i opad z 3 stacji (Kraków-Balice, Bielsko-Biała, Zakopane).
Plik nie jest używany jako źródło cech. Tych danych nie ma w historii, dublują dane z Open-Meteo,
a Zakopane leży poza zlewnią Wisły powyżej Krakowa. Może służyć do kontroli prognoz opadu.

## Stacje i punkty pogodowe

| `station_id` | Stacja | Rzeka |
|---|---|---|
| 150190340 | Kraków-Bielany (cel prognozy) | Wisła |
| 150190260 | Smolice | Wisła |
| 150190170 | Pustynia | Wisła |
| 149190060 | Jawiszowice | Wisła |
| 149180240 | Goczałkowice | Wisła |
| 149180100 | Skoczów | Wisła |
| 150190160 | Oświęcim | Soła |
| 149190100 | Żywiec | Soła |
| 149190170 | Zator | Skawa |
| 149190180 | Wadowice | Skawa |
| 149190260 | Osielec | Skawa |
| 149190210 | Sucha Beskidzka | Skawa |
| 149190270 | Radziszów | Skawinka |
| 150190310 | Balice | Rudawa |
| 150190100 | Niwka | Biała Przemsza |
| 150190180 | Jeleń | Przemsza |
| 149190200 | Sucha Beskidzka | Stryszawka |
| 149180210 | Zabrzeg | Wisła |
| 149190120 | Czaniec-Kobiernice | Soła |

Trzech ostatnich stacji nie używamy w modelu. Stryszawka nie przesyła danych live od czerwca 2026 r.,
Zabrzeg ma historię dopiero od 2010 r., a Czaniec dopiero od 2013 r.

Punkty pogodowe: `krakow`, `wadowice`, `makow_podhalanski` (górna Skawa), `zywiec` (Soła),
`wisla_beskidy` (źródła Wisły), `oswiecim`, `katowice` (Przemsza).

## Najważniejsze cechy

Wstępna analiza (gradient boosting, test na latach 2015–2025) wskazuje, że o jakości prognozy
decydują głównie:

1. zmiana stanu wody w ciągu ostatniej doby na stacjach w górze rzeki (prognoza na 1 dzień),
2. aktualny stan wody w Krakowie,
3. prognozowany opad na 48–72 h (prognoza na 2–3 dni).

Mniejsze znaczenie mają opad z ostatniej doby, wilgotność gleby i pora roku. Pokrywa śnieżna
i temperatura zostają w modelu ze względu na wezbrania roztopowe.

## Uwagi

- Strefy czasowe: `measured_at` w `hydro.csv` jest w czasie lokalnym, a pozostałe dane w UTC.
- Rozdzielczość: historyczne stany wody są dobowe, więc model jest dobowy, a dane live agregujemy do doby.
- Luka: brak stanów wody od 1.11.2025 do 11.10.2026. IMGW opublikuje ten rok później,
  a do treningu nie jest on potrzebny.
- Model uczony na faktycznym opadzie będzie na prognozach opadu gorszy niż w testach historycznych.
  Ocena tej różnicy jest jednym z celów testu na danych live.

## Automatyzacja i praca z repozytorium

| Workflow | Kiedy | Co robi |
|---|---|---|
| `collect.yml` | co godzinę, automatycznie | uruchamia `collect.py` i commituje dane do `data/live/` |
| `historical.yml` | ręcznie (Actions → fetch-historical-data → Run workflow) | uruchamia `fetch_historical.py` i commituje `data/historical/` |

Danych historycznych nie trzeba pobierać ponownie, chyba że IMGW opublikuje nowy rok
albo zmieni się lista stacji. Przed pracą zawsze wykonaj `git pull`, bo bot commituje dane
co godzinę. Plików w `data/` nie edytujemy ręcznie.

Wymagania: `pip install -r requirements.txt`.

```python
import pandas as pd
h = pd.read_parquet("data/historical/hydro_daily.parquet")
levels = h.pivot(index="date", columns="station_id", values="level_cm").loc["1983":]
precip = pd.read_parquet("data/historical/meteo_hourly_zywiec.parquet")
```
