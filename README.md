# RiverSense
A Machine Learning-Based System for River Water Level Prediction Using Hydrological and Weather Data

Prognoza stanu wody na Wiśle w Krakowie (wodowskaz Kraków-Bielany) na **1–3 dni do przodu**
z ostrzeżeniem przy stanie ostrzegawczym (**370 cm**) i alarmowym (**520 cm**). Model korzysta
ze stanów wody na stacjach w górze rzeki i z opadów w zlewni.

## Przebieg projektu

| Etap | Stan | Wynik |
|---|---|---|
| 1. Wybór stacji i źródeł danych | ✅ zakończony | 19 stacji IMGW w zlewni Wisły powyżej Krakowa, 7 punktów pogodowych |
| 2. Dane historyczne | ✅ zakończony | stany wody 1980–2025, pogoda ERA5 1980 – obecnie, zjawiska lodowe |
| 3. Zbieranie danych na żywo | 🔄 trwa od 12.10.2026 | stany wody, prognozy pogody i ostrzeżenia IMGW co godzinę (GitHub Actions) |
| 4. Przygotowanie danych | ✅ zakończony 15.10.2026 | czyste tabele w `data/processed/` + raport jakości |
| 5. Eksploracyjna analiza danych (EDA) | 🔄 w toku | – |
| 6. Cechy i model | ⏳ planowany | trening 1983–2014, walidacja 2015–2025 |
| 7. Test na danych live | ⏳ planowany | porównanie z oficjalnymi ostrzeżeniami IMGW |

## Wyniki

**Dane historyczne – 45 lat obserwacji**
- Kraków-Bielany: komplet pomiarów od 1.11.1980 (4 brakujące dni uzupełnione interpolacją).
- Stan ≥ 370 cm (ostrzegawczy) w **158 dniach**, ≥ 520 cm (alarmowy) w **38 dniach** – wystarczająco wiele
  wezbrań, żeby model nauczył się zachowania rzeki przy wysokiej wodzie.
- Największe wezbrania: **902 cm** (18.05.2010), 867 cm (10.07.1997), 826 cm (26.07.2001).

**Jakość danych** (pełny raport: `reports/data_quality.md`)
- 12 z 16 głównych stacji ma poniżej 0,2% brakujących dni, pozostałe 4 (Zator, Wadowice, Osielec,
  Smolice) – 2–5%. Zabrzeg, Czaniec-Kobiernice (krótka historia) i Stryszawka (brak danych live) zostają w danych, ale nie są głównymi cechami modelu.
- Usunięte zostały tylko 2 błędne odczyty; prawdziwe wezbrania i skoki przy zjawiskach lodowych
  zostają nienaruszone.
- Wykryto 12 możliwych zmian zera wodowskazu (najwięcej w Wadowicach) – do oceny w EDA.
- Pogoda ERA5: bez braków, 1980 – obecnie.

**Ustalenia o danych na żywo**
- Czasy pomiarów IMGW są w UTC (ostrzeżenia – w czasie polskim); pomiar trafia do nas średnio 0,7 h po wykonaniu.
- Prognozy pogody zapisujemy w postaci znanej w danej chwili, więc test na żywo będzie uczciwy:
  model nie zobaczy przyszłego opadu.

**Wstępna analiza cech** (gradient boosting, test na latach 2015–2025) – o jakości prognozy decydują głównie:
1. zmiana stanu wody w ostatniej dobie na stacjach w górze rzeki (prognoza na 1 dzień),
2. aktualny stan wody w Krakowie,
3. prognozowany opad na 48–72 h (prognoza na 2–3 dni).

## Otwarte kwestie

- **Definicja doby IMGW** – nie wiadomo, czy stan dobowy w archiwum to odczyt poranny, czy średnia;
  przyjęto odczyt o 06 UTC (`src/data/config.py`).
- **Luka 11.2025–10.2026** – IMGW opublikuje stany wody za ten rok później; nie jest potrzebna do treningu.
- **Prognoza a faktyczny opad** – model uczony na faktycznym opadzie będzie na prognozach gorszy;
  ocena tej różnicy to jeden z celów testu na żywo.

## Struktura repozytorium

```
collect.py, fetch_historical.py   pobieranie danych (live co godzinę, historia jednorazowo)
data/historical/, data/live/      surowe dane (tylko do odczytu)
src/data/                         przygotowanie danych -> data/processed/
notebooks/RiverSense.ipynb        główny notatnik: wstęp, preprocessing, EDA
reports/data_quality.md           raport jakości danych
docs/                             opis danych i zasady ich czyszczenia
```

## Uruchomienie

```bash
pip install -r requirements.txt
python -m src.data.build      # buduje czyste tabele w data/processed/ (ok. 15 s)
```

Potem `notebooks/RiverSense.ipynb`. Bot dopisuje dane co godzinę, więc przed pracą zawsze `git pull`.

Szczegóły: opis plików i kolumn – `docs/dane.md`, zasady czyszczenia – `docs/plan_czyszczenia_danych.md`.
