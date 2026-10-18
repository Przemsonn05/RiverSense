# Raport jakości danych

Wygenerowano: 2026-10-18 21:43 UTC · `python -m src.data.build`
Definicja doby: `06utc` (otwarta decyzja nr 1, `config.DAILY_DEFINITION`)

## Tabele

| tabela | wiersze |
|---|---|
| stations | 19 |
| levels_daily | 312398 |
| levels_hourly | 2812 |
| meteo_hourly | 2871610 |
| meteo_daily | 119658 |
| forecast_archive | 86592 |
| forecast_latest | 1273 |
| synop_hourly | 425 |
| warnings | 100 |
| levels_daily_wide | 16442 |

## Stany wody – historia (1980-11-01 – 2025-10-31)

| stacja | station_id | main | braki % | najdłuższa luka [dni] | od | uzupełnione | skoki usunięte | podejrzane | dni z lodem |
|---|---|---|---|---|---|---|---|---|---|
| Skoczów (Wisła) | 149180100 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 1231 |
| Zabrzeg (Wisła) | 149180210 | nie | 71.2 | 10957 | 1980-11-01 | 2 | 0 | 0 | 4 |
| Goczałkowice (Wisła) | 149180240 | tak | 0.0 | 0 |  | 0 | 0 | 1 | 493 |
| Jawiszowice (Wisła) | 149190060 | tak | 0.0 | 0 |  | 2 | 2 | 2 | 451 |
| Żywiec (Soła) | 149190100 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 1960 |
| Czaniec-Kobiernice (Soła) | 149190120 | nie | 73.8 | 12053 | 1980-11-01 | 0 | 0 | 0 | 4 |
| Zator (Skawa) | 149190170 | tak | 2.8 | 365 | 2005-11-01 | 9 | 0 | 0 | 915 |
| Wadowice (Skawa) | 149190180 | tak | 4.4 | 730 | 1980-11-01 | 0 | 0 | 0 | 1602 |
| Sucha Beskidzka (Stryszawka) | 149190200 | nie | 0.0 | 0 |  | 0 | 0 | 0 | 2177 |
| Sucha Beskidzka (Skawa) | 149190210 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 2235 |
| Osielec (Skawa) | 149190260 | tak | 5.1 | 730 | 1980-11-01 | 1 | 0 | 0 | 1665 |
| Radziszów (Skawinka) | 149190270 | tak | 0.1 | 15 | 2019-01-23 | 0 | 0 | 0 | 1182 |
| Niwka (Biała Przemsza) | 150190100 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 280 |
| Oświęcim (Soła) | 150190160 | tak | 0.0 | 0 |  | 0 | 0 | 1 | 705 |
| Pustynia (Wisła) | 150190170 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 14 |
| Jeleń (Przemsza) | 150190180 | tak | 0.0 | 0 |  | 0 | 0 | 0 | 5 |
| Smolice (Wisła) | 150190260 | tak | 2.2 | 365 | 1980-11-01 | 0 | 0 | 1 | 92 |
| Balice (Rudawa) | 150190310 | tak | 0.1 | 9 | 2012-02-15 | 3 | 0 | 0 | 652 |
| Kraków-Bielany (Wisła) | 150190340 | tak | 0.0 | 0 |  | 4 | 0 | 0 | 31 |

Braki na stację i rok hydrologiczny: `reports/missing_by_year.csv` (mapa ciepła w EDA).
Skoki przy lodzie oznaczone jako podejrzane (nieusunięte): 5.

**Usunięte skoki (błędy odczytu)**

| date | station_id | level_cm |
|---|---|---|
| 1989-07-10 00:00:00 | 149190060 | 460.0 |
| 2002-05-30 00:00:00 | 149190060 | 553.0 |

**Kandydaci na zmianę zera wodowskazu** – trwała zmiana minimum rocznego o > 30 cm.
Niczego nie korygujemy automatycznie; decyzja zespołu (korekta przesunięciem, ucięcie okresu
albo naturalna zmiana koryta / praca zbiornika).

| station_id | hydro_year | min_before_cm | min_after_cm | shift_cm |
|---|---|---|---|---|
| 149190120 | 2022 | 186.0 | 147.0 | -39.0 |
| 149190180 | 1987 | 112.0 | 78.0 | -34.0 |
| 149190180 | 1992 | 70.0 | 32.0 | -38.0 |
| 149190180 | 1996 | 22.0 | 70.0 | 48.0 |
| 149190180 | 1999 | 70.0 | 18.0 | -52.0 |
| 149190180 | 2009 | 11.0 | 107.0 | 96.0 |
| 149190210 | 2010 | 104.0 | 73.0 | -31.0 |
| 149190260 | 2001 | 164.0 | 128.0 | -36.0 |
| 149190260 | 2010 | 110.0 | 75.0 | -35.0 |
| 149190260 | 2021 | 85.0 | 45.0 | -40.0 |
| 150190170 | 2002 | 138.0 | 194.0 | 56.0 |
| 150190260 | 2006 | 18.0 | 94.0 | 76.0 |

## Stany wody – live

- Wiersze surowe: 2810, duplikaty: 0, mediana opóźnienia pomiaru: 0.69 h
- Przestarzałe odczyty (> 3 h, odrzucone): {'149190200': 1}
- Usunięte skoki godzinowe: 0

| station_id | brak godzin (surowe) | brak po uzupełnieniu | uzupełnione |
|---|---|---|---|
| 149180100 | 17 | 15 | 2 |
| 149180210 | 3 | 0 | 3 |
| 149180240 | 17 | 15 | 2 |
| 149190060 | 3 | 0 | 3 |
| 149190100 | 3 | 0 | 3 |
| 149190120 | 3 | 0 | 3 |
| 149190170 | 17 | 15 | 2 |
| 149190180 | 18 | 15 | 3 |
| 149190200 | 148 | 148 | 0 |
| 149190210 | 17 | 15 | 2 |
| 149190260 | 36 | 34 | 2 |
| 149190270 | 17 | 15 | 2 |
| 150190100 | 5 | 0 | 5 |
| 150190160 | 8 | 1 | 7 |
| 150190170 | 3 | 0 | 3 |
| 150190180 | 17 | 15 | 2 |
| 150190260 | 17 | 15 | 2 |
| 150190310 | 10 | 0 | 10 |
| 150190340 | 3 | 0 | 3 |

Zmiany zera wodowskazu / progów w `stations_meta.csv`:

_brak_

## Pogoda

- ERA5 do: 2026-10-09 23:00:00+00:00, brakujące godziny w ERA5: 0, wartości podejrzane: 0
- Prognozy: 129 wydań (2026-10-13 09:00:00+00:00 – 2026-10-18 21:00:00+00:00), pominięte godziny wydań: 4, lead_h (-47, 71)
- Wilgotność gleby w prognozach: braki 96, uzupełnione 0
- Godziny bez ERA5 i bez analizy z prognozy (po końcu ERA5): 48 (2026-10-10 00:00:00+00:00 – 2026-10-11 23:00:00+00:00)

## Ostrzeżenia IMGW

- Wszystkie: 100, dla zlewni: 27, susza: 94

Ostrzeżenia powodziowe dla zlewni:

_brak_
