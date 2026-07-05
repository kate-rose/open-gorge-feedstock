"""
process_fia.py — Skamania County FIA Feedstock Analysis
Produces a single plot-level JSON where each plot contains per-category
volume estimates (raw and TPA-expanded) for all five size classes.
"""

import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "extracted"
OUTPUT_FILE = Path(__file__).parent / "skamania_feedstock.json"

SKAMANIA_COUNTYCD = 59
LIVE_STATUSCD = 1

SPCD_NAMES = {
    11:  "True fir spp.",
    202: "Douglas-fir",
    263: "Western hemlock",
    264: "Mountain hemlock",
    431: "Grand fir",
    17:  "Pacific silver fir",
    19:  "Subalpine fir",
    20:  "White fir",
    22:  "Noble fir",
    746: "Western redcedar",
    747: "Alaska yellow-cedar",
    351: "Red alder",
    352: "White alder",
    122: "Ponderosa pine",
    108: "Lodgepole pine",
    15:  "White pine",
    41:  "Port-Orford-cedar",
    312: "Oregon white oak",
    242: "Bigleaf maple",
    231: "Pacific madrone",
    93:  "Engelmann spruce",
    492: "Black cottonwood",
    542: "Quaking aspen",
    815: "Willow spp.",
    920: "Other hardwood",
    661: "Cascara",
}

# CLT suitability: "excellent" | "good" | "fair" | "limited"
CLT_SUITABILITY = {
    11:  "fair",        # True fir spp. — Abies, likely Pacific true firs
    202: "excellent",   # Douglas-fir — gold standard
    263: "good",        # Western hemlock
    264: "good",        # Mountain hemlock
    431: "fair",        # Grand fir
    17:  "fair",        # Pacific silver fir
    19:  "fair",        # Subalpine fir
    20:  "fair",        # White fir
    22:  "fair",        # Noble fir
    746: "limited",     # Western redcedar — dimensional stability issues
    747: "limited",     # Alaska yellow-cedar
    351: "limited",     # Red alder — hardwood, different process
    352: "limited",     # White alder
    122: "good",        # Ponderosa pine
    108: "fair",        # Lodgepole pine
    15:  "good",        # White pine
    41:  "fair",        # Port-Orford-cedar
    312: "limited",     # Oregon white oak — hardwood
    242: "limited",     # Bigleaf maple — hardwood
    231: "limited",     # Pacific madrone — hardwood
    93:  "good",        # Engelmann spruce
    492: "limited",     # Black cottonwood
    542: "limited",     # Quaking aspen
    815: "limited",     # Willow
    920: "limited",     # Other hardwood
    661: "limited",     # Cascara
}

# OWNCD → (human label, fiscal category)
# Fiscal categories: federal | tribal | taxable | state | unknown
OWNCD_INFO = {
    11: ("National Forest",        "federal"),
    12: ("National Park",          "federal"),
    13: ("Other Federal",          "federal"),
    21: ("State / DNR Trust",      "state"),
    22: ("Local Government",       "state"),
    23: ("State / Local Unknown",  "state"),
    24: ("State",                  "state"),
    25: ("State",                  "state"),
    31: ("Corporate Timber",       "taxable"),
    32: ("Non-industrial Private", "taxable"),
    33: ("Other Private",          "taxable"),
    46: ("Tribal",                 "tribal"),
}

# Five size categories. Each tree lands in exactly one bucket based on DIA.
SIZE_CATEGORIES = [
    ("biomass",       0.0,   5.0),   # chips, hog fuel, wood fiber
    ("small_timber",  5.0,   9.0),   # mass timber feedstock (CLT/NLT)
    ("sawlog",        9.0,  15.0),   # conventional dimensional lumber
    ("premium",      15.0,  21.0),   # premium lumber, glulam beams
    ("large_timber", 21.0, 999.0),   # high-value veneer, specialty products
]


def _assign_category(dia) -> str | None:
    if pd.isna(dia):
        return None
    for cat, lo, hi in SIZE_CATEGORIES:
        if lo <= dia < hi:
            return cat
    return None


def load_table(filename: str, usecols: list) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        sys.exit(f"ERROR: {filename} not found in {DATA_DIR}")
    print(f"  Loading {path.name} ...")
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    print(f"    {len(df):,} rows")
    return df


def main():
    print("=== Skamania FIA Feedstock Processor ===\n")

    plot_cols = ["CN", "COUNTYCD", "LAT", "LON", "INVYR"]
    tree_cols = ["PLT_CN", "STATUSCD", "DIA", "VOLCFGRS", "TPA_UNADJ", "SPCD"]
    cond_cols = ["PLT_CN", "CONDID", "OWNCD", "RESERVCD"]

    plots = load_table("WA_PLOT.csv", plot_cols)
    trees = load_table("WA_TREE.csv", tree_cols)
    cond  = load_table("WA_COND.csv",  cond_cols)

    plots["CN"] = plots["CN"].astype(str).str.strip()
    trees["PLT_CN"] = trees["PLT_CN"].astype(str).str.strip()

    merged = trees.merge(plots, left_on="PLT_CN", right_on="CN", how="inner")
    print(f"\nAfter join: {len(merged):,} tree records")

    skamania = merged[merged["COUNTYCD"] == SKAMANIA_COUNTYCD].copy()
    print(f"Skamania County trees: {len(skamania):,}")

    live = skamania[skamania["STATUSCD"] == LIVE_STATUSCD].copy()
    print(f"Live trees: {len(live):,}")

    live["DIA"] = pd.to_numeric(live["DIA"], errors="coerce")
    live["VOLCFGRS"] = pd.to_numeric(live["VOLCFGRS"], errors="coerce").fillna(0.0)
    live["TPA_UNADJ"] = pd.to_numeric(live["TPA_UNADJ"], errors="coerce").fillna(0.0)
    live["vol_expanded"] = live["VOLCFGRS"] * live["TPA_UNADJ"]

    live["category"] = live["DIA"].apply(_assign_category)
    live = live.dropna(subset=["category"])
    print(f"Trees with valid DIA and category: {len(live):,}")

    # Aggregate per plot per category
    cat_agg = (
        live.groupby(["PLT_CN", "category"])
        .agg(
            vol_raw=("VOLCFGRS", "sum"),
            vol_expanded=("vol_expanded", "sum"),
            tree_count=("VOLCFGRS", "count"),
        )
        .reset_index()
    )

    # Pivot so each plot is one row with all categories as columns
    plot_coords = (
        live.groupby("PLT_CN")
        .agg(LAT=("LAT", "first"), LON=("LON", "first"))
        .reset_index()
    )

    # Build one flat record per plot
    plots_wide = plot_coords.copy()
    for cat, _, _ in SIZE_CATEGORIES:
        subset = cat_agg[cat_agg["category"] == cat][
            ["PLT_CN", "vol_raw", "vol_expanded", "tree_count"]
        ].rename(columns={
            "vol_raw":      f"{cat}_vol",
            "vol_expanded": f"{cat}_vol_expanded",
            "tree_count":   f"{cat}_count",
        })
        plots_wide = plots_wide.merge(subset, on="PLT_CN", how="left")

    # Fill missing categories with 0
    for cat, _, _ in SIZE_CATEGORIES:
        for col in [f"{cat}_vol", f"{cat}_vol_expanded", f"{cat}_count"]:
            plots_wide[col] = plots_wide[col].fillna(0.0)

    # Drop plots without coordinates
    plots_wide = plots_wide.dropna(subset=["LAT", "LON"])
    plots_wide = plots_wide[(plots_wide["LAT"] != 0) & (plots_wide["LON"] != 0)]

    # ── Ownership join from WA_COND ───────────────────────────────────────────
    cond["PLT_CN"] = cond["PLT_CN"].astype(str).str.strip()
    # Take the dominant (lowest CONDID) condition per plot
    dominant = (
        cond.sort_values("CONDID")
        .groupby("PLT_CN")
        .first()
        .reset_index()[["PLT_CN", "OWNCD", "RESERVCD"]]
    )
    dominant["own_label"] = dominant["OWNCD"].apply(
        lambda x: OWNCD_INFO.get(int(x), ("Unknown", "unknown"))[0] if pd.notna(x) else "Unknown"
    )
    dominant["fiscal_cat"] = dominant["OWNCD"].apply(
        lambda x: OWNCD_INFO.get(int(x), ("Unknown", "unknown"))[1] if pd.notna(x) else "unknown"
    )
    dominant["reserved"] = dominant["RESERVCD"].fillna(0).astype(int)

    plots_wide = plots_wide.merge(
        dominant[["PLT_CN", "own_label", "fiscal_cat", "reserved"]],
        on="PLT_CN", how="left"
    )
    plots_wide["own_label"]  = plots_wide["own_label"].fillna("Unknown")
    plots_wide["fiscal_cat"] = plots_wide["fiscal_cat"].fillna("unknown")
    plots_wide["reserved"]   = plots_wide["reserved"].fillna(0).astype(int)

    # Ownership summary
    print("\nOwnership breakdown (by plot):")
    for fc, grp in plots_wide.groupby("fiscal_cat"):
        print(f"  {fc:<12}  {len(grp):>4} plots  ({len(grp)/len(plots_wide)*100:.1f}%)")

    print(f"\nPlots with coordinate data: {len(plots_wide):,}")

    # Species breakdown per size category (before pivot, use the live tree frame)
    live["spcd_name"] = live["SPCD"].apply(
        lambda x: SPCD_NAMES.get(int(x), f"Other (SPCD {int(x)})") if pd.notna(x) else "Unknown"
    )
    live["clt_suit"] = live["SPCD"].apply(
        lambda x: CLT_SUITABILITY.get(int(x), "unknown") if pd.notna(x) else "unknown"
    )

    species_by_cat = {}
    for cat, _, _ in SIZE_CATEGORIES:
        cat_trees = live[live["category"] == cat]
        sp_agg = (
            cat_trees.groupby(["spcd_name", "clt_suit"])["vol_expanded"]
            .sum()
            .reset_index()
            .sort_values("vol_expanded", ascending=False)
        )
        total_vol = sp_agg["vol_expanded"].sum()
        sp_records = []
        for _, row in sp_agg.iterrows():
            sp_records.append({
                "species": row["spcd_name"],
                "clt_suitability": row["clt_suit"],
                "vol_expanded": round(float(row["vol_expanded"]), 1),
                "pct": round(float(row["vol_expanded"] / total_vol * 100), 1) if total_vol > 0 else 0.0,
            })
        species_by_cat[cat] = sp_records

    # Summary per category
    summary = {}
    for cat, lo, hi in SIZE_CATEGORIES:
        total_exp = plots_wide[f"{cat}_vol_expanded"].sum()
        total_raw = plots_wide[f"{cat}_vol"].sum()
        n_plots = (plots_wide[f"{cat}_vol_expanded"] > 0).sum()
        summary[cat] = {
            "vol_raw": round(total_raw, 1),
            "vol_expanded": round(total_exp, 1),
            "plots_with_volume": int(n_plots),
            "species": species_by_cat.get(cat, []),
        }
        print(f"  {cat:15s}  raw={total_raw:>10,.0f} ft³  expanded={total_exp:>12,.0f}  plots={n_plots}")

    records = plots_wide.to_dict(orient="records")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(
            {
                "metadata": {
                    "county": "Skamania",
                    "state": "Washington",
                    "countycd": SKAMANIA_COUNTYCD,
                    "statuscd_filter": LIVE_STATUSCD,
                    "source": "USDA Forest Service FIA Datamart — WA_CSV",
                    "invyr_min": int(live["INVYR"].min()),
                    "invyr_max": int(live["INVYR"].max()),
                    "n_plots_total": len(plots_wide),
                    "categories": summary,
                },
                "plots": records,
            },
            f,
            indent=2,
        )

    print(f"\nSaved → {OUTPUT_FILE}")
    print("Done.")


if __name__ == "__main__":
    main()
