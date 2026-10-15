"""Funkcje wspólne dla danych historycznych i live."""
import numpy as np
import pandas as pd

from . import config


def to_utc(values, tz="UTC", ambiguous="NaT"):
    """Tekst lub daty -> datetime64[ns, UTC].
    tz: strefa, w której zapisano czasy bez oznaczenia strefy (z oznaczeniem, np. 'Z', są
    przeliczane bez zmian). Przy zmianie czasu niejednoznaczne godziny -> NaT."""
    t = pd.to_datetime(pd.Series(values), errors="coerce", format="ISO8601")
    if t.dt.tz is None:
        t = t.dt.tz_localize(tz, ambiguous=ambiguous, nonexistent="NaT")
    return t.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")


def full_grid(df, key, time_col, start, end, freq, keys=None):
    """Pełna siatka key × czas: brakujące dni/godziny jako wiersze z NaN.
    keys: lista obiektów (domyślnie te, które występują w df)."""
    tz = df[time_col].dt.tz

    def stamp(t):
        t = pd.Timestamp(t)
        return t.tz_localize(tz) if t.tzinfo is None and tz is not None else t

    times = pd.date_range(stamp(start), stamp(end), freq=freq)
    keys = sorted(df[key].unique() if keys is None else keys)
    idx = pd.MultiIndex.from_product([keys, times], names=[key, time_col])
    return (df.set_index([key, time_col]).reindex(idx).reset_index())


def interpolate_short_gaps(s, max_gap):
    """Interpolacja liniowa tylko luk o długości ≤ max_gap kroków.
    Zwraca (uzupełniona seria, maska uzupełnionych wartości). Luki na brzegach zostają NaN."""
    isna = s.isna()
    gap_len = isna.groupby((~isna).cumsum()).transform("sum")
    filled = s.interpolate(method="linear", limit_area="inside")
    mask = isna & (gap_len <= max_gap) & filled.notna()
    return s.where(~mask, filled), mask


def interpolate_wide(wide, max_gap):
    """interpolate_short_gaps dla każdej kolumny tabeli szerokiej (czas × stacja)."""
    out, mask = wide.copy(), pd.DataFrame(False, index=wide.index, columns=wide.columns)
    for col in wide.columns:
        out[col], mask[col] = interpolate_short_gaps(wide[col], max_gap)
    return out, mask


def neighbors(station_id):
    """Stacje bezpośrednio powyżej i poniżej w sieci rzecznej (config.STATIONS)."""
    down = config.STATIONS[station_id][2]
    up = [sid for sid, (_, _, d) in config.STATIONS.items() if d == station_id]
    return up + ([down] if down else [])


def flag_spikes(wide, threshold, neighbor_threshold, protect=None):
    """Pojedyncze skoki będące błędem odczytu (tabela szeroka czas × stacja, krok regularny).

    Skok w chwili t, gdy jednocześnie:
      1. |x[t] − x[t−1]| > threshold i wartość wraca w t+1 (przeciwny znak, > threshold),
         a |x[t+1] − x[t−1]| < połowy skoku,
      2. żadna sąsiednia stacja nie zmienia się o > neighbor_threshold w t−1…t+1
         (prawdziwe wezbranie widać na kilku stacjach),
      3. stacja nie ma w t zjawisk lodowych (protect – tabela bool tego samego kształtu).
    """
    up = wide.diff()
    down = wide.shift(-1) - wide
    net = (wide.shift(-1) - wide.shift(1)).abs()
    spike = ((up.abs() > threshold) & (down.abs() > threshold)
             & (np.sign(up) != np.sign(down)) & (net < up.abs() / 2))

    change = up.abs()
    moving = change.rolling(3, center=True, min_periods=1).max() > neighbor_threshold
    for sid in wide.columns:
        nb = [n for n in neighbors(sid) if n in wide.columns]
        if nb:
            spike[sid] &= ~moving[nb].any(axis=1)
    if protect is not None:
        spike &= ~protect.reindex_like(spike).fillna(False).astype(bool)
    return spike.fillna(False).astype(bool)


def range_suspect(values, low=None, high=None):
    """Wartości poza zakresem [low, high] -> True (NaN -> False)."""
    out = pd.Series(False, index=values.index)
    if low is not None:
        out |= values < low
    if high is not None:
        out |= values > high
    return out


def day_label(time_utc):
    """Doba, do której należy godzina (znacznik = koniec godziny, np. 01:00 = 00–01).
    Dla config.DAILY_DEFINITION = '06utc' doba D to godziny (D−1 06:00, D 06:00]."""
    shifted = time_utc - pd.Timedelta(hours=config.DAY_END_HOUR) - pd.Timedelta(nanoseconds=1)
    day = shifted.dt.floor("D") + pd.Timedelta(days=1 if config.DAY_END_HOUR else 0)
    return day.dt.tz_localize(None)


def longest_gap(s):
    """Najdłuższa seria NaN (liczba kroków) i data jej początku."""
    isna = s.isna()
    if not isna.any():
        return 0, None
    groups = (~isna).cumsum()[isna]
    sizes = groups.value_counts()
    g = sizes.idxmax()
    return int(sizes.max()), s.index[isna & ((~isna).cumsum() == g)][0]
