"""Wykresy do README (docs/img/*.png, wersja jasna i ciemna).

    python -m src.data.build && python docs/figures.py
"""
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import config, load_table  # noqa: E402

OUT = Path(__file__).parent / "img"
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7", series="#2a78d6",
                  seq=["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835", series="#3987e5",
                 seq=["#1a1a19", "#104281", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"]),
}
WARNING, ALARM = "#fab219", "#d03b3b"
MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]


def style(ax, t):
    ax.set_facecolor(t["surface"])
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], labelsize=9, length=0)
    ax.grid(axis="y", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def figure(t, w, h):
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(t["surface"])
    style(ax, t)
    return fig, ax


def title(fig, t, text, sub):
    h = fig.get_figheight()
    fig.text(0.012, 1 - 0.12 / h, text, color=t["ink"], fontsize=12, fontweight="bold", va="top")
    fig.text(0.012, 1 - 0.42 / h, sub, color=t["ink2"], fontsize=9, va="top")


def bielany_levels(levels):
    s = (levels[(levels["station_id"] == config.TARGET) & (levels["source"] == "hist")]
         .set_index("date")["level_cm"])
    peaks = [("2010-05-18", "maj 2010"), ("1997-07-10", "lipiec 1997"), ("2001-07-26", "lipiec 2001")]
    for name, t in THEMES.items():
        fig, ax = figure(t, 10, 3.6)
        ax.plot(s.index, s.values, color=t["series"], linewidth=0.7)
        for level, color, label in [(370, WARNING, "stan ostrzegawczy 370 cm"),
                                    (520, ALARM, "stan alarmowy 520 cm")]:
            ax.axhline(level, color=color, linewidth=1.2, linestyle=(0, (4, 3)))
            ax.text(s.index[-1], level + 12, label, color=t["ink2"], fontsize=8.5, ha="right")
        for day, label in peaks:
            d = pd.Timestamp(day)
            ax.annotate(f"{label}\n{s[d]:.0f} cm", (d, s[d]), xytext=(8, -4), textcoords="offset points",
                        color=t["ink"], fontsize=8.5, va="top")
        ax.set_ylim(0, 1000)
        ax.set_xlim(s.index[0], s.index[-1])
        ax.set_ylabel("stan wody [cm]", color=t["muted"], fontsize=9)
        title(fig, t, "Wisła w Krakowie-Bielanach, 1980–2025",
              "dobowy stan wody (archiwum IMGW) – cel prognozy projektu")
        fig.subplots_adjust(left=0.07, right=0.985, top=0.8, bottom=0.09)
        fig.savefig(OUT / f"bielany_levels_{name}.png", facecolor=t["surface"])
        plt.close(fig)


def seasonality(levels):
    s = levels[(levels["station_id"] == config.TARGET) & (levels["source"] == "hist")]
    days = s[s["level_cm"] >= 370].groupby(s["date"].dt.month).size().reindex(range(1, 13), fill_value=0)
    for name, t in THEMES.items():
        fig, ax = figure(t, 10, 3.2)
        ax.bar(range(12), days.values, width=0.7, color=t["series"])
        for i, v in enumerate(days.values):
            if v:
                ax.text(i, v + 1, str(v), ha="center", color=t["ink2"], fontsize=8.5)
        ax.set_xticks(range(12), MONTHS)
        ax.set_ylabel("liczba dni", color=t["muted"], fontsize=9)
        title(fig, t, "Kiedy Wisła w Krakowie przekracza stan ostrzegawczy",
              f"dni ze stanem ≥ 370 cm w poszczególnych miesiącach, 1980–2025 (razem {days.sum()})")
        fig.subplots_adjust(left=0.07, right=0.985, top=0.78, bottom=0.1)
        fig.savefig(OUT / f"seasonality_{name}.png", facecolor=t["surface"])
        plt.close(fig)


def completeness(stations):
    missing = pd.read_csv(config.REPORTS / "missing_by_year.csv", index_col="station_id",
                          dtype={"station_id": str})
    order = [sid for sid in config.STATIONS]
    missing = missing.reindex(order)
    labels = [f"{stations.at[sid, 'name']} ({stations.at[sid, 'river']})" for sid in order]
    for name, t in THEMES.items():
        fig, ax = figure(t, 10, 5.6)
        ax.grid(False)
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", t["seq"])
        im = ax.imshow(missing.values, aspect="auto", cmap=cmap, vmin=0, vmax=100, interpolation="none")
        years = missing.columns.astype(int)
        ticks = [i for i, y in enumerate(years) if y % 5 == 0]
        ax.set_xticks(ticks, [years[i] for i in ticks])
        ax.set_yticks(range(len(labels)), labels, fontsize=8.5)
        ax.spines["bottom"].set_visible(False)
        cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
        cb.outline.set_visible(False)
        cb.ax.tick_params(colors=t["muted"], labelsize=8, length=0)
        cb.set_label("% brakujących dni", color=t["muted"], fontsize=8.5)
        title(fig, t, "Kompletność danych historycznych",
              "% dni bez pomiaru stanu wody w roku hydrologicznym (lata hydrologiczne 1981–2025)")
        fig.subplots_adjust(left=0.25, right=0.92, top=0.88, bottom=0.06)
        fig.savefig(OUT / f"completeness_{name}.png", facecolor=t["surface"])
        plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    levels = load_table("levels_daily")
    stations = load_table("stations").set_index("station_id")
    bielany_levels(levels)
    seasonality(levels)
    completeness(stations)
    print(f"Zapisano wykresy w {OUT}")
