"""Wczytywanie i czyszczenie danych RiverSense (plan: docs/plan_czyszczenia_danych.md).

Budowa wszystkich tabel:   python -m src.data.build
Wczytanie gotowej tabeli:  from src.data import load_table; load_table("levels_daily")
"""
import pandas as pd

from . import config


def load_table(name):
    """Tabela z data/processed/ (najpierw uruchom python -m src.data.build)."""
    path = config.PROCESSED / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Brak {path} – uruchom: python -m src.data.build")
    return pd.read_parquet(path)
