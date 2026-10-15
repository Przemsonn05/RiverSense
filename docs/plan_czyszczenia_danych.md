# Wczytywanie i czyszczenie danych – plan

14.10.2026 · @Przemek · poprawiony 15.10.2026 po weryfikacji na danych i API IMGW (zmiany na końcu)

## Cel i wynik

Na koniec etapu (do 25 października) zespół ma jeden moduł `src/data/`, który jednym poleceniem zamienia surowe pliki z `data/historical/` i `data/live/` w czyste, spójne tabele w `data/processed/`. Z tych tabel korzystają potem EDA, cechy, trening i `predict.py` – nikt nie wczytuje surowych plików samodzielnie.

Cel projektu (README): dobowy stan wody `level_cm` na stacji **Kraków-Bielany (`150190340`)** na 1–3 dni do przodu, z ostrzeżeniem przy 370 cm (ostrzegawczy) i 520 cm (alarmowy).

**Wynik etapu**

- `python -m src.data.build` – buduje wszystkie tabele od zera.
- `data/processed/*.parquet` – tabele o ustalonych schematach (sekcja „Łączenie historii i live”).
- `reports/data_quality.md` – automatyczny raport: braki na stację i rok, najdłuższe luki, oznaczone anomalie.
- `tests/test_data.py` – testy, które zatrzymują build, gdy dane są błędne.

Poza zakresem: tworzenie cech (lagi, sumy kroczące) i EDA – to następne etapy.

## Przepływ danych

```
data/historical/  (hydro_daily, ice_daily, meteo_hourly_*)  ─┐
                                                             ├─ wczytanie → czas UTC → typy i nazwy
data/live/  (hydro, stations_meta, forecast_*, synop,        │  → siatka → kontrola zakresów i skoków
             warnings_hydro)                                ─┘  → krótkie luki → data/processed/
```

Ten sam kod uruchamiają trening (raz) i `predict.py` (co godzinę), więc model zawsze dostaje dane przygotowane identycznie.

## Wspólne zasady

| Zasada | Ustalenie | Dlaczego |
| --- | --- | --- |
| Czas | Wszystkie znaczniki czasu w **UTC**, typ `datetime64[ns, UTC]`; kolumna `time_utc` (godzinowe) lub `date` (dobowe) | Źródła zapisują czas różnie (tabela niżej) |
| Identyfikator stacji | `station_id` jako **tekst** (np. `"150190340"`), nigdy liczba ani nazwa | Nazwy się powtarzają (dwie Suche Beskidzkie) |
| Identyfikator punktu pogody | `point` = nazwa z `METEO_POINTS` (np. `zywiec`) | Te same nazwy w historii i live |
| Nazwy kolumn | snake\_case z jednostką: `level_cm`, `flow_m3s`, `precip_mm`, `snow_depth_cm`, `temp_c`, `soil_moist_m3m3` | Jednostka widoczna bez zaglądania do dokumentacji |
| Jednostki | cm (stan, śnieg), m³/s, mm, °C, m³/m³ | Open-Meteo podaje pokrywę śnieżną w m – przeliczamy na cm |
| Braki | Zawsze `NaN`, nigdy 0, 9999 ani pusty tekst | 0 mm opadu to informacja, brak pomiaru to co innego |
| Uzupełnione wartości | Kolumna `is_imputed` (bool) przy każdej interpolowanej wartości | Model i raport muszą wiedzieć, co było zmierzone |
| Źródło | Kolumna `source`: `hist`, `live`, `era5`, `forecast` | Łatwe filtrowanie i kontrola po połączeniu |
| Typy | Liczby `float32`, flagi `bool`, teksty `string` | Pliki 2–3× mniejsze, szybsze wczytywanie |
| Surowe pliki | **Tylko do odczytu** – skrypty nigdy ich nie nadpisują | Zawsze da się odbudować wynik od zera |

**Strefy czasowe w surowych plikach (sprawdzone 15.10.2026)**

| Plik | Kolumny | Strefa | Dowód |
| --- | --- | --- | --- |
| `hydro.csv` | `measured_at`, `flow_at`, `ice_at` | **UTC**, bez oznaczenia | o 15:15 UTC API podaje pomiar z 14:50; żaden pomiar nie jest późniejszy niż `fetched_at` |
| `hydro.csv`, `stations_meta.csv` | `fetched_at` | UTC (`Z`) | – |
| `forecast_*.csv` | `issued_at` (z `Z`), `valid_at` (bez) | UTC | zapytanie z `timezone=UTC` |
| `synop.csv` | `data_pomiaru` + `godzina_pomiaru` | UTC | godzina 9 pobrana o 10:01 UTC |
| `warnings_hydro.csv` | `opublikowano`, `data_od`, `data_do` | **Europe/Warsaw** | ostrzeżenie „opublikowane 09:13” pobrane o 08:01 UTC |
| `meteo_hourly_*.parquet` | `time_utc` | UTC | – |

## Dane historyczne

Historia jest już wstępnie oczyszczona przez `fetch_historical.py` (kody braków IMGW zamienione na `NaN`, daty z roku hydrologicznego przeliczone, tylko 19 stacji wybranych po kodzie), więc tu chodzi głównie o ciągłość szeregów i wykrycie błędnych pomiarów.

**A. Stany wody dobowe – `hydro_daily.parquet` + `ice_daily.parquet`**

1. **Wczytanie i typy:** `station_id` jako tekst, `date` jako data, liczby jako `float32`.
2. **Kontrola listy stacji:** dokładnie 19 kodów z `stations_found.csv` (błędne stacje Chełmek i jezioro Jeleń zostały już odrzucone przy pobieraniu).
3. **Okres:** tabele `processed` od **1 listopada 1980** (początek roku hydrologicznego 1981 – od tego dnia są dane z Bielan). Trening od 1983 r. zgodnie z README (podział 1983–2014 / 2015–2025) – to decyzja etapu modelu, nie czyszczenia.
4. **Pełny kalendarz:** dla każdej stacji siatka wszystkich dni od 1980-11-01 do 2025-10-31; brakujące dni = `NaN` (teraz są po prostu pominięte).
5. **Kontrola zakresu:** stan < 0 cm lub > rekord stacji + 100 cm → `is_suspect`. Rekordy z kolumny `max_level_cm` w `stations_found.csv` (np. Bielany 902 cm, 18.05.2010; wartość dobowa, nie chwilowa).
6. **Lód:** do tabeli dołączamy `ice_daily` jako kolumnę `ice_code` (brak wiersza = brak zjawisk) i flagę `has_ice`. Zator lodowy (`05`, `09`) i pokrywa (`04`) podnoszą stan bez wzrostu przepływu – w te dni skoków **nie zamieniamy na `NaN`**, tylko oznaczamy `is_suspect`.
7. **Skoki pojedynczego dnia:** zmiana > 150 cm w dobę, która wraca następnego dnia **i** nie występuje na stacjach sąsiednich **i** nie ma lodu → błąd odczytu, zamieniamy na `NaN`. Takich zmian > 150 cm jest w historii 441 (Jawiszowice 145, Smolice 70, Radziszów 59, Bielany 54) – większość to prawdziwe wezbrania, więc wszystkie trzy warunki są konieczne.
8. **Zmiany zera wodowskazu:** szukamy trwałych skoków poziomu (np. nagła zmiana rocznego minimum o > 30 cm przy podobnym przepływie). Jeśli występują, korygujemy przesunięciem albo ucinamy okres sprzed zmiany – decyzja w raporcie. Bieżącą rzędną zera mamy w `data/live/stations_meta.csv` (`gauge_zero_m`); nowa wartość pojawi się tam automatycznie przy zmianie.
9. **Uzupełnianie luk:** interpolacja liniowa tylko dla luk **≤ 3 dni** (`is_imputed = True`); dłuższe luki zostają `NaN`.
10. **Przepływ i temperatura wody:** te same kroki 4–9, ale nie są kluczowe – nie usuwamy dni z powodu braku przepływu.
11. **Metadane stacji:** tabela `stations.parquet` – kod, nazwa, rzeka, `river_km`, `lat`, `lon`, `gauge_zero_m`, progi (z `stations_meta.csv`), okres danych i flaga `main_feature`. `main_feature = False` dla trzech stacji: **Zabrzeg** `149180210` (historia od 2010), **Czaniec-Kobiernice** `149190120` (od 2013) i **Sucha Beskidzka – Stryszawka** `149190200` (od czerwca 2026 brak nowych odczytów live).

**B. Pogoda godzinowa – 7 plików `meteo_hourly_<punkt>.parquet`**

1. **Połączenie w jedną tabelę** z kolumną `point`, czas jako UTC.
2. **Ciągłość godzin:** sprawdzamy pełną siatkę godzinową od 1980-01-01. Obecnie pliki nie mają braków ani dziur i kończą się ok. 6 dni przed pobraniem (stan na 15.10.2026: do 9.10.2026 23:00) – skrypt pobierania już obcina niepełne dni ERA5.
3. **Jednostki i nazwy:** `snow_depth` z m na cm, nazwy kolumn wg wspólnych zasad.
4. **Zakresy fizyczne:** opad < 0 → 0; opad > 80 mm/h, temperatura poza −40…+45 °C, wilgotność gleby poza 0–0,6 → `is_suspect`. (Maksimum opadu w historii to 14,4 mm/h – próg 80 to tylko zabezpieczenie.)
5. **Znaczenie znacznika czasu:** opad o godzinie 01:00 to suma z 00:00–01:00 (godzina poprzedzająca) – zapisujemy to w dokumentacji tabeli, żeby przy agregacji nie przesunąć opadu o godzinę.
6. **Agregacja dobowa** (`meteo_daily`): suma opadu, deszczu i śniegu, średnia/min/max temperatury, średnia wilgotność gleby, pokrywa śnieżna o 06 UTC – granice doby zgodne z definicją dobowego stanu IMGW (otwarta decyzja nr 1).

## Dane live

Dane live są surowe: wszystko zapisane jako tekst, możliwe przestarzałe pomiary i luki po pominiętych uruchomieniach. Ten kod będzie też uruchamiany co godzinę przez `predict.py`, więc musi być szybki i odporny na błędy.

**A. Stany wody – `hydro.csv` + `stations_meta.csv`**

1. **Typy:** `station_id` jako tekst, liczby przez `pd.to_numeric(errors="coerce")` (puste i `None` → `NaN`).
2. **Czas pomiaru na UTC:** `measured_at` jest już w UTC bez oznaczenia strefy → `tz_localize("UTC")`. **Nie** przeliczamy z czasu polskiego – zmiana czasu 25.10.2026 tych danych nie dotyczy.
3. **Duplikaty:** jeden wiersz na (`station_id`, `measured_at`) – `collect.py` już to zapewnia; build tylko sprawdza.
4. **Przestarzałe pomiary:** gdy `measured_at` jest starszy niż `fetched_at` o > 3 h → wiersz odrzucamy (`stale`). Typowe opóźnienie to 0,4–1,2 h; dotyczy to praktycznie tylko Stryszawki. Od 15.10.2026 `fetched_at` to czas **pierwszego** pobrania pomiaru; w starszych wierszach – ostatniego (przy godzinowym pobieraniu różnica jest pomijalna).
5. **Przepływ:** nie używamy w modelu. IMGW aktualizuje go rzadko (dla Bielan ostatni `flow_at` to 27.11.2025); jeśli potrzebny do kontroli – tylko gdy `flow_at` jest młodszy niż 24 h.
6. **Lód:** `ice_code` (`0` = brak, kody jak w historii, zbierane od 15.10.2026) → `has_ice`, ta sama rola co w historii (krok A.6).
7. **Siatka godzinowa:** ostatni pomiar w każdej pełnej godzinie UTC na stację; luki **≤ 3 h** interpolujemy (`is_imputed`), dłuższe zostają `NaN`.
8. **Zakresy i skoki:** te same reguły co w historii, ale w skali godzin (np. skok > 50 cm/h wracający w następnej godzinie → `NaN`).
9. **Agregacja dobowa:** z siatki godzinowej liczymy wartość dobową **tak samo jak IMGW** (średnia lub odczyt o 06 UTC – otwarta decyzja nr 1), żeby live było porównywalne z historią.
10. **Progi i metadane:** `warning_cm`, `alarm_cm`, `gauge_zero_m`, `river_km` bierzemy z `stations_meta.csv` (ostatni wiersz na stację) do `stations.parquet`, nie trzymamy ich w tabeli pomiarów. Zmiana `gauge_zero_m` w trakcie zbierania → przesunięcie odczytów i wpis w raporcie jakości.

**B. Prognozy pogody – `forecast_RRRR-MM.csv`**

1. **Wczytanie:** wszystkie pliki miesięczne (`glob("forecast_*.csv")`) w jedną tabelę.
2. **Typy i czas:** `issued_at` i `valid_at` na UTC (oba są w UTC, tylko `valid_at` nie ma oznaczenia strefy). `issued_at` to pełna godzina pobrania.
3. **Kontrola zawartości:** dokładnie 7 punktów jak w historii i kolumny `precipitation, rain, snowfall, snow_depth, temperature_2m, soil_moisture_0_to_7cm` (ta sama głębokość gleby co w ERA5).
4. **Wyprzedzenie:** kolumna `lead_h = valid_at − issued_at`, zakres od −47 do +71 h (`past_days=1`, `forecast_days=3`). Ujemne `lead_h` to analiza modelu, dodatnie – prognoza.
5. **Wilgotność gleby z ECMWF:** ok. 0,3% braków (bywa co 3 h lub brak przy błędzie zapytania) – interpolacja w obrębie jednej prognozy (`issued_at`), nigdy między różnymi prognozami.
6. **Dwie tabele wynikowe:**
   - `forecast_archive` – wszystkie prognozy (do oceny trafności i testu na żywo),
   - `forecast_latest` – dla każdej godziny `valid_at` najnowsza prognoza wydana **przed** tą godziną (to, co model naprawdę wiedział w danym momencie).
7. **„Obserwowany” opad dla okresu live:** ERA5 jest dostępne z ok. 6-dniowym opóźnieniem i dociągane przez `historical.yml` (pobranie przyrostowe, ok. minuty). Dla ostatnich ~6 dni, których ERA5 jeszcze nie ma, używamy godzin z `lead_h` od −24 do 0 z najnowszej prognozy (`source = forecast`).

**C. Pogoda zmierzona – `synop.csv`**

1. **Czas:** `data_pomiaru` + `godzina_pomiaru` → UTC (sprawdzone: godziny synoptyczne IMGW są w UTC).
2. **Typy i nazwy:** liczby (temperatura, opad, wiatr, ciśnienie, wilgotność) na `float32`, nazwy wg wspólnych zasad.
3. **Duplikaty:** jeden wiersz na stację i godzinę (`collect.py` już to zapewnia).
4. **Rola:** tylko kontrola i dashboard (porównanie z prognozą), nie cecha modelu – brak odpowiednika w historii.

**D. Ostrzeżenia IMGW – `warnings_hydro.csv`**

1. **Czas:** `opublikowano`, `data_od`, `data_do` są w **czasie polskim** → `tz_localize("Europe/Warsaw", ambiguous="NaT")` → UTC; `data_do = 9999-12-31` → `NaT` (ostrzeżenie bez ustalonego końca).
2. **Stopień:** `stopien` jako liczba. `-1` to ostrzeżenie przed **suszą hydrologiczną** (wszystkie takie wiersze mają `zdarzenie = "Susza hydrologiczna"`), nie odwołanie – flaga `is_drought`. Ostrzeżenia powodziowe mają stopień 1–3.
3. **Filtr:** tabela dla zlewni (`dotyczy_zlewni = True`) do porównań i pełna tabela do archiwum.

## Łączenie historii i live

Wynikiem są tabele o wspólnych schematach, w których historia i live leżą obok siebie i różnią się tylko kolumną `source`.

| Plik w `data/processed/` | Klucz | Zawartość | Źródła |
| --- | --- | --- | --- |
| `stations.parquet` | `station_id` | Nazwa, rzeka, `river_km`, `lat`, `lon`, `gauge_zero_m`, progi, `main_feature`, okres danych | historia + `stations_meta.csv` |
| `levels_daily.parquet` | `station_id`, `date` | `level_cm`, `flow_m3s`, `has_ice`, `is_imputed`, `is_suspect`, `source` | historia 1980-11-01 – 2025-10-31 + live od 12.10.2026 |
| `levels_hourly.parquet` | `station_id`, `time_utc` | `level_cm`, `has_ice`, `is_imputed`, `source` | tylko live |
| `meteo_hourly.parquet` | `point`, `time_utc` | opad, deszcz, śnieg, pokrywa śnieżna, temperatura, wilgotność gleby, `source` | ERA5 od 1980 do ok. 6 dni wstecz + analiza z prognozy dla ostatnich dni |
| `meteo_daily.parquet` | `point`, `date` | agregaty dobowe z `meteo_hourly` | jw. |
| `forecast_archive.parquet` | `point`, `issued_at`, `valid_at` | wszystkie prognozy + `lead_h` | live |
| `forecast_latest.parquet` | `point`, `valid_at` | najnowsza prognoza znana przed `valid_at` | live |
| `synop_hourly.parquet` | `station_id`, `time_utc` | pogoda zmierzona | live |
| `warnings.parquet` | `numer`, `biuro`, `opublikowano` | ostrzeżenia IMGW + flagi zlewni i suszy | live |

Dodatkowo `levels_daily_wide.parquet` – ta sama tabela w układzie data × stacja (kolumny `lvl_<station_id>`), wygodna do EDA i modelu.

**Na co uważać przy łączeniu**

- **Luka w stanach wody listopad 2025 – październik 2026:** między archiwum IMGW a live nie ma stanów wody (pogoda ERA5 jest ciągła). Nigdy nie interpolujemy przez tę przerwę; każdy szereg ma kolumnę `source`, a funkcje tworzące cechy muszą pilnować ciągłości.
- **Ten sam zestaw stacji i punktów:** test sprawdza, że każda stacja z `main_feature = True` ma dane w obu źródłach.
- **Inne źródło opadu w live:** ERA5 w historii, analiza modelu prognostycznego w live – rozkłady mogą się różnić. W raporcie jakości porównujemy je na wspólnym okresie (od 12.10.2026, gdy ERA5 go obejmie).
- **Definicja doby:** dobowe wartości live liczone dokładnie tak, jak IMGW liczy archiwum (otwarta decyzja nr 1).

## Walidacja i testy

Każdy build kończy się testami – jeśli któryś nie przejdzie, tabele nie są zapisywane, a GitHub Actions pokaże czerwony krzyżyk. Lepiej zatrzymać prognozę, niż policzyć ją na błędnych danych.

**Testy w `tests/test_data.py` (pytest)**

- [ ] Klucze są unikalne w każdej tabeli (brak duplikatów stacja + czas).
- [ ] Czas jest typu UTC i rosnący w obrębie stacji/punktu.
- [ ] Siatka jest pełna: liczba godzin/dni = oczekiwana (braki jako `NaN`, nie brakujące wiersze).
- [ ] Zakresy fizyczne: stan 0–1200 cm, opad 0–80 mm/h, temperatura −40…+45 °C, wilgotność gleby 0–0,6.
- [ ] Dokładnie 19 stacji; każda stacja z `main_feature = True` i każdy z 7 punktów pogody występuje w historii i w live.
- [ ] Na Bielanach maksimum historii 850–960 cm i pojawia się w maju 2010 (obecnie 902 cm, 18.05.2010 – test „zdrowego rozsądku”).
- [ ] Każdy wiersz `ice_daily` ma odpowiadający dzień w `hydro_daily`.
- [ ] Najnowszy pomiar live na Bielanach nie jest starszy niż 3 h (test używany przez `predict.py`).
- [ ] Małe testy jednostkowe na sztucznych danych: ostrzeżenia IMGW przy zmianie czasu (25.10), usuwanie duplikatów, interpolacja tylko krótkich luk, skoki przy lodzie nie są usuwane.

**Raport jakości `reports/data_quality.md`** (generowany automatycznie przy buildzie)

- % braków na stację i rok (tabela + w EDA mapa ciepła),
- najdłuższa luka każdej stacji,
- liczba wartości oznaczonych `is_suspect` i usuniętych skoków, z datami (osobno dni z lodem),
- liczba pominiętych godzin w danych live i przestarzałych odczytów,
- zmiany `gauge_zero_m` i progów w `stations_meta.csv`.

## Struktura kodu i podział pracy

Kod dzielimy na małe pliki według źródła danych, żeby kilka osób mogło pracować równolegle bez konfliktów w gicie.

```
src/data/
├── config.py      # ścieżki, lista 19 stacji i 7 punktów, progi, strefy czasowe źródeł (jedno źródło prawdy)
├── schema.py      # nazwy kolumn, typy, funkcja validate(df, schemat)
├── utils.py       # wspólne: to_utc(), full_grid(), interpolate_short_gaps(), flag_spikes()
├── hist_hydro.py  # historia: stany wody + zjawiska lodowe
├── hist_meteo.py  # historia: pogoda ERA5
├── live_hydro.py  # live: hydro.csv + stations_meta.csv
├── live_meteo.py  # live: forecast_*.csv + synop.csv
├── live_warnings.py
├── stations.py    # tabela stations.parquet
├── combine.py     # łączenie historii i live
└── build.py       # python -m src.data.build – wszystko po kolei + testy + raport
tests/test_data.py
notebooks/01_data_check.ipynb   # szybki podgląd wyników (nie logika!)
```

Zasada: notebooki tylko **używają** funkcji z `src/data/`, nie zawierają własnej logiki czyszczenia – inaczej `predict.py` liczyłby dane inaczej niż trening.

**Kolejność i podział (14–25 października)**

| Zadanie | Kto | Termin | Zależy od |
| --- | --- | --- | --- |
| `config.py`, `schema.py`, `utils.py` | Data engineer | 16 paź | – |
| `hist_hydro.py` + `stations.py` | Data engineer | 19 paź | utils |
| `hist_meteo.py` | Analityk danych | 19 paź | utils |
| `live_hydro.py` | ML engineer | 20 paź | utils |
| `live_meteo.py` + `live_warnings.py` | Frontend / ostrzeżenia | 20 paź | utils |
| `combine.py` + `build.py` | Data engineer | 22 paź | wszystkie powyżej |
| `tests/test_data.py` + raport jakości | Kierownik projektu | 23 paź | build |
| Przegląd, poprawki, merge do `main` | Wszyscy | 25 paź | – |

Każda osoba pracuje na własnej gałęzi i wystawia pull request; review robi osoba odpowiedzialna za `combine.py`, bo to ona musi połączyć wszystkie części.

## Otwarte decyzje

| Nr | Pytanie | Stan | Propozycja / rozstrzygnięcie |
| --- | --- | --- | --- |
| 1 | Czym jest dobowy stan w archiwum IMGW: odczytem porannym czy średnią z doby? | **otwarta** | Opis formatu (`CODZ_publiczne_format.txt`) tego nie mówi. Założyć odczyt poranny (ok. 06 UTC) i trzymać definicję w jednej funkcji w `utils.py`, żeby dało się ją zmienić. Sprawdzić: zapytanie do IMGW albo porównanie z archiwum za 2026, gdy zostanie opublikowane |
| 2 | Od którego roku dane? | rozstrzygnięta | Tabele od 1.11.1980, trening od 1983 (README) |
| 3 | Jak długie luki uzupełniamy? | propozycja | ≤ 3 dni (historia), ≤ 3 h (live); porównać błąd interpolacji na sztucznie usuniętych fragmentach |
| 4 | Co z Zabrzegiem, Czańcem i Stryszawką? | rozstrzygnięta | Zostają w danych, `main_feature = False` |
| 5 | Czy dociągać ERA5 dla okresu live? | rozstrzygnięta | Tak: `historical.yml` pobiera pogodę przyrostowo (ok. minuty); uruchamiać ręcznie raz na kilka dni albo dodać harmonogram. Bez zmian w `collect.py` |

## Zmiany względem wersji z 14.10.2026

- `measured_at` w `hydro.csv` jest w **UTC**, nie w czasie polskim (sprawdzone na API); w czasie polskim są za to ostrzeżenia IMGW.
- Plik prognoz to `forecast_RRRR-MM.csv` (miesięczne), nie `forecast.csv`; nie ma w nim punktu `bielsko` ani kolumny `soil_moisture_0_to_1cm`.
- Chełmek i jezioro Jeleń nie występują w danych – krok usuwania zastąpiony kontrolą listy 19 stacji.
- Rekord Bielan w archiwum dobowym to 902 cm (18.05.2010), nie 957 cm; rekordy brane z `stations_found.csv`.
- `main_feature = False` także dla Stryszawki; poprawna nazwa to Czaniec-Kobiernice.
- Pogoda ERA5 sięga do ok. 6 dni przed pobraniem (teraz do 9.10.2026) i nie ma braków; decyzja nr 5 rozstrzygnięta.
- `stopien = -1` to susza hydrologiczna, nie odwołanie.
- Nowe dane: zjawiska lodowe (`ice_daily.parquet`, `ice_code` w `hydro.csv`) i metadane stacji (`stations_meta.csv`: zero wodowskazu, kilometr rzeki, progi).
