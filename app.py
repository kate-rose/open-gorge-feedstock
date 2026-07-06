"""
app.py — Open Gorge: Skamania Feedstock Inventory Dashboard
Interactive 5-category, ownership-aware explorer for county commissioners and general public.
"""

import json
import math
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# pydeck powers the interactive slippy maps. It ships with a normal Streamlit install
# (local run, Streamlit Community Cloud) but is NOT bundled in the stlite/WebAssembly
# build used for the static GitHub Pages version — and it won't install cleanly there.
# So we import it optionally and fall back to a lightweight Altair point map when absent.
try:
    import pydeck as pdk
    HAS_PYDECK = True
except ModuleNotFoundError:
    HAS_PYDECK = False

DATA_FILE = Path(__file__).parent / "skamania_feedstock.json"

st.set_page_config(
    page_title="Open Gorge: Skamania Feedstock",
    page_icon="🌲",
    layout="wide",
)

@st.cache_data
def load_data():
    with open(DATA_FILE) as f:
        payload = json.load(f)
    return pd.DataFrame(payload["plots"]), payload["metadata"]

df, meta = load_data()

# ── Timber category definitions ───────────────────────────────────────────────
CATEGORIES = {
    "biomass": {
        "label":        "Biomass  (0 – 5\" diameter)",
        "short":        "Biomass",
        "desc": (
            "The smallest trees, tops, and slash — chipped into hog fuel, wood fiber, or biomass energy feedstock. "
            "Low unit value, but a useful byproduct of any active harvest. Often used to offset energy costs "
            "at mills or sold to biomass heating plants."
        ),
        "end_uses":     "Wood chips · Hog fuel · Biomass energy · Particle board · Pulp",
        "note":         "FIA does not record cubic foot volume for trees below merchantable size, so raw volume shows 0. "
                        "Actual biomass tonnage would require weight-based field measurements.",
        "prices": {
            "stumpage":    (0.02, 0.08,  "$/ft³ at the stump"),
            "mill_gate":   (0.25, 0.50,  "$/ft³ delivered to biomass facility"),
            "end_product": (0.40, 1.20,  "$/ft³ heat / power equivalent"),
        },
        "mass_timber":  False,
        "equiv_label":  "cords of firewood",
        "equiv_factor": 1 / 80,
    },
    "small_timber": {
        "label":        "Small Timber / Mass Timber Feedstock  (5 – 9\")",
        "short":        "Small Timber",
        "desc": (
            "Trees 5–9\" in diameter are the core feedstock for engineered mass timber: "
            "cross-laminated timber (CLT) and nail-laminated timber (NLT) panels used in "
            "commercial buildings and schools. These trees are too small for conventional "
            "sawmills but well-suited for modern engineered lumber processes. "
            "This is Skamania County's most strategically significant size class for mass timber development. "
            "\n\n*Note on fuel treatment framing:* Small-diameter thinning reduces ladder-fuel fire risk most "
            "effectively in dry mixed-conifer forests (east-side pine types). The Gifford Pinchot is predominantly "
            "a mesic Douglas-fir / western hemlock forest where fire science is more complex — thinning can "
            "reduce fire risk in some stand conditions but increase it in others by drying the understory. "
            "Fuel treatment benefits should be evaluated stand-by-stand with USFS silviculturists, not assumed county-wide."
        ),
        "end_uses":     "CLT panels · NLT panels · Glulam · Laminated veneer lumber · Structural wall panels",
        "note":         None,
        "prices": {
            "stumpage":    (0.50, 1.50,  "$/ft³ at the stump"),
            "mill_gate":   (2.00, 4.00,  "$/ft³ at the mass timber mill"),
            "end_product": (8.00, 12.00, "$/ft³ as finished CLT/NLT panel"),
        },
        "mass_timber":  True,
        "equiv_label":  "average homes framed",
        "equiv_factor": 1 / 1_000,
    },
    "sawlog": {
        "label":        "Sawlogs — Conventional Lumber  (9 – 15\")",
        "short":        "Sawlogs",
        "desc": (
            "The workhorse of conventional lumber. Trees 9–15\" in diameter are processed "
            "into dimensional lumber (2×4s, 2×6s, plywood) at traditional sawmills. "
            "Skamania County has substantial sawlog volume supporting regional mills "
            "in Longview, Camas, and Hood River."
        ),
        "end_uses":     "2×4 / 2×6 framing · Plywood · OSB · Decking · Siding",
        "note":         None,
        "prices": {
            "stumpage":    (1.00, 2.00, "$/ft³ at the stump"),
            "mill_gate":   (4.00, 6.00, "$/ft³ at the sawmill"),
            "end_product": (6.00, 9.00, "$/ft³ as finished dimensional lumber"),
        },
        "mass_timber":  True,
        "equiv_label":  "average homes framed",
        "equiv_factor": 1 / 1_000,
    },
    "premium": {
        "label":        "Premium Timber  (15 – 21\")",
        "short":        "Premium",
        "desc": (
            "Larger trees 15–21\" in diameter command premium prices for high-quality "
            "structural lumber, glulam beams, and appearance-grade products. "
            "These trees represent decades of forest growth and carry the highest "
            "per-unit stumpage value of any merchantable category."
        ),
        "end_uses":     "Glulam beams · Premium lumber · Flooring · Heavy timber · Exposed structural",
        "note":         None,
        "prices": {
            "stumpage":    (2.00, 4.00,  "$/ft³ at the stump"),
            "mill_gate":   (6.00, 9.00,  "$/ft³ at the mill"),
            "end_product": (10.0, 18.00, "$/ft³ as finished premium product"),
        },
        "mass_timber":  False,
        "equiv_label":  "average homes framed",
        "equiv_factor": 1 / 1_000,
    },
    "large_timber": {
        "label":        "Large Timber — Specialty  (21\"+)",
        "short":        "Large Timber",
        "desc": (
            "Old-growth and large second-growth trees over 21\" in diameter. "
            "Extremely high individual value for veneer, specialty products, and appearance lumber. "
            "**Important:** this size class includes late-successional and potentially old-growth trees "
            "that provide critical habitat for Northern Spotted Owl, Marbled Murrelet, and other "
            "ESA-listed species. Any harvest in this category faces significant ecological, regulatory, "
            "and community scrutiny far beyond what this dashboard can capture."
        ),
        "end_uses":     "Veneer · Specialty appearance lumber · Live-edge slabs · High-value exports",
        "note":         "Harvest decisions in the 21\"+ size class require ESA Section 7 consultation, "
                        "NEPA environmental review, and forest plan compatibility analysis. "
                        "This dashboard does not assess ecological suitability — only physical inventory.",
        "prices": {
            "stumpage":    (3.00, 6.00,  "$/ft³ at the stump"),
            "mill_gate":   (8.00, 12.00, "$/ft³ at the mill"),
            "end_product": (15.0, 30.00, "$/ft³ as finished specialty product"),
        },
        "mass_timber":  False,
        "equiv_label":  "average homes framed",
        "equiv_factor": 1 / 1_000,
    },
}

TIER_LABELS = {
    "stumpage":    "Stumpage",
    "mill_gate":   "Mill Gate",
    "end_product": "End Product",
}
TIER_HELP = {
    "stumpage":    "Value at the stump — what a landowner earns before harvest and transport costs.",
    "mill_gate":   "Delivered value at the processing facility after logging and hauling.",
    "end_product": "Finished lumber, panel, or product market value.",
}

# ── Fiscal / ownership definitions ────────────────────────────────────────────
FISCAL = {
    "all":     {
        "label": "All land",
        "desc":  None,
        "color": [150, 150, 150],
        "hex":   "#969696",
    },
    "federal": {
        "label": "Federal — Nat'l Forest (SRS/PILT)",
        "desc":  (
            "This land is managed by the US Forest Service (Gifford Pinchot National Forest). "
            "The county receives no property tax from it. Instead, Skamania depends on "
            "**Secure Rural Schools (SRS)** and **Payment in Lieu of Taxes (PILT)** — "
            "federal programs that Congress can reduce, delay, or let expire. "
            "When SRS lapses, school and road funding falls immediately."
        ),
        "color": [30, 100, 190],
        "hex":   "#1e64be",
    },
    "tribal":  {
        "label": "Tribal — trust land",
        "desc":  (
            "Trust land held by tribal nations (primarily Yakama Nation), managed under tribal sovereignty. "
            "Under federal law, trust land is not subject to state or local property tax — a consequence of "
            "treaty rights and federal trust responsibilities, not a policy choice by the county. "
            "Yakama Nation manages its forestlands under its own tribal forest plan, which may include "
            "timber harvest, cultural resource protection, and ecosystem management priorities. "
            "The county's fiscal relationship with tribal lands is governed by federal treaty law, "
            "not local ordinance."
        ),
        "color": [200, 120, 30],
        "hex":   "#c87818",
    },
    "taxable": {
        "label": "On the local tax rolls",
        "desc":  (
            "Corporate timber (Weyerhaeuser et al.) and private land. "
            "This is the only category that generates direct county property tax revenue. "
            "However, Washington's **Designated Forest Land** program (RCW 84.33) allows "
            "corporate timberland to be assessed at current-use value — typically well below "
            "market — significantly limiting what the county actually collects."
        ),
        "color": [30, 160, 80],
        "hex":   "#1ea050",
    },
    "state":   {
        "label": "State / DNR Trust",
        "desc":  (
            "Washington Department of Natural Resources trust lands. Revenue from timber "
            "sales flows to state trust beneficiaries (Common School Fund, etc.), "
            "not directly to Skamania County's general fund."
        ),
        "color": [110, 40, 160],
        "hex":   "#6e28a0",
    },
}

FISCAL_COLOR_MAP = {k: v["color"] for k, v in FISCAL.items()}

# ── SRS / 25% Fund historical payment data ────────────────────────────────────
# Sources: USDA Forest Service ASR-10-03 Final Payment Detail Reports
# FY2010–2012: extracted from USFS PDFs (per-district rows summed for Skamania County)
# FY2013–2025: scraped from USFS ASR HTML / PDF archives
SRS_PAYMENTS = [
    {"fy": 2010, "amount": 1_335_332.54, "type": "25% Fund",
     "note": "25% rolling avg; SRS not fully disbursed this year"},
    {"fy": 2011, "amount":   830_835.01, "type": "25% Fund",
     "note": "Declining 7-yr avg of NF receipts; SRS reauth. pending"},
    {"fy": 2012, "amount": 1_178_516.64, "type": "25% Fund",
     "note": "P.L. 112-141 signed July 2012; SRS payments flow from FY2013"},
    {"fy": 2013, "amount": 3_490_667.74, "type": "SRS Formula",
     "note": "First full year under P.L. 112-141"},
    {"fy": 2014, "amount": 3_246_179.74, "type": "SRS Formula", "note": ""},
    {"fy": 2015, "amount": 3_477_890.03, "type": "SRS Formula", "note": ""},
    {"fy": 2016, "amount": 2_488_554.95, "type": "SRS Formula", "note": ""},
    {"fy": 2017, "amount": 3_182_629.73, "type": "SRS Formula",
     "note": "P.L. 115-141 reauthorization (FY2017–2023)"},
    {"fy": 2018, "amount": 0,            "type": "No data",
     "note": "ASR 10-03 report not found in USFS archives"},
    {"fy": 2019, "amount": 2_640_744.54, "type": "SRS Formula", "note": ""},
    {"fy": 2020, "amount": 2_542_601.53, "type": "SRS Formula", "note": ""},
    {"fy": 2021, "amount": 3_109_049.77, "type": "SRS Formula", "note": ""},
    {"fy": 2022, "amount": 2_593_667.44, "type": "SRS Formula", "note": ""},
    {"fy": 2023, "amount": 2_399_155.31, "type": "SRS Formula", "note": ""},
    {"fy": 2024, "amount":   448_081.62, "type": "25% Fund",
     "note": "SRS lapsed — county fell back to 25% rolling average"},
    {"fy": 2025, "amount": 2_467_842.84, "type": "SRS Formula",
     "note": "P.L. 118-42 reauthorization (FY2024–2026)"},
]
_SRS_TYPE_COLORS = {
    "SRS Formula": "#1e64be",   # federal blue
    "25% Fund":    "#e88020",   # amber
    "No data":     "#cccccc",   # light gray
}

# ── Gifford Pinchot timber program figures (BOCC meeting record) ──────────────
# Shared by Forest Service staff at the June 30, 2026 Skamania BOCC meeting.
# Meeting-record figures — pending written confirmation from the GP.
GP_PROGRAM_MBF = {
    "Recent years (avg)":  32_000,   # MBF/yr, GP-wide, all contract vehicles
    "2026 planned":        36_000,
    "2030 stated target":  68_000,
}
GP_THINNING_ACRES_YR = 3_600         # forest-wide thinning program, stated 20–30 yr horizon

TOWNS = pd.DataFrame([
    {"name": "Stevenson",     "lat": 45.6951, "lon": -121.8862},
    {"name": "White Salmon",  "lat": 45.7201, "lon": -121.4898},
    {"name": "N. Bonneville", "lat": 45.6437, "lon": -121.9609},
    {"name": "Carson",        "lat": 45.7251, "lon": -121.9156},
    {"name": "Underwood",     "lat": 45.7279, "lon": -121.5457},
    {"name": "Trout Lake",    "lat": 46.0013, "lon": -121.5354},
    {"name": "Husum",         "lat": 45.7893, "lon": -121.4821},
    {"name": "Skamania",      "lat": 45.6290, "lon": -122.0382},
])

# ── Section navigation + session state defaults ───────────────────────────────
SECTIONS = [
    "🏔️ Overview",
    "🗺️ Where the Timber Is",
    "💰 County Revenue & Timber Payments",
    "🌊 State Logging Rules",
    "❓ Questions & Sources",
]

_SS_DEFAULTS = {
    "nav_radio":    "🏔️ Overview",
    "cat_radio":    "small_timber",
    "tier_radio":   "mill_gate",
    "fiscal_radio": "all",
    "reserved_cb":  False,
}
for _k, _v in _SS_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Open Gorge")
    st.caption("Skamania Feedstock Inventory")
    st.divider()

    # Persisted section nav — holds its place when a filter below triggers a rerun.
    section = st.radio("Go to", options=SECTIONS, key="nav_radio")

    # The timber/ownership filters only affect the map, so they only show there.
    if section == "🗺️ Where the Timber Is":
        st.divider()
        if st.button(
            "🔥 Fuel Treatment View",
            width="stretch",
            help="Jumps to small-diameter timber (5–9\") on non-wilderness Gifford Pinchot "
                 "land — the fuel-thinning size class.",
        ):
            st.session_state.cat_radio    = "small_timber"
            st.session_state.fiscal_radio = "federal"
            st.session_state.reserved_cb  = True
            st.rerun()

        st.divider()
        st.radio(
            "**Timber size class**",
            options=list(CATEGORIES.keys()),
            format_func=lambda k: CATEGORIES[k]["short"],
            captions=[
                "Chips, hog fuel, biomass energy",
                "CLT / NLT mass timber feedstock",
                "Dimensional lumber — 2×4, 2×6…",
                "Glulam beams, premium appearance",
                "Veneer, specialty & export products",
            ],
            key="cat_radio",
        )
        st.radio(
            "**Value estimate**",
            options=list(TIER_LABELS.keys()),
            format_func=lambda k: TIER_LABELS[k],
            captions=[
                "Value at the stump",
                "Delivered to the mill",
                "Finished product",
            ],
            key="tier_radio",
            help="Pacific Northwest benchmark prices — not a formal appraisal.",
        )
        st.radio(
            "**Land ownership**",
            options=list(FISCAL.keys()),
            format_func=lambda k: FISCAL[k]["label"],
            captions=[
                "All plots, colored by owner",
                "Gifford Pinchot NF — SRS / PILT",
                "Yakama Nation — trust land",
                "Corporate & private — taxable",
                "DNR trust — state school funds",
            ],
            key="fiscal_radio",
        )
        st.checkbox(
            "Exclude wilderness & reserved areas",
            key="reserved_cb",
            help="Removes plots in designated wilderness and other reserved areas "
                 "where harvest is prohibited.",
        )

    # Read the current filter selections (valid on every page via session_state).
    cat_key       = st.session_state.cat_radio
    cat           = CATEGORIES[cat_key]
    vol_col       = f"{cat_key}_vol_expanded"
    raw_col       = f"{cat_key}_vol"
    cnt_col       = f"{cat_key}_count"
    price_tier    = st.session_state.tier_radio
    fiscal_filter = st.session_state.fiscal_radio
    exclude_reserved = st.session_state.reserved_cb

    # Map-page summary metrics
    if section == "🗺️ Where the Timber Is":
        st.divider()
        fdf = df.copy()
        if fiscal_filter != "all":
            fdf = fdf[fdf["fiscal_cat"] == fiscal_filter]
        if exclude_reserved:
            fdf = fdf[fdf["reserved"] == 0]

        vol_expanded = fdf[vol_col].sum()
        n_plots = int((fdf[vol_col] > 0).sum())
        lo, hi, tier_unit = cat["prices"][price_tier]

        st.metric(
            "Timber volume (this selection)",
            f"{vol_expanded:,.0f} ft³",
            help="Trees-per-acre-expanded cubic feet for the size class and ownership selected above.",
        )
        st.metric(
            f"Estimated value — {TIER_LABELS[price_tier]}",
            f"${vol_expanded * lo / 1e6:,.1f}M – ${vol_expanded * hi / 1e6:,.1f}M",
            help=f"{tier_unit}. Benchmark: ${lo}–${hi}/ft³. Illustrative, not an appraisal.",
        )
        st.metric("Plots shown", f"{n_plots:,} of {len(df):,}")

    st.divider()
    st.caption(
        "Data: USDA Forest Service FIA Datamart.  \n"
        "Analysis: Open Gorge / SkamaniaDispatch."
    )

# ── Build map dataframe ───────────────────────────────────────────────────────
map_df = df.copy()
if fiscal_filter != "all":
    map_df = map_df[map_df["fiscal_cat"] == fiscal_filter]
if exclude_reserved:
    map_df = map_df[map_df["reserved"] == 0]

max_vol = map_df[vol_col].max() if len(map_df) > 0 and map_df[vol_col].max() > 0 else 1.0
map_df["_radius"] = (map_df[vol_col] / max_vol * 1_200).clip(lower=40)

if fiscal_filter == "all":
    map_df["_color"] = map_df["fiscal_cat"].apply(
        lambda fc: FISCAL_COLOR_MAP.get(fc, [150, 150, 150]) + [200]
    )
else:
    r, g, b = FISCAL[fiscal_filter]["color"]
    map_df["_alpha"] = (map_df[vol_col] / max_vol * 210).clip(lower=40).astype(int)
    map_df["_color"] = [[r, g, b, int(a)] for a in map_df["_alpha"]]

# ── Ownership breakdown chart data ────────────────────────────────────────────
chart_rows = []
for fk, fdef in FISCAL.items():
    if fk == "all":
        continue
    sub = df[df["fiscal_cat"] == fk]
    if exclude_reserved:
        sub = sub[sub["reserved"] == 0]
    v = sub[vol_col].sum()
    chart_rows.append({
        "category": fdef["label"],
        "fiscal_cat": fk,
        "volume": v,
        "color": fdef["hex"],
    })
chart_data = pd.DataFrame(chart_rows).sort_values("volume", ascending=True)

# Federal-only subset used by the scenario tab (respects the reserved checkbox)
federal_df = df[df["fiscal_cat"] == "federal"]
if exclude_reserved:
    federal_df = federal_df[federal_df["reserved"] == 0]

def _altair_fallback_map(
    pts: pd.DataFrame,
    *,
    color: alt.Color,
    size_field: str,
    tooltip: list,
    height: int = 560,
    towns: pd.DataFrame | None = None,
    markers: pd.DataFrame | None = None,
    marker_color: str = "#dc1e1e",
) -> alt.LayerChart:
    """Lightweight lon/lat scatter used when pydeck is unavailable (stlite web build).

    Not a slippy basemap — but it preserves the spatial distribution, ownership/distance
    coloring, and volume sizing that carry the analytical point. Works purely client-side
    in stlite with no extra packages.

    Geography is drawn to true scale: the chart width is derived from the height so that
    one ground-mile east equals one ground-mile north, applying the cos(latitude)
    correction (a degree of longitude is only ~0.70x a degree of latitude at ~46°N).
    """
    # Standardize every layer onto LON/LAT columns so they share one scale + domain.
    town_pts = marker_pts = None
    all_lon, all_lat = list(pts["LON"]), list(pts["LAT"])
    if towns is not None:
        town_pts = towns.rename(columns={"lon": "LON", "lat": "LAT"})
        all_lon += list(town_pts["LON"]); all_lat += list(town_pts["LAT"])
    if markers is not None:
        marker_pts = markers.rename(columns={"lon": "LON", "lat": "LAT"})
        all_lon += list(marker_pts["LON"]); all_lat += list(marker_pts["LAT"])

    lon_min, lon_max = min(all_lon), max(all_lon)
    lat_min, lat_max = min(all_lat), max(all_lat)
    lon_pad = (lon_max - lon_min) * 0.05 or 0.02
    lat_pad = (lat_max - lat_min) * 0.05 or 0.02
    lon_min -= lon_pad; lon_max += lon_pad
    lat_min -= lat_pad; lat_max += lat_pad

    dlon, dlat = lon_max - lon_min, lat_max - lat_min
    phi = math.radians((lat_min + lat_max) / 2)
    width = int(max(240, min(1000, height * (dlon / dlat) * math.cos(phi))))

    x = alt.X("LON:Q", title=None, axis=alt.Axis(format=".2f", grid=True),
              scale=alt.Scale(domain=[lon_min, lon_max], nice=False, zero=False))
    y = alt.Y("LAT:Q", title=None, axis=alt.Axis(format=".2f", grid=True),
              scale=alt.Scale(domain=[lat_min, lat_max], nice=False, zero=False))

    layers = [
        alt.Chart(pts)
        .mark_circle(opacity=0.65, stroke="#ffffff", strokeWidth=0.3)
        .encode(
            x=x, y=y,
            size=alt.Size(f"{size_field}:Q", legend=None, scale=alt.Scale(range=[8, 320])),
            color=color,
            tooltip=tooltip,
        )
    ]
    if town_pts is not None:
        layers.append(
            alt.Chart(town_pts).mark_point(
                shape="triangle", size=60, filled=True, color="#333333"
            ).encode(x=x, y=y, tooltip=alt.Tooltip("name:N", title="Town"))
        )
        layers.append(
            alt.Chart(town_pts).mark_text(
                dy=-9, fontSize=9, color="#333333"
            ).encode(x=x, y=y, text="name:N")
        )
    if marker_pts is not None:
        layers.append(
            alt.Chart(marker_pts).mark_point(
                shape="diamond", size=200, filled=True, color=marker_color,
                stroke="#7a0000", strokeWidth=1.5,
            ).encode(x=x, y=y, tooltip=alt.Tooltip("name:N", title="Location"))
        )
    return alt.layer(*layers).properties(width=width, height=height)

# ── Sections (rendered based on the persisted sidebar nav) ────────────────────

# ════════════════════════════════════════════════════════════════════════════
if section == "🏔️ Overview":
    st.markdown("## The Balancing Act, in One Screen")
    st.markdown(
        "Skamania County is caught between two governments at once. The **federal** government "
        "owns most of the county's forest and pays the county in place of property tax — but "
        "those payments keep lapsing. The **state** is tightening logging rules on the private "
        "land that *does* pay tax. And the county's schools are the ones feeling it. "
        "No single fix solves this; the point of this tool is to show the real numbers behind "
        "each piece so the tradeoffs can be discussed plainly."
    )
    st.caption(
        "Built for commissioners, district staff, and residents following the county ↔ Forest "
        "Service conversation. Every figure traces to a source; numbers from the June 2026 "
        "meeting record are marked *pending written confirmation*."
    )

    # Shared computations (defaults: $300/MBF blended stumpage, 50% Skamania share of GP receipts)
    _BR_PRICE  = 300.0    # $/MBF blended stumpage — benchmark, adjustable in Scenario tab
    _BR_SHARE  = 0.50     # Skamania share of GP 25% Fund distribution — adjustable in Scenario tab
    _br_formula_amts = [r["amount"] for r in SRS_PAYMENTS if r["type"] == "SRS Formula"]
    _br_srs_avg  = sum(_br_formula_amts) / len(_br_formula_amts)
    _br_fy23     = next(r["amount"] for r in SRS_PAYMENTS if r["fy"] == 2023)
    _br_fy24     = next(r["amount"] for r in SRS_PAYMENTS if r["fy"] == 2024)
    _br_fy25     = next(r["amount"] for r in SRS_PAYMENTS if r["fy"] == 2025)
    _br_drop_pct = (1 - _br_fy24 / _br_fy23) * 100

    def _br_county_rev(mbf_gp: float, trad_share: float) -> float:
        """County 25% Fund revenue at a given GP program level and traditional-sale share."""
        return mbf_gp * trad_share * _BR_PRICE * 0.25 * _BR_SHARE

    _br_2030_75 = _br_county_rev(GP_PROGRAM_MBF["2030 stated target"], 0.75)
    _br_2026_100 = _br_county_rev(GP_PROGRAM_MBF["2026 planned"], 1.00)

    # ── The balancing act, as one picture ────────────────────────────────────
    _fed_stat1 = f"${_br_srs_avg/1e6:.1f}M/yr average, but"
    _fed_stat2 = f"${_br_fy24/1e6:.2f}M in the FY2024 lapse (−{_br_drop_pct:.0f}%)"
    _bal_svg = f"""
<svg viewBox="0 0 760 392" width="100%" height="392" preserveAspectRatio="xMidYMid meet"
     xmlns="http://www.w3.org/2000/svg"
     font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">
  <!-- Pressure 1: Federal -->
  <rect x="12" y="8" width="230" height="92" rx="8" fill="#eaf1fb" stroke="#1e64be" stroke-width="1.5"/>
  <text x="127" y="30" text-anchor="middle" font-size="14" font-weight="700" fill="#1e3a5f">FEDERAL PAYMENTS</text>
  <text x="127" y="48" text-anchor="middle" font-size="11.5" fill="#41556a">shrinking &amp; unreliable</text>
  <text x="127" y="70" text-anchor="middle" font-size="11.5" font-weight="600" fill="#1e3a5f">{_fed_stat1}</text>
  <text x="127" y="86" text-anchor="middle" font-size="11.5" font-weight="600" fill="#1e3a5f">{_fed_stat2}</text>
  <!-- Pressure 2: State -->
  <rect x="265" y="8" width="230" height="92" rx="8" fill="#fdecec" stroke="#c0392b" stroke-width="1.5"/>
  <text x="380" y="30" text-anchor="middle" font-size="14" font-weight="700" fill="#7a241a">STATE LOGGING RULES</text>
  <text x="380" y="48" text-anchor="middle" font-size="11.5" fill="#8a4038">raising cost on taxable land</text>
  <text x="380" y="70" text-anchor="middle" font-size="11.5" font-weight="600" fill="#7a241a">new stream buffers,</text>
  <text x="380" y="86" text-anchor="middle" font-size="11.5" font-weight="600" fill="#7a241a">start Aug 2026</text>
  <!-- Pressure 3: Schools -->
  <rect x="518" y="8" width="230" height="92" rx="8" fill="#fdf3e3" stroke="#d98c1f" stroke-width="1.5"/>
  <text x="633" y="30" text-anchor="middle" font-size="14" font-weight="700" fill="#7a5510">LOCAL SCHOOLS</text>
  <text x="633" y="48" text-anchor="middle" font-size="11.5" fill="#8a6a2f">already cutting</text>
  <text x="633" y="70" text-anchor="middle" font-size="11.5" font-weight="600" fill="#7a5510">2 schools closed ·</text>
  <text x="633" y="86" text-anchor="middle" font-size="11.5" font-weight="600" fill="#7a5510">~$250K SRS shortfall</text>
  <!-- Arrows down to the squeeze -->
  <line x1="127" y1="100" x2="127" y2="144" stroke="#8a97a5" stroke-width="2"/>
  <polygon points="121,144 133,144 127,151" fill="#8a97a5"/>
  <line x1="380" y1="100" x2="380" y2="144" stroke="#8a97a5" stroke-width="2"/>
  <polygon points="374,144 386,144 380,151" fill="#8a97a5"/>
  <line x1="633" y1="100" x2="633" y2="144" stroke="#8a97a5" stroke-width="2"/>
  <polygon points="627,144 639,144 633,151" fill="#8a97a5"/>
  <!-- The squeeze -->
  <rect x="110" y="152" width="540" height="74" rx="8" fill="#eef1f4" stroke="#5b6b7d" stroke-width="1.5"/>
  <text x="380" y="184" text-anchor="middle" font-size="16" font-weight="700" fill="#2b3a4a">SKAMANIA COUNTY BUDGET</text>
  <text x="380" y="208" text-anchor="middle" font-size="12" fill="#41556a">~91% of the county is federal forest — little property tax to fall back on</text>
  <!-- Arrow to the lever -->
  <line x1="380" y1="226" x2="380" y2="264" stroke="#8a97a5" stroke-width="2"/>
  <polygon points="374,264 386,264 380,271" fill="#8a97a5"/>
  <!-- The lever -->
  <rect x="70" y="272" width="620" height="112" rx="8" fill="#e9f6ee" stroke="#2f8f5b" stroke-width="1.5"/>
  <text x="380" y="298" text-anchor="middle" font-size="14" font-weight="700" fill="#1c5c39">THE ONE LOCAL LEVER — how federal timber gets sold</text>
  <text x="380" y="322" text-anchor="middle" font-size="12" fill="#265f3e">Traditional timber sales send money to county schools. Stewardship &amp; Good</text>
  <text x="380" y="340" text-anchor="middle" font-size="12" fill="#265f3e">Neighbor deals — whatever their forest-health value — mostly don't.</text>
  <text x="380" y="366" text-anchor="middle" font-size="12" font-weight="600" fill="#1c5c39">Even the 2030 timber target falls short of past payments, so a timber push</text>
  <text x="380" y="382" text-anchor="middle" font-size="12" font-weight="600" fill="#1c5c39">and federal payment reform are both needed — not one or the other.</text>
</svg>
"""
    components.html(
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif">{_bal_svg}</div>',
        height=410,
    )
    st.caption("The three pressures converging on the county budget — each quantified in the sections below.")
    st.divider()

    _k1, _k2, _k3, _k4, _k5 = st.columns(5)
    _k1.metric(
        "SRS payment, avg formula year",
        f"${_br_srs_avg/1e6:.2f}M/yr",
        help="Average of the 11 SRS Formula years FY2013–FY2025. "
             "Source: USFS ASR-10-03 Final Payment Detail Reports.",
    )
    _k2.metric(
        "FY2024 lapse payment",
        f"${_br_fy24/1e6:.2f}M",
        delta=f"-{_br_drop_pct:.0f}% vs FY2023",
        help="When SRS lapsed, the county fell back to the 25% Fund rolling average. "
             "Source: USFS ASR-10-03.",
    )
    _k3.metric(
        "GP timber program, 2026",
        "36M BF",
        help="Forest Service figure shared at the June 30, 2026 BOCC meeting "
             "(recent years ~32M BF). Meeting record — pending written confirmation.",
    )
    _k4.metric(
        "GP stated target, 2030",
        "68M BF",
        help="Forest Service 2030 target shared at the June 30, 2026 BOCC meeting, "
             "alongside a ~3,600 acre/yr forest-wide thinning program over 20–30 years. "
             "Meeting record — pending written confirmation.",
    )
    _k5.metric(
        "County revenue if 2030 target is 75% traditional",
        f"≈${_br_2030_75/1e6:.1f}M/yr",
        help=f"68M BF × 75% traditional sales × ${_BR_PRICE:.0f}/MBF blended stumpage × "
             f"25% Fund × {_BR_SHARE:.0%} Skamania share. Steady-state estimate — the 25% Fund "
             "pays a 7-year rolling average, so revenue phases in over several years.",
    )

    st.divider()
    st.markdown("#### Three things to know")

    _f1, _f2, _f3 = st.columns(3)
    with _f1:
        _s_2026_100 = f"${_br_2026_100/1e6:.2f}M"
        st.markdown(
            f"""
**1. The mix is the money.**

The contract vehicle — not the harvest volume — determines whether schools see a dollar.
Traditional sales flow to the 25% Fund; stewardship and Good Neighbor Authority sales
mostly don't. Even if 2026's full 36M BF program were **100% traditional sales**, the county
would receive roughly **{_s_2026_100}/yr** at benchmark stumpage. At a stewardship-heavy mix,
far less. The commissioners' "floor of 50%" demand is a revenue argument, and the
arithmetic backs the instinct behind it.
            """
        )
    with _f2:
        _s_2030_75 = f"${_br_2030_75/1e6:.1f}M"
        _s_avg     = f"${_br_srs_avg/1e6:.2f}M"
        st.markdown(
            f"""
**2. Even the 2030 target falls short of SRS.**

At the stated 68M BF target with a **75% traditional mix** — the commissioners' aspiration —
county revenue reaches roughly **{_s_2030_75}/yr**, against an SRS-formula average of
**{_s_avg}/yr**. The timber push and the SRS/PILT recombination strategy
(the Merkley conversation) are **complements, not alternatives**: even a successful
harvest program needs structural payment reform to close the gap.
            """
        )
    with _f3:
        st.markdown(
            """
**3. Pressure is converging from both governments.**

Federal payment uncertainty (the FY2024 lapse), the state's Type Np buffer rule
(effective August 2026, costs on private timberland), and a reported ~$250K
SRS distribution error at Stevenson-Carson *(pending written confirmation)* are
landing on the same county in the same budget cycles — while the district has
now closed its second school. No single agency's process accounts for the
cumulative picture. This dashboard tries to.
            """
        )

    st.divider()
    st.markdown("#### Numbers to carry into the room")

    _mbf_replace_fy25 = _br_fy25 / (0.25 * _BR_SHARE * _BR_PRICE)
    _mbf_replace_avg  = _br_srs_avg / (0.25 * _BR_SHARE * _BR_PRICE)
    _room_df = pd.DataFrame([
        {"The number": f"${_br_srs_avg/1e6:.2f}M/yr",
         "What it is": "Average Skamania SRS payment in a formula year (FY2013–FY2025)",
         "Source": "USFS ASR-10-03 reports"},
        {"The number": f"-{_br_drop_pct:.0f}%",
         "What it is": "One-year county revenue drop when SRS lapsed (FY2023 → FY2024)",
         "Source": "USFS ASR-10-03 reports"},
        {"The number": f"~{_mbf_replace_fy25/1000:.0f}M BF/yr",
         "What it is": "GP-wide traditional-sale volume needed to replace the FY2025 SRS payment "
                       "(100% traditional mix, benchmark stumpage)",
         "Source": "This dashboard — assumptions in Scenario tab"},
        {"The number": f"~{_mbf_replace_avg/1000:.0f}M BF/yr",
         "What it is": "GP-wide traditional-sale volume needed to match the SRS-formula average",
         "Source": "This dashboard — assumptions in Scenario tab"},
        {"The number": "68M BF by 2030",
         "What it is": "The Forest Service's own stated program target (vs. 36M BF planned for 2026)",
         "Source": "June 30, 2026 BOCC meeting — pending written confirmation"},
    ])
    st.table(_room_df)
    st.caption(
        "Revenue math assumes $300/MBF blended stumpage and a 50% Skamania share of Gifford "
        "Pinchot receipts — both adjustable under **County Revenue & Timber Payments**. These "
        "are order-of-magnitude anchors for a conversation, not budget forecasts."
    )

    st.divider()
    st.markdown("#### Where to go deeper")
    st.markdown(
        """
- **💰 County Revenue & Timber Payments** — the payment history, the school-funding stakes,
  and the traditional-sale-vs-stewardship question that decides whether logging reaches schools.
- **🗺️ Where the Timber Is** — the county's timber by size and owner, and why ~91% of it
  generates no property tax.
- **🌊 State Logging Rules** — the new state stream-buffer rule (effect August 2026) and its
  cost to the private land that *is* on the tax rolls.
- **❓ Questions & Sources** — plain answers, including why stewardship contracts don't pay
  schools, and where every number comes from.
        """
    )

# ════════════════════════════════════════════════════════════════════════════
if section == "🗺️ Where the Timber Is":
    st.markdown("## Where the Timber Is — and Who Owns It")
    st.markdown(
        "This map shows the county's timber, broken out by tree size and by who owns the land. "
        "The ownership split is the whole fiscal problem in one picture: the vast majority sits "
        "on federal land that pays no property tax. Use the controls on the left to change the "
        "tree size class, price basis, and owner."
    )
    st.divider()
    st.markdown(f"### {cat['label']}")
    st.markdown(cat["desc"])
    st.markdown(f"**End uses:** {cat['end_uses']}")
    if cat["note"]:
        st.info(cat["note"])

    # Fiscal context callout when a specific ownership is selected
    if fiscal_filter != "all" and FISCAL[fiscal_filter]["desc"]:
        st.warning(FISCAL[fiscal_filter]["desc"])

    # Fuel treatment mode banner
    if cat_key == "small_timber" and fiscal_filter == "federal" and exclude_reserved:
        st.success(
            "**🔥 Fuel Treatment View** — showing small-diameter timber (5–9\") on "
            "non-wilderness Gifford Pinchot NF land. These stands overlap with the ladder-fuel "
            "targets of USFS's 10-Year Wildfire Crisis Strategy. Thinning them can produce "
            "mass timber feedstock and generate 25% Fund receipts for the county — "
            "the same work, two different framings."
        )
        st.caption(
            "⚠️ **Science note:** Ladder-fuel thinning is best-established in dry ponderosa pine forests "
            "(eastern Cascades). The Gifford Pinchot's wet west-side Douglas-fir / hemlock forests have "
            "more complex fire dynamics — thinning benefits depend heavily on stand structure, slope, and "
            "aspect. Stand-level analysis with USFS silviculturists is needed before assuming county-wide "
            "fuel reduction benefits."
        )

    # Value tier comparison
    st.markdown("#### Estimated Value by Tier")
    c1, c2, c3 = st.columns(3)
    for col_ui, tk in zip([c1, c2, c3], ["stumpage", "mill_gate", "end_product"]):
        lo_t, hi_t, _ = cat["prices"][tk]
        v_lo = vol_expanded * lo_t / 1e6
        v_hi = vol_expanded * hi_t / 1e6
        label = ("▶ " if tk == price_tier else "") + TIER_LABELS[tk]
        col_ui.metric(label, f"${v_lo:,.1f}M – ${v_hi:,.1f}M", help=TIER_HELP[tk])

    # Ownership breakdown chart
    st.divider()
    st.markdown("#### Ownership Breakdown — Volume by Fiscal Category")

    total_all = chart_data["volume"].sum()
    if total_all > 0:
        chart_data["share"] = (chart_data["volume"] / total_all * 100).round(1)
        chart_data["label"] = chart_data.apply(
            lambda r: f"{r['share']:.1f}%  ({r['volume']:,.0f} ft³)", axis=1
        )

        bar = (
            alt.Chart(chart_data)
            .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
            .encode(
                x=alt.X("volume:Q", title="TPA-Expanded Volume (ft³)",
                        axis=alt.Axis(format="~s")),
                y=alt.Y("category:N", sort="-x", title=None,
                        axis=alt.Axis(labelLimit=320)),
                color=alt.Color(
                    "fiscal_cat:N",
                    scale=alt.Scale(
                        domain=[k for k in FISCAL if k != "all"],
                        range=[FISCAL[k]["hex"] for k in FISCAL if k != "all"],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("category:N", title="Ownership"),
                    alt.Tooltip("volume:Q",   title="Volume (ft³)", format=",.0f"),
                    alt.Tooltip("share:Q",    title="Share (%)",    format=".1f"),
                ],
            )
            .properties(height=160)
        )

        # Large bars (>20% share): label centered inside the bar in white
        # Small bars: label left-aligned just outside the bar end in dark text
        _inside  = chart_data[chart_data["share"] > 20].copy()
        _outside = chart_data[chart_data["share"] <= 20].copy()
        _inside["mid_vol"] = _inside["volume"] / 2   # center of the bar

        text_in  = alt.Chart(_inside).mark_text(
            align="center", baseline="middle", fontSize=12, color="white"
        ).encode(
            x=alt.X("mid_vol:Q"),
            y=alt.Y("category:N", sort="-x"),
            text="label:N",
        )
        text_out = alt.Chart(_outside).mark_text(
            align="left", dx=4, fontSize=12, color="#333333"
        ).encode(
            x=alt.X("volume:Q"),
            y=alt.Y("category:N", sort="-x"),
            text="label:N",
        )

        st.altair_chart(bar + text_in + text_out, width="stretch")

        # Fiscal dependency callout
        federal_vol = chart_data.loc[chart_data["fiscal_cat"] == "federal", "volume"].sum()
        taxable_vol = chart_data.loc[chart_data["fiscal_cat"] == "taxable", "volume"].sum()
        fed_pct = federal_vol / total_all * 100 if total_all > 0 else 0
        tax_pct = taxable_vol / total_all * 100 if total_all > 0 else 0
        st.caption(
            f"**{fed_pct:.0f}% of {cat['short'].lower()} volume is on federal land** — "
            f"managed by the US Forest Service, generating SRS/PILT payments instead of property tax. "
            f"Only **{tax_pct:.0f}%** is on locally taxable land."
        )
    else:
        st.info("No volume recorded for this category under the current filters.")

    # Map
    st.divider()
    if fiscal_filter == "all":
        map_note = "Dots are colored by land ownership / fiscal category. Size reflects timber volume."
    else:
        map_note = (
            f"Showing only **{FISCAL[fiscal_filter]['label']}** plots. "
            "Dot size and brightness reflect expanded volume for the selected timber category."
        )
    st.markdown(f"**Map — FIA Sample Plots:** {map_note} White markers are towns.")

    if HAS_PYDECK:
        fia_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["LON", "LAT"],
            get_radius="_radius",
            get_fill_color="_color",
            pickable=True,
            auto_highlight=True,
        )
        town_dot_layer = pdk.Layer(
            "ScatterplotLayer",
            data=TOWNS,
            get_position=["lon", "lat"],
            get_radius=400,
            get_fill_color=[255, 255, 255, 220],
            get_line_color=[80, 80, 80, 255],
            stroked=True,
            line_width_min_pixels=1,
            pickable=False,
        )
        town_label_layer = pdk.Layer(
            "TextLayer",
            data=TOWNS,
            get_position=["lon", "lat"],
            get_text="name",
            get_size=13,
            get_color=[30, 30, 30, 255],
            get_background_color=[255, 255, 255, 200],
            background=True,
            get_padding=[3, 2, 3, 2],
            get_alignment_baseline="'bottom'",
            get_text_anchor="'middle'",
            get_pixel_offset=[0, -10],
            billboard=True,
            pickable=False,
        )

        center_lat = df["LAT"].mean() if len(df) > 0 else 45.87
        center_lon = df["LON"].mean() if len(df) > 0 else -121.9
        view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=9, pitch=0)

        tooltip = {
            "html": (
                f"<b>FIA Plot</b><br/>"
                f"<b>Ownership:</b> {{own_label}}<br/>"
                f"<b>Fiscal:</b> {{fiscal_cat}}<br/>"
                f"<b>Wilderness:</b> {{reserved}}<br/>"
                f"<b>{cat['short']} vol (expanded):</b> {{{vol_col}:.1f}} ft³<br/>"
                f"<b>Raw plot vol:</b> {{{raw_col}:.1f}} ft³<br/>"
                f"<b>Trees sampled:</b> {{{cnt_col}}}<br/>"
                f"<b>Coords:</b> {{LAT:.4f}}, {{LON:.4f}}"
            ),
            "style": {
                "backgroundColor": "#1e3a2f",
                "color": "#d4edda",
                "fontSize": "13px",
                "padding": "8px 10px",
                "borderRadius": "4px",
                "border": "1px solid #52b788",
            },
        }

        deck = pdk.Deck(
            layers=[fia_layer, town_dot_layer, town_label_layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        )
        st.pydeck_chart(deck, width="stretch")
    else:
        # stlite / web build: pydeck unavailable — Altair lon/lat scatter fallback.
        _fb = map_df.copy()
        _fb_color = alt.Color(
            "fiscal_cat:N",
            scale=alt.Scale(
                domain=[k for k in FISCAL if k != "all"],
                range=[FISCAL[k]["hex"] for k in FISCAL if k != "all"],
            ),
            legend=alt.Legend(title="Ownership", orient="bottom"),
        )
        st.altair_chart(
            _altair_fallback_map(
                _fb,
                color=_fb_color,
                size_field=vol_col,
                tooltip=[
                    alt.Tooltip("own_label:N", title="Ownership"),
                    alt.Tooltip("fiscal_cat:N", title="Fiscal"),
                    alt.Tooltip(f"{vol_col}:Q", title=f"{cat['short']} vol (ft³)", format=",.0f"),
                    alt.Tooltip("LAT:Q", title="Lat", format=".3f"),
                    alt.Tooltip("LON:Q", title="Lon", format=".3f"),
                ],
                towns=TOWNS,
                height=600,
            ),
            width="content",
        )
        st.caption(
            "🗺️ Simplified map (web version): points plotted by longitude/latitude, colored by "
            "ownership and sized by volume. Triangles mark towns. The full interactive basemap "
            "with pan/zoom is available in the desktop version of this dashboard."
        )

    # Map legend when in "all" mode
    if fiscal_filter == "all":
        leg_cols = st.columns(len(FISCAL) - 1)
        for col_ui, (fk, fdef) in zip(leg_cols, [(k, v) for k, v in FISCAL.items() if k != "all"]):
            r2, g2, b2 = fdef["color"]
            col_ui.markdown(
                f"<span style='display:inline-block;width:12px;height:12px;"
                f"background:rgb({r2},{g2},{b2});border-radius:50%;margin-right:4px'></span>"
                f"<small>{fdef['label']}</small>",
                unsafe_allow_html=True,
            )

    # Data table
    with st.expander("View plot-level data table"):
        disp = map_df[["PLT_CN", "LAT", "LON", "own_label", "fiscal_cat", "reserved",
                        vol_col, raw_col, cnt_col]].copy()
        disp.columns = ["Plot CN", "Lat", "Lon", "Ownership", "Fiscal Cat", "Reserved",
                        "Expanded Vol (ft³)", "Raw Vol (ft³)", "Trees"]
        disp = disp.sort_values("Expanded Vol (ft³)", ascending=False).reset_index(drop=True)
        st.dataframe(disp, width="stretch")

    # Expert methodology
    with st.expander("Expert Methodology — For University Researchers"):
        invyr_min = meta.get("invyr_min", "unknown")
        invyr_max = meta.get("invyr_max", "unknown")
        st.markdown(
            f"""
### Data Source
**USDA Forest Service, Forest Inventory and Analysis (FIA) Program**
Washington State CSV download from the FIA Datamart (`WA_CSV.zip`).
Tables used: `WA_PLOT`, `WA_TREE`, and `WA_COND`.

---

### ⚠️ Measurement Year Range — Critical Limitation

This dashboard includes **all available FIA plot measurements for Skamania County,
spanning inventory years {invyr_min}–{invyr_max}** (a rolling panel design where each plot
is revisited roughly every 10 years).

**What this means:** The same physical plot location may appear more than once in the dataset
— measured once around 2005 and again around 2015, for example. Volume figures shown here are
**not** equivalent to a current point-in-time inventory. A tree measured in 2008 that appears
in this data may have since been harvested, died, or grown into a larger size class.

**For statistically rigorous county-level totals:** filter to the current evaluation
(`EVALID = 532201`, Washington 2022: 2012–2022) and apply `POP_STRATUM` post-stratification
weights. This dashboard does not perform that filtering. **Treat all volume figures as
order-of-magnitude estimates, not auditable inventory counts.** Uncertainty is likely ±30–50%.

---

### Ownership Join
`WA_COND.OWNCD` is joined to plots via `PLT_CN`. The dominant condition (`CONDID = 1`) is used
for plots with multiple conditions. `RESERVCD = 1` indicates wilderness or other reserved status.

### Ownership Codes Used

| OWNCD | Label | Fiscal Category |
|---|---|---|
| 11 | National Forest | federal |
| 12–13 | Other Federal | federal |
| 21–25 | State / DNR Trust | state |
| 31–33 | Corporate / Private Timber | taxable |
| 46 | Tribal | tribal |

---

### Size Categories

| Category | DBH Range | Primary End Use |
|---|---|---|
| Biomass | 0–5" | Chips, hog fuel, energy |
| Small Timber | 5–9" | Mass timber feedstock (CLT/NLT) |
| Sawlogs | 9–15" | Conventional dimensional lumber |
| Premium | 15–21" | Glulam, premium appearance lumber |
| Large Timber | 21"+ | Veneer, specialty products |

---

### Volume Variables

**`VOLCFGRS`** — **Gross** cubic foot volume of the entire stem, including defect, decay,
and breakage that a mill would reject. Actual net merchantable volume is typically 10–25% lower,
with larger trees (premium, large_timber) showing the greatest defect-related reduction.
NULL for sub-merchantable trees (treated as 0 here).

**`TPA_UNADJ`** — Trees Per Acre unadjusted expansion factor. `VOLCFGRS × TPA_UNADJ` = cubic
feet per acre contribution for that sample tree. Unadjusted factors are used here; proper
county estimates require `TPA_ADJ` and `POP_STRATUM` post-stratification.

---

### Price Methodology

Ranges reflect Pacific Northwest benchmarks (2023–2025). Three tiers:
stumpage (landowner), mill gate (delivered), end product (finished goods).
Illustrative only — not formal appraisals.

**Note on small-diameter stumpage:** For small-diameter timber (5–9\") on steep or complex
National Forest terrain in the Pacific Northwest, **stumpage prices are frequently near zero
or negative** — meaning the Forest Service may subsidize removal through stewardship contracts
rather than generating revenue. The value capture argument for this size class depends on
mill gate pricing, which requires a negotiated stewardship contract structure.

---

### Known Limitations

| Issue | Impact |
|---|---|
| All measurement years included (not filtered to current EVALID) | May overstate current inventory by 30–50% |
| VOLCFGRS is gross, not net merchantable | Overstates harvestable volume, especially in 21"+ class |
| TPA_UNADJ used instead of TPA_ADJ | Minor bias depending on plot stratum |
| Plot coordinates fuzzed/swapped ±1 mile | Haul distance calculations have inherent uncertainty |
| Biomass (0–5") shows zero volume | Sub-merchantable trees not volumetrically measured by FIA |
| County-wide totals use mean density × acreage | Statistically invalid without POP_STRATUM weights |
            """
        )

# ════════════════════════════════════════════════════════════════════════════

def _fia_model():
    """Optional deeper model shown in the County Revenue expander: what the FIA
    land base could support if actively harvested. Superseded for day-to-day use by
    the Forest Service program figures above, but kept for feasibility-testing."""

    st.divider()
    st.markdown("#### The FIA inventory model")
    st.markdown(
        "The program figures shown on the main page work from the Forest Service's actual "
        "different question: what could the land base itself support, using FIA inventory data? "
        "Useful for testing whether the 2030 target is physically plausible — with the caveats below."
    )

    st.info(
        "The 'Exclude wilderness & reserved areas' checkbox in the sidebar applies here — "
        "checking it removes congressionally reserved plots from the inventory base.",
        icon="ℹ️",
    )
    st.warning(
        "**Three important caveats before reading these numbers:**  \n"
        "1. **Multi-cycle data:** This dashboard includes FIA plots measured 2001–2022. "
        "Volume figures likely overstate *current* inventory by 30–50% compared to a "
        "current-evaluation-only analysis (EVALID 532201, 2012–2022).  \n"
        "2. **Gross volume:** VOLCFGRS is gross stem volume, not net merchantable. "
        "Actual harvestable volume is 10–25% lower, especially in the larger size classes.  \n"
        "3. **Small-diameter stumpage economics:** On steep NF terrain, stumpage for 5–9\" "
        "timber is often near zero or negative. The breakeven analysis below shows this. "
        "Revenue projections in this tab assume benchmark stumpage prices that may not "
        "be achievable without a subsidized stewardship contract structure.",
        icon="⚠️",
    )
    st.divider()

    inp1, inp2, inp3 = st.columns(3)
    with inp1:
        harvest_rate = st.slider(
            "Annual harvest rate (% of standing inventory)",
            min_value=0.5, max_value=5.0, value=2.0, step=0.5, format="%.1f%%",
            help="Typical sustainable yield from actively managed NF land runs 1–3%/year. "
                 "Planning assumption only — not a silvicultural prescription.",
        )
    with inp2:
        fed_acres = st.number_input(
            "Federal forested acres in Skamania Co.",
            min_value=100_000, max_value=1_000_000, value=650_000, step=10_000,
            format="%d",
            help="Gifford Pinchot NF spans ~1.3M acres across several counties. "
                 "Skamania holds the largest share — roughly 600–700k acres. "
                 "Adjust if you have a more precise figure from the forest plan.",
        )
    with inp3:
        treatment_cost = st.slider(
            "Fuel treatment cost ($/acre)",
            min_value=500, max_value=2_000, value=1_200, step=100,
            help="USFS ground-based thinning in the Cascades typically runs $800–$1,500/acre. "
                 "Helicopter-assisted terrain pushes toward the high end.",
        )

    st.caption(
        f"At **{harvest_rate:.1f}%/year** the scenario harvests that share of expanded "
        f"inventory per category. County receives **25% of stumpage** under the historic formula. "
        f"County-wide totals scale the FIA mean per-acre density across **{fed_acres:,} federal acres**."
    )

    st.divider()
    st.markdown("#### Scenario Results by Timber Category — Federal Land Only")

    # Per-plot mean per-acre density across all federal plots (including zero-volume plots)
    n_fed_plots = max(len(federal_df), 1)

    scenario_rows = []
    total_county_lo = total_county_hi = 0.0
    total_harvest_mbf = 0.0
    for ck, cdef in CATEGORIES.items():
        fed_vol     = federal_df[f"{ck}_vol_expanded"].sum()
        mean_per_ac = federal_df[f"{ck}_vol_expanded"].mean()          # ft³/acre
        county_vol  = mean_per_ac * fed_acres                          # county-wide ft³
        harvested   = county_vol * harvest_rate / 100                  # annual ft³
        harvest_mbf = harvested * 12 / 1_000                          # annual MBF
        lo_p, hi_p, _ = cdef["prices"]["stumpage"]
        county_lo   = harvested * lo_p * 0.25
        county_hi   = harvested * hi_p * 0.25
        total_county_lo  += county_lo
        total_county_hi  += county_hi
        total_harvest_mbf += harvest_mbf
        scenario_rows.append({
            "Timber Category":       cdef["label"],
            "Mean density (ft³/ac)": mean_per_ac,
            "County-wide vol (ft³)": county_vol,
            "Harvest/yr (MBF)":      harvest_mbf,
            "Stumpage ($/ft³)":      f"${lo_p:.2f} – ${hi_p:.2f}",
            "County 25% — Low":      county_lo,
            "County 25% — High":     county_hi,
        })

    scen_df = pd.DataFrame(scenario_rows)
    disp_scen = scen_df.copy()
    disp_scen["Mean density (ft³/ac)"] = disp_scen["Mean density (ft³/ac)"].map("{:,.1f}".format)
    disp_scen["County-wide vol (ft³)"] = disp_scen["County-wide vol (ft³)"].map("{:,.0f}".format)
    disp_scen["Harvest/yr (MBF)"]      = disp_scen["Harvest/yr (MBF)"].map("{:,.1f}".format)
    disp_scen["County 25% — Low"]      = disp_scen["County 25% — Low"].map("${:,.0f}".format)
    disp_scen["County 25% — High"]     = disp_scen["County 25% — High"].map("${:,.0f}".format)
    st.dataframe(disp_scen, width="stretch", hide_index=True)
    st.caption(
        "MBF = thousand board feet (1 ft³ ≈ 12 board feet). "
        "County-wide volume is the FIA mean per-acre density × entered federal acreage — "
        "a planning estimate, not a statistically rigorous county total."
    )

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        f"County Receipt — Low",
        f"${total_county_lo/1e6:,.2f}M/yr",
        help="Low-end stumpage × 25% Fund formula, county-wide acreage estimate.",
    )
    m2.metric(
        f"County Receipt — High",
        f"${total_county_hi/1e6:,.2f}M/yr",
        help="High-end stumpage × 25% Fund formula.",
    )
    m3.metric(
        "Total Annual Harvest",
        f"{total_harvest_mbf:,.0f} MBF/yr",
        help="All size classes combined. A small-to-medium CLT plant needs roughly 10,000–50,000 MBF/yr.",
    )
    m4.metric(
        "Formula",
        "25% of stumpage",
        help="16 U.S.C. § 500 — counties received 25% of gross NF timber receipts for roads and schools.",
    )

    # ── Breakeven analysis ────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Fuel Treatment Breakeven — Small Timber")
    st.markdown(
        "The central policy question behind Commissioner Leckie's proposal: "
        "does the stumpage revenue from thinning small-diameter trees cover the cost of the treatment? "
        "If so, USFS can run a self-funding project. If not, what subsidy is required — and "
        "is that subsidy cheaper than the cost of the wildfire it prevents?"
    )

    # Focus on small timber — the fuel treatment category
    st_mean_per_ac   = federal_df["small_timber_vol_expanded"].mean()
    st_lo_p, st_hi_p, _ = CATEGORIES["small_timber"]["prices"]["stumpage"]
    stumpage_rev_lo  = st_mean_per_ac * st_lo_p    # $/acre
    stumpage_rev_hi  = st_mean_per_ac * st_hi_p    # $/acre
    stumpage_rev_mid = (stumpage_rev_lo + stumpage_rev_hi) / 2

    net_cost_lo  = treatment_cost - stumpage_rev_hi   # best case (high stumpage)
    net_cost_hi  = treatment_cost - stumpage_rev_lo   # worst case (low stumpage)
    county_per_ac_lo = stumpage_rev_lo * 0.25
    county_per_ac_hi = stumpage_rev_hi * 0.25

    b1, b2, b3, b4 = st.columns(4)
    b1.metric(
        "Small timber density",
        f"{st_mean_per_ac:,.0f} ft³/acre",
        help="Mean TPA-expanded volume of 5–9\" trees across federal non-reserved plots.",
    )
    b2.metric(
        "Stumpage revenue/acre",
        f"${stumpage_rev_lo:,.0f} – ${stumpage_rev_hi:,.0f}",
        help=f"At ${st_lo_p:.2f}–${st_hi_p:.2f}/ft³ stumpage.",
    )
    b3.metric(
        "Net USFS cost/acre",
        f"${max(net_cost_lo,0):,.0f} – ${max(net_cost_hi,0):,.0f}",
        help=f"Treatment cost (${treatment_cost:,}/acre) minus stumpage revenue. "
             "The gap USFS must cover through appropriations, grants, or stewardship contracts.",
    )
    b4.metric(
        "County 25% share/acre",
        f"${county_per_ac_lo:,.0f} – ${county_per_ac_hi:,.0f}",
        help="What Skamania County receives per treated acre under the 25% Fund formula.",
    )

    _mg_lo, _mg_hi, _ = CATEGORIES["small_timber"]["prices"]["mill_gate"]
    _mg_rev_lo = st_mean_per_ac * _mg_lo
    _mg_rev_hi = st_mean_per_ac * _mg_hi

    # Pre-format dollar strings to avoid LaTeX-triggering $ in markdown f-strings
    _s_treat   = f"${treatment_cost:,}"
    _s_stump   = f"${stumpage_rev_mid:,.0f}"
    _s_mg_lo   = f"${_mg_lo:.2f}"
    _s_mg_hi   = f"${_mg_hi:.2f}"
    _s_rev_lo  = f"${_mg_rev_lo:,.0f}"
    _s_rev_hi  = f"${_mg_rev_hi:,.0f}"

    if stumpage_rev_mid >= treatment_cost:
        st.success(
            f"At the current treatment cost ({_s_treat}/acre) and mean small timber density "
            f"({st_mean_per_ac:,.0f} ft³/acre), stumpage revenue **covers treatment costs** — "
            f"making a self-funding stewardship contract feasible. Adjust the sliders to test sensitivity."
        )
    else:
        gap = treatment_cost - stumpage_rev_mid
        gap_pct = gap / treatment_cost * 100
        cover_pct = 100 - gap_pct
        _s_gap = f"${gap:,.0f}"
        st.warning(
            f"Stumpage revenue (midpoint **{_s_stump}/acre**) covers "
            f"**{cover_pct:.0f}%** of the {_s_treat}/acre treatment cost. "
            f"The **{_s_gap}/acre gap** would need to be covered by USFS appropriations, "
            f"CFLRP grant funds, or a stewardship contract capturing mill gate value instead of stumpage. "
            f"At mill gate prices ({_s_mg_lo}–{_s_mg_hi}/ft³), "
            f"revenue reaches **{_s_rev_lo}–{_s_rev_hi}/acre** — "
            f"well above treatment cost."
        )

    st.divider()
    st.markdown("#### How This Compares to the 25% Fund Scenario")
    st.markdown(
        "Use the historical chart above to pick a reference year, or enter a custom amount "
        "to see how the 25% Fund scenario compares to actual SRS payments."
    )
    srs_actual = st.number_input(
        "Reference SRS payment ($/year)",
        min_value=0,
        value=2_467_843,
        step=100_000,
        format="%d",
        help="Default: FY2025 confirmed SRS payment ($2,467,842.84). "
             "Change to any year from the historical chart to compare.",
    )
    if srs_actual > 0:
        mid_scenario = (total_county_lo + total_county_hi) / 2
        delta = mid_scenario - srs_actual
        delta_pct = delta / srs_actual * 100
        d1, d2 = st.columns(2)
        d1.metric(
            "25% Fund scenario (midpoint)",
            f"${mid_scenario:,.0f}/yr",
            delta=f"{'+'if delta>=0 else ''}{delta:,.0f} vs SRS ({delta_pct:+.0f}%)",
            delta_color="normal",
        )
        d2.metric(
            "SRS payment entered",
            f"${srs_actual:,.0f}/yr",
        )
        _s_delta = f"${abs(delta):,.0f}"
        if delta > 0:
            st.success(
                f"At {harvest_rate:.1f}%/yr harvest, the 25% Fund would generate roughly "
                f"**{_s_delta}/yr more** than the SRS payment entered. "
                f"This is the revenue foregone by structurally replacing harvest receipts with a grant program."
            )
        else:
            st.warning(
                f"At {harvest_rate:.1f}%/yr harvest, the 25% Fund scenario yields roughly "
                f"**{_s_delta}/yr less** than the SRS payment entered — meaning Congress's "
                f"SRS formula has been more generous than active harvest would have generated at this rate. "
                f"Try increasing the harvest rate to find the breakeven."
            )

    st.divider()
    st.markdown(
        """
**Important caveats**
- Federal inventory in this scenario includes all FIA measurement cycles, not just the most recent.
  Actual harvestable volume would require current-cycle analysis with EVALID filtering.
- "Sustainable yield" depends on growth rates, age class distribution, and the Gifford Pinchot
  forest plan — 2% is a planning assumption only.
- The 25% Fund formula applies to gross receipts, which track stumpage prices at the time of sale.
- Biomass (0–5\" trees) shows near-zero because VOLCFGRS is not recorded for sub-merchantable trees.
- This tool is for policy illustration and public education, not for budget forecasting.
        """
    )

if section == "💰 County Revenue & Timber Payments":
    st.markdown("## County Revenue & Timber Payments")
    st.markdown(
        "**The short version.** Most of Skamania is federal forest, so instead of property "
        "tax the county leans on federal timber payments — and those have become unreliable. "
        "Below: what the county has actually received, what it pays for, and the one choice "
        "(how the timber is sold) that decides whether more logging would ever reach county schools."
    )
    st.caption(
        "Background: counties with National Forest land historically received 25% of timber "
        "sale receipts (the \"25% Fund\"). When harvests collapsed in the 1990s, Congress replaced "
        "that with Secure Rural Schools (SRS) payments — which need periodic reauthorization and "
        "have lapsed. Full explanation under Questions & Sources."
    )

    # ── Historical SRS payment chart ─────────────────────────────────────────
    st.divider()
    st.markdown("### The Payment Record — Skamania County, FY2010–FY2025")
    st.caption(
        "Source: USDA Forest Service ASR-10-03 Final Payment Detail Reports. "
        "FY2010–2012 extracted from USFS PDF archives (per-district amounts summed). "
        "FY2018 data not available in USFS archives."
    )

    _srs_df = pd.DataFrame(SRS_PAYMENTS)
    _srs_df["amount_m"] = _srs_df["amount"] / 1e6
    _srs_df["label"]    = _srs_df["amount"].apply(
        lambda v: f"${v/1e6:.2f}M" if v > 0 else ""
    )

    _srs_bars = (
        alt.Chart(_srs_df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("fy:O", title="Fiscal Year",
                    axis=alt.Axis(labelAngle=0, labelFlush=True)),
            y=alt.Y("amount_m:Q", title="Payment ($M)",
                    axis=alt.Axis(format="$~f")),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(
                    domain=list(_SRS_TYPE_COLORS.keys()),
                    range=list(_SRS_TYPE_COLORS.values()),
                ),
                legend=alt.Legend(title="Payment Type", orient="top-right"),
            ),
            tooltip=[
                alt.Tooltip("fy:O",       title="Fiscal Year"),
                alt.Tooltip("amount_m:Q", title="Amount ($M)",    format="$.3f"),
                alt.Tooltip("type:N",     title="Payment Type"),
                alt.Tooltip("note:N",     title="Notes"),
            ],
        )
        .properties(height=280)
    )

    # Value labels above each bar (skip zero / no-data bars)
    _srs_labels = _srs_df[_srs_df["amount"] > 0].copy()
    _srs_text = (
        alt.Chart(_srs_labels)
        .mark_text(dy=-7, fontSize=9, color="#444444")
        .encode(
            x=alt.X("fy:O"),
            y=alt.Y("amount_m:Q"),
            text=alt.Text("label:N"),
        )
    )

    # "No data" label for FY2018 gap
    _gap_df = pd.DataFrame([{"fy": 2018, "y": 0.18, "label": "no data"}])
    _gap_text = (
        alt.Chart(_gap_df)
        .mark_text(baseline="bottom", fontSize=9, fontStyle="italic", color="#999999")
        .encode(
            x=alt.X("fy:O"),
            y=alt.Y("y:Q"),
            text=alt.Text("label:N"),
        )
    )

    st.altair_chart(_srs_bars + _srs_text + _gap_text, width="stretch")

    # Summary callout
    _srs_confirmed = [r for r in SRS_PAYMENTS if r["amount"] > 0]
    _srs_avg_formula = sum(
        r["amount"] for r in _srs_confirmed if r["type"] == "SRS Formula"
    ) / max(sum(1 for r in _srs_confirmed if r["type"] == "SRS Formula"), 1)
    _srs_max_rec = max(_srs_confirmed, key=lambda r: r["amount"])
    _srs_min_rec = min(_srs_confirmed, key=lambda r: r["amount"])
    _fy24_rec  = next(r for r in SRS_PAYMENTS if r["fy"] == 2024)
    _fy23_rec  = next(r for r in SRS_PAYMENTS if r["fy"] == 2023)
    _drop_pct  = int(round((1 - _fy24_rec["amount"] / _fy23_rec["amount"]) * 100))
    _s_avg     = f"${_srs_avg_formula/1e6:.2f}M"
    _s_min     = f"${_srs_min_rec['amount']/1e6:.2f}M"
    _s_max     = f"${_srs_max_rec['amount']/1e6:.2f}M"
    _s_fy23    = f"${_fy23_rec['amount']/1e6:.2f}M"
    _s_fy24    = f"${_fy24_rec['amount']/1e6:.2f}M"
    st.caption(
        f"SRS Formula years average **{_s_avg}/yr**. "
        f"Range: **{_s_min}** (FY{_srs_min_rec['fy']}, 25% Fund fallback) to "
        f"**{_s_max}** (FY{_srs_max_rec['fy']}). "
        f"**Key risk:** Congress let SRS lapse in FY2024, dropping county revenue by "
        f"**{_drop_pct}%** in a single fiscal year — from {_s_fy23} to {_s_fy24}."
    )

    # ── What the payments fund: the school district stakes ───────────────────
    st.markdown("##### What these payments fund — the Stevenson-Carson stakes")
    _sk1, _sk2, _sk3 = st.columns(3)
    _sk1.metric(
        "Schools closed",
        "2",
        help="Stevenson-Carson School District closed its second school in June 2026; "
             "the first closure and a $1.85M budget cut were reported in February 2026. "
             "Source: SkamaniaDispatch reporting on district board actions.",
    )
    _sk2.metric(
        "Reported SRS distribution loss",
        "~$250K",
        help="Per EDC Director Kevin Waters at the June 30, 2026 BOCC meeting: a state "
             "drafting error stripped roughly 30% of SRS timber money from about 200 "
             "districts statewide, costing Stevenson-Carson roughly a quarter million dollars. "
             "Meeting record — figure pending written confirmation.",
    )
    _sk3.metric(
        "Corrective bill",
        "Drafted",
        help="Per Waters at the same meeting: a corrective bill is drafted with the "
             "state superintendent and DNR. Meeting record — pending confirmation.",
    )
    st.caption(
        "Federal forest payments are split between county roads and schools under state law "
        "(RCW 28A.520 governs the school apportionment). The chart above is county-level; "
        "the school district receives its share through the state distribution — which is "
        "where the reported drafting error hit. The point of pairing these numbers with the "
        "payment history: the FY2024 lapse and the distribution error are not abstractions — "
        "they land on a district that has now closed two schools."
    )

    # ── Part 1: The actual GP program & the mix question ─────────────────────
    st.divider()
    st.markdown("### The Mix Question — Traditional Sales vs. Stewardship")
    st.markdown(
        """
At the **June 16 and June 30, 2026 BOCC meetings**, commissioners pressed the Gifford Pinchot
to make traditional timber sales at least **50% of the forest's program, with 75% as the goal**
("I want the floor to be 50 percent"). The distinction matters because of how the money moves:

| Contract vehicle | Where the timber value goes | County schools & roads receive |
|---|---|---|
| **Traditional timber sale** | Purchaser pays USFS → gross receipts | **25% of receipts** via the 25% Fund |
| **Stewardship contract** | Timber value traded against restoration work (goods-for-services) | **Little to none** — receipts are offset, not distributed |
| **Good Neighbor Authority (GNA)** | Receipts retained for further restoration under the agreement | **None distributed to counties** |

Whatever the forest-health merits of each vehicle — and stewardship work has real merits —
the *vehicle choice* determines whether a school district sees a dollar. That is the entire
substance of the "floor" demand.
        """
    )

    _p1, _p2, _p3, _p4 = st.columns(4)
    _p1.metric("Recent years (avg)", "~32M BF/yr", help="GP-wide planned volume, all contract vehicles.")
    _p2.metric("2026 planned", "36M BF", help="GP-wide planned volume for 2026.")
    _p3.metric("2030 stated target", "68M BF", help="GP-wide target stated by Forest Service staff.")
    _p4.metric("Thinning program", f"{GP_THINNING_ACRES_YR:,} ac/yr",
               help="Forest-wide thinning program, stated 20–30 year horizon.")
    st.caption(
        "Program figures as shared by Forest Service staff at the June 30, 2026 BOCC meeting. "
        "Meeting record — **pending written confirmation** from the Gifford Pinchot."
    )

    _mx1, _mx2 = st.columns(2)
    with _mx1:
        _mx_price = st.slider(
            "Blended stumpage ($/MBF)",
            min_value=100, max_value=600, value=300, step=25,
            help="Blended across size classes and species. Westside federal stumpage varies "
                 "widely with sale design; recent regional comparables run roughly $200–$450/MBF. "
                 "This is the single most sensitive assumption in the table below.",
        )
    with _mx2:
        _mx_share_pct = st.slider(
            "Skamania share of GP 25% Fund distribution (%)",
            min_value=30, max_value=70, value=50, step=5,
            help="The 25% Fund distributes receipts to counties in proportion to NF acreage "
                 "within each county. ASR reports list 532,288 Skamania acres in the GP — "
                 "the largest county share. Adjust if you have the precise distribution percentage.",
        )
    _mx_share = _mx_share_pct / 100

    st.markdown("##### County revenue by program level and traditional-sale share")
    _mx_rows = []
    for _lvl_name, _lvl_mbf in GP_PROGRAM_MBF.items():
        _row = {"GP program level": f"{_lvl_name} — {_lvl_mbf/1000:.0f}M BF/yr"}
        for _trad in (0.25, 0.50, 0.75, 1.00):
            _rev = _lvl_mbf * _trad * _mx_price * 0.25 * _mx_share
            _row[f"{int(_trad*100)}% traditional"] = f"${_rev/1e6:.2f}M/yr"
        _mx_rows.append(_row)
    st.dataframe(pd.DataFrame(_mx_rows), width="stretch", hide_index=True)
    st.caption(
        "County revenue = GP volume × traditional share × blended stumpage × 25% Fund × Skamania share. "
        "**50% traditional** is the commissioners' stated floor; **75%** is the stated goal. "
        "The 25% Fund pays a 7-year rolling average of receipts, so a program ramp-up reaches "
        "county budgets gradually — full effect only after several sustained years."
    )

    # SRS replacement threshold — the reverse calculation
    _mx_srs_avg = sum(
        r["amount"] for r in SRS_PAYMENTS if r["type"] == "SRS Formula"
    ) / max(sum(1 for r in SRS_PAYMENTS if r["type"] == "SRS Formula"), 1)
    _mx_srs_fy25 = next(r["amount"] for r in SRS_PAYMENTS if r["fy"] == 2025)
    _mx_bf_fy25  = _mx_srs_fy25 / (0.25 * _mx_share * _mx_price)   # MBF at 100% traditional
    _mx_bf_avg   = _mx_srs_avg  / (0.25 * _mx_share * _mx_price)
    _mx_2030_75  = GP_PROGRAM_MBF["2030 stated target"] * 0.75 * _mx_price * 0.25 * _mx_share
    _mx_gap_75   = _mx_srs_avg - _mx_2030_75

    st.markdown("##### The SRS replacement threshold")
    _t1, _t2, _t3 = st.columns(3)
    _t1.metric(
        "To replace FY2025 SRS ($2.47M)",
        f"~{_mx_bf_fy25/1000:.0f}M BF/yr",
        help="GP-wide volume needed at 100% traditional sales and the slider assumptions above. "
             "Compare: the stated 2030 target is 68M BF.",
    )
    _t2.metric(
        "To match SRS-formula average",
        f"~{_mx_bf_avg/1000:.0f}M BF/yr",
        help=f"Matching the ${_mx_srs_avg/1e6:.2f}M/yr average of FY2013–FY2025 formula years.",
    )
    _t3.metric(
        "2030 target @ 75% traditional",
        f"${_mx_2030_75/1e6:.2f}M/yr",
        delta=f"{(_mx_2030_75 - _mx_srs_avg)/1e6:+.2f}M vs SRS avg",
        help="What the commissioners' aspirational mix delivers at the stated 2030 volume target.",
    )

    _s_gap75 = f"${abs(_mx_gap_75)/1e6:.2f}M"
    if _mx_gap_75 > 0:
        st.info(
            f"**The arithmetic behind the strategy question:** at these assumptions, even the "
            f"Forest Service's 2030 target at the commissioners' 75% traditional goal falls about "
            f"**{_s_gap75}/yr short** of the SRS-formula average. This is not an argument against "
            f"the timber push — it is the reason the timber push and the **SRS/PILT recombination** "
            f"strategy (raised at the June 30 meeting after EDC Director Waters' conversation with "
            f"Sen. Merkley) are complements rather than alternatives. If even success falls short, "
            f"structural payment reform isn't just advocacy — it's arithmetic.",
            icon="🧮",
        )
    else:
        st.success(
            f"At these assumptions, the 2030 target at a 75% traditional mix would **exceed** the "
            f"SRS-formula average by about {_s_gap75}/yr. Note this requires both the volume ramp "
            f"(68M BF, nearly double current) *and* the mix shift to materialize, and the 7-year "
            f"rolling average delays the full effect."
        )

    st.markdown(
        """
**A structural option on the table:** at the June 30 meeting, the Forest Supervisor offered to
connect Skamania with a **California county that built a master stewardship agreement program
from scratch**. A master agreement doesn't by itself change the 25% Fund math — but it can give
the county a seat in designing sale structure, local-hire terms, and the traditional/stewardship
mix over a multi-year horizon rather than sale-by-sale. The county's homework before that
conversation: know exactly which revenue outcome it needs the agreement to protect
(the mix table above is that number).
        """
    )


    st.divider()
    with st.expander("🔍 Deeper detail — what the land base could support (FIA model)"):
        _fia_model()

# ════════════════════════════════════════════════════════════════════════════
if section == "🌊 State Logging Rules":
    st.markdown("## State Logging Rules — the New Stream Buffers")
    st.markdown(
        "**The short version.** While federal payments shrink, the state is adding to the cost "
        "of logging the private land that actually pays county tax. A new rule widens the "
        "no-cut buffer along small non-fish streams from 50 to 75 feet, starting August 2026. "
        "This page puts real numbers on what that means for Skamania — using the state's own "
        "cost estimates — and sits alongside the federal payment picture, because the county "
        "feels both at once."
    )
    st.markdown(
        """
The Washington State Forest Practices Board voted **7–5 on November 12, 2025** to expand
no-harvest buffer requirements along Type Np (non-fish-bearing perennial) streams — small
year-round streams without fish — on private and state-owned forestland in Western Washington.

**This is not advocacy for or against the rule.** The rule was adopted through the state's
formal rulemaking process and cites peer-reviewed science on water temperature and stream
health. The goal here is to make both the costs and the context quantifiable, so conversations
between county commissioners, landowners, state agencies, and conservation stakeholders can
start from a shared factual baseline rather than competing generalizations.
        """
    )

    st.info(
        "**Source:** Washington DNR FP Hydro layer queried May 2026 · "
        "WA Forest Practices Board Type Np Rule CBA (Industrial Economics Inc., April 2025) · "
        "Cascade Daily News reporting on November 2025 final vote.",
        icon="📋",
    )

    st.divider()

    # ── Stream classification breakdown ──────────────────────────────────────
    st.markdown("#### How Skamania County's Streams Are Classified")
    st.markdown(
        "Washington DNR classifies every mapped stream under the Forest Practices rules. "
        "The classification determines whether a buffer is required — and how wide. "
        "Data queried from the [DNR FP Hydro REST API](https://gis.dnr.wa.gov/site2/rest/services/Public_Forest_Practices/WADNR_PUBLIC_FP_Hydro/MapServer/0) "
        "for the Skamania County bounding box (42,335 stream segments, all land ownerships)."
    )

    # Hardcoded from our API query — avoids a live call on every page load
    _stream_types = pd.DataFrame([
        {"type_code": "N",  "type_name": "Non-fish bearing",          "miles": 15_367.1,
         "note": "Subject to new buffer rule (Np subset)"},
        {"type_code": "F",  "type_name": "Fish bearing",               "miles":  4_878.6,
         "note": "Existing 50–100 ft buffers apply"},
        {"type_code": "U",  "type_name": "Untyped / not yet classified","miles":  2_735.4,
         "note": "No current buffer requirement"},
        {"type_code": "S",  "type_name": "Shorelines of the State",    "miles":  1_447.8,
         "note": "Highest protection tier"},
        {"type_code": "X",  "type_name": "No designation",             "miles":    335.1,
         "note": ""},
    ])
    _total_stream_miles = _stream_types["miles"].sum()
    _stream_types["share"] = (_stream_types["miles"] / _total_stream_miles * 100).round(1)
    _stream_types["label"] = _stream_types.apply(
        lambda r: f"{r['share']:.1f}%  ({r['miles']:,.0f} mi)", axis=1
    )

    _TYPE_COLORS = {
        "N": "#e88020",   # amber — non-fish (subject to rule)
        "F": "#1e64be",   # blue — fish-bearing
        "U": "#9e9e9e",   # gray — untyped
        "S": "#2196f3",   # light blue — shorelines
        "X": "#cccccc",   # pale — no designation
    }
    _stream_types["color"] = _stream_types["type_code"].map(_TYPE_COLORS)

    _stream_bar = (
        alt.Chart(_stream_types)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("miles:Q", title="Stream Miles",
                    axis=alt.Axis(format="~s")),
            y=alt.Y("type_name:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=220)),
            color=alt.Color(
                "type_code:N",
                scale=alt.Scale(
                    domain=list(_TYPE_COLORS.keys()),
                    range=list(_TYPE_COLORS.values()),
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("type_name:N", title="Stream Type"),
                alt.Tooltip("miles:Q",     title="Miles",    format=",.1f"),
                alt.Tooltip("share:Q",     title="Share (%)", format=".1f"),
                alt.Tooltip("note:N",      title="Notes"),
            ],
        )
        .properties(height=180)
    )

    _st_inside  = _stream_types[_stream_types["share"] > 20].copy()
    _st_outside = _stream_types[_stream_types["share"] <= 20].copy()
    _st_inside["mid_miles"] = _st_inside["miles"] / 2

    _st_text_in = alt.Chart(_st_inside).mark_text(
        align="center", baseline="middle", fontSize=12, color="white"
    ).encode(
        x=alt.X("mid_miles:Q"),
        y=alt.Y("type_name:N", sort="-x"),
        text=alt.Text("label:N"),
    )
    _st_text_out = alt.Chart(_st_outside).mark_text(
        align="left", dx=4, fontSize=11, color="#333333"
    ).encode(
        x=alt.X("miles:Q"),
        y=alt.Y("type_name:N", sort="-x"),
        text=alt.Text("label:N"),
    )

    st.altair_chart(_stream_bar + _st_text_in + _st_text_out, width="stretch")

    # Non-fish sub-breakdown
    st.markdown("##### Inside the 15,367 miles of Non-Fish Streams")
    st.markdown(
        "The Forest Practices Act distinguishes between **perennial** (year-round flow) and "
        "**seasonal** streams. The new buffer rule specifically targets **Type Np** — "
        "non-fish-bearing *perennial* streams. Most non-fish stream miles in the DNR database "
        "currently carry an **unknown continuity** classification — which is the pivotal "
        "variable in the rule's long-term impact."
    )

    _np_breakdown = pd.DataFrame([
        {"continuity": "Perennial (Np) — confirmed",     "miles": 491.5,
         "color": "#e88020", "note": "Directly subject to new rule — buffer 50 ft → 75 ft"},
        {"continuity": "Seasonal (Ns) — confirmed",      "miles": 340.1,
         "color": "#f4a340", "note": "Not subject to the Np rule; existing rules apply"},
        {"continuity": "Unknown continuity",              "miles": 14_535.4,
         "color": "#d0d0d0", "note": "The contested bucket: field reclassification could "
                                     "expand the Np category substantially"},
    ])
    _np_total = _np_breakdown["miles"].sum()
    _np_breakdown["share"] = (_np_breakdown["miles"] / _np_total * 100).round(1)
    _np_breakdown["label"] = _np_breakdown.apply(
        lambda r: f"{r['share']:.1f}%  ({r['miles']:,.0f} mi)", axis=1
    )

    _np_bar = (
        alt.Chart(_np_breakdown)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("miles:Q", title="Stream Miles", axis=alt.Axis(format="~s")),
            y=alt.Y("continuity:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=260)),
            color=alt.Color(
                "continuity:N",
                scale=alt.Scale(
                    domain=_np_breakdown["continuity"].tolist(),
                    range=_np_breakdown["color"].tolist(),
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("continuity:N", title="Classification"),
                alt.Tooltip("miles:Q",      title="Miles",    format=",.1f"),
                alt.Tooltip("share:Q",      title="Share (%)", format=".1f"),
                alt.Tooltip("note:N",       title="Meaning"),
            ],
        )
        .properties(height=140)
    )

    _np_txt_in  = _np_breakdown[_np_breakdown["share"] > 20].copy()
    _np_txt_in["mid_mi"] = _np_txt_in["miles"] / 2
    _np_txt_out = _np_breakdown[_np_breakdown["share"] <= 20].copy()

    _np_text_layer_in = alt.Chart(_np_txt_in).mark_text(
        align="center", baseline="middle", fontSize=11, color="white"
    ).encode(
        x=alt.X("mid_mi:Q"),
        y=alt.Y("continuity:N", sort="-x"),
        text=alt.Text("label:N"),
    )
    _np_text_layer_out = alt.Chart(_np_txt_out).mark_text(
        align="left", dx=4, fontSize=11, color="#333333"
    ).encode(
        x=alt.X("miles:Q"),
        y=alt.Y("continuity:N", sort="-x"),
        text=alt.Text("label:N"),
    )
    st.altair_chart(_np_bar + _np_text_layer_in + _np_text_layer_out, width="stretch")

    st.caption(
        "Source: Washington DNR FP Hydro layer, May 2026. County bounding box query — "
        "includes streams on all land ownership types (federal, state, private, tribal). "
        "Only private and state-owned forestland is subject to the Forest Practices Act."
    )

    # ── What the rule actually says ───────────────────────────────────────────
    st.divider()
    st.markdown("#### What the Rule Actually Changes")

    _rule_cols = st.columns(2)
    with _rule_cols[0]:
        st.markdown("**Before (current rule)**")
        st.markdown(
            """
- Type Np streams: **50-foot no-harvest buffer** measured horizontally from bankfull width
- Buffer required along portions of the stream within a specified distance from a Type S or F confluence
- No buffer required on reaches beyond the trigger length
            """
        )
    with _rule_cols[1]:
        st.markdown("**After (effective August 2026)**")
        st.markdown(
            """
- **75-foot no-harvest buffer** for the first 600 feet upstream from a Type S or F confluence
- For basins >30 acres with >85% harvest planned in 5 years: 75-foot buffer the **entire stream length**
- For remaining reaches: 50-foot no-harvest + 25-foot partial-harvest zone (up to 50% removal), OR 65-foot full no-harvest buffer
- Sensitive sites (headwall seeps, etc.): additional 50-foot protections
            """
        )
    st.markdown(
        "_Scientific basis cited by FPB:_ Decades of research indicating that 50-foot buffers are "
        "insufficient to maintain water temperature standards in harvested units adjacent to Np streams. "
        "The board determined that buffer widths consistent with the rule are required to meet "
        "water quality standards under the Clean Water Act."
    )

    # ── Impact calculator ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Impact Calculator — Skamania County")
    st.markdown(
        "Use the state's own preliminary CBA figures (Industrial Economics Inc., April 2025) "
        "to estimate Skamania-specific impacts. Two key uncertainties drive the range: "
        "what fraction of non-fish streams are on FPA-regulated (private/state) land, "
        "and how many unknown-continuity streams are eventually reclassified as perennial."
    )

    _ic1, _ic2 = st.columns(2)
    with _ic1:
        _fpa_pct = st.slider(
            "Fraction of Np streams on FPA-regulated land (%)",
            min_value=5, max_value=25, value=10, step=1,
            help="Only private and state-owned forestland is subject to the Forest Practices Act. "
                 "Skamania is ~90% Gifford Pinchot NF (not subject) and ~10% private/state. "
                 "Stream density varies — western valleys have more private land and more streams. "
                 "10% is a conservative baseline; 18–20% may be more accurate for the western portion.",
        )
    with _ic2:
        _reclass_pct = st.slider(
            "% of unknown-continuity streams eventually classified as perennial",
            min_value=0, max_value=30, value=5, step=1,
            help="14,535 miles of non-fish streams have no recorded continuity in the DNR database. "
                 "Field surveys triggered by the new rule may reclassify some as perennial (Np), "
                 "bringing them under the buffer requirements. "
                 "Even 5% reclassification adds ~727 miles — more than the currently confirmed Np total.",
        )

    _confirmed_np_mi = 491.5
    _unknown_mi      = 14_535.4
    _reclassified_mi = _unknown_mi * _reclass_pct / 100
    _total_np_mi     = _confirmed_np_mi + _reclassified_mi
    _fpa_np_mi       = _total_np_mi * _fpa_pct / 100

    # CBA per-mile figures (statewide averages from IEc preliminary CBA, April 2025)
    _land_val_lo_per_mi = 17_000   # $ present value lost per Np mile
    _land_val_hi_per_mi = 23_000
    _econ_lo_per_mi     =  7_700   # $/yr total economic activity lost per Np mile
    _econ_hi_per_mi     = 15_000
    _harvest_lo_per_mi  =  0.68    # MBF/yr reduced per Np mile
    _harvest_hi_per_mi  =  1.30
    _tax_lo_per_mi      =     16   # $/yr timber excise tax lost per Np mile
    _tax_hi_per_mi      =     27

    _land_lo  = _fpa_np_mi * _land_val_lo_per_mi
    _land_hi  = _fpa_np_mi * _land_val_hi_per_mi
    _econ_lo  = _fpa_np_mi * _econ_lo_per_mi
    _econ_hi  = _fpa_np_mi * _econ_hi_per_mi
    _mbf_lo   = _fpa_np_mi * _harvest_lo_per_mi
    _mbf_hi   = _fpa_np_mi * _harvest_hi_per_mi
    _tax_lo   = _fpa_np_mi * _tax_lo_per_mi
    _tax_hi   = _fpa_np_mi * _tax_hi_per_mi

    _r1, _r2, _r3, _r4 = st.columns(4)
    _r1.metric(
        "Np miles on FPA land (estimated)",
        f"{_fpa_np_mi:,.0f} mi",
        help=f"Confirmed: {_confirmed_np_mi:.0f} mi · Reclassified: {_reclassified_mi:,.0f} mi · "
             f"FPA fraction: {_fpa_pct}%",
    )
    _r2.metric(
        "Land value loss (one-time PV)",
        f"${_land_lo/1e6:,.1f}M – ${_land_hi/1e6:,.1f}M",
        help="Present value reduction in forestland market value. "
             "Per-mile figure from IEc preliminary CBA, April 2025.",
    )
    _r3.metric(
        "Annual economic activity lost",
        f"${_econ_lo/1e3:,.0f}K – ${_econ_hi/1e3:,.0f}K/yr",
        help="Includes direct harvest value reduction and downstream supply chain effects. "
             "Per-mile figure from IEc preliminary CBA.",
    )
    _r4.metric(
        "Annual harvest reduction",
        f"{_mbf_lo:,.0f} – {_mbf_hi:,.0f} MBF/yr",
        help="Thousand board feet per year of reduced harvest on affected FPA land. "
             "At these volumes, annual timber excise tax reduction is "
             f"${_tax_lo:,.0f}–${_tax_hi:,.0f}/yr.",
    )

    st.caption(
        f"**Inputs:** {_confirmed_np_mi:.0f} confirmed Np miles + {_reclassified_mi:,.0f} reclassified "
        f"({_reclass_pct}% of {_unknown_mi:,.0f} unknown-continuity miles) = "
        f"**{_total_np_mi:,.0f} total Np miles**, of which **{_fpa_np_mi:,.0f} miles** are estimated "
        f"on FPA-regulated land ({_fpa_pct}%). "
        f"Per-mile figures from statewide IEc CBA averages — Skamania terrain and species mix may differ. "
        f"Annual excise tax impact: **${_tax_lo:,.0f}–${_tax_hi:,.0f}/yr**."
    )

    # What the rule is designed to protect
    with st.expander("What the rule is designed to protect — the benefit side"):
        st.markdown(
            """
The state's preliminary CBA found the following **probable benefits** from wider Np buffers:

**Water temperature protection (moderate to major benefit)**
Research cited by the FPB shows that 50-foot buffers adjacent to Np streams are insufficient
to prevent water temperature increases during and after harvest. Cooler, more stable stream
temperatures benefit macroinvertebrates, amphibians, and — indirectly — fish in downstream
connected Type F waters. The FPB determined that meeting Clean Water Act temperature standards
requires the wider buffers.

**Wildlife habitat (moderate benefit)**
The rule adds an estimated 67,000–170,000 acres of harvest-restricted riparian forest statewide —
representing 0.4–0.9% of total western Washington forest habitat. Riparian zones support
85% of the state's terrestrial vertebrate species and are disproportionately important for
breeding, foraging, and migration.

**Amphibian habitat (19,000–44,000 stream miles statewide)**
Non-fish-bearing streams are critical habitat for stream-associated amphibians (tailed frogs,
torrent salamanders, Pacific giant salamanders) that are sensitive to both water temperature
and riparian canopy removal.

**Carbon sequestration (negligible to minor)**
IEc estimated 220,000–3.3 million metric tons CO₂ in additional sequestration over 45 years —
a wide range reflecting significant uncertainty about harvest practices and timber end uses.

**The 7–5 vote reflects genuine disagreement** among board members about whether these benefits,
many of which are difficult to monetize, outweigh the quantified costs borne by private landowners
and timber-dependent counties. That's not a flaw in the process — it's an honest reflection of
the tradeoff.
            """
        )

    # ── Combined fiscal pressure ───────────────────────────────────────────────
    st.divider()
    st.markdown("#### Combined Fiscal Pressure on Skamania County")
    st.markdown(
        "Federal and state policy pressures don't arrive in separate buckets. "
        "The chart below puts them in the same frame using real numbers — "
        "not to argue against either policy, but to show the cumulative fiscal context "
        "county commissioners are navigating simultaneously."
    )

    # Build a combined comparison chart
    # Left side: SRS lapse risk (annual gap between SRS formula avg and 25% Fund fallback)
    _srs_formula_avg = sum(
        r["amount"] for r in SRS_PAYMENTS if r["type"] == "SRS Formula"
    ) / max(sum(1 for r in SRS_PAYMENTS if r["type"] == "SRS Formula"), 1)
    _fy24_amount = next(r["amount"] for r in SRS_PAYMENTS if r["fy"] == 2024)
    _srs_lapse_gap = _srs_formula_avg - _fy24_amount   # annual gap during a lapse year

    # Right side: buffer rule impacts (use current slider values)
    _econ_mid = (_econ_lo + _econ_hi) / 2
    _land_mid = (_land_lo + _land_hi) / 2

    _pressure_df = pd.DataFrame([
        {
            "item":     "SRS lapse gap (FY2024 vs. avg SRS year)",
            "category": "Federal — SRS Risk",
            "amount":   _srs_lapse_gap,
            "unit":     "annual",
            "note":     f"SRS formula avg ${_srs_formula_avg/1e6:.2f}M/yr vs. "
                        f"FY2024 25% Fund fallback ${_fy24_amount/1e6:.2f}M/yr",
        },
        {
            "item":     "Buffer rule: annual economic activity lost (mid-estimate)",
            "category": "State — Buffer Rule",
            "amount":   _econ_mid,
            "unit":     "annual",
            "note":     f"At {_fpa_pct}% FPA land, {_reclass_pct}% reclassification. "
                        f"Range: ${_econ_lo/1e3:,.0f}K–${_econ_hi/1e3:,.0f}K/yr.",
        },
        {
            "item":     "Buffer rule: one-time land value reduction (mid-estimate)",
            "category": "State — Buffer Rule",
            "amount":   _land_mid,
            "unit":     "one-time",
            "note":     f"Present value of forestland market value reduction. "
                        f"Range: ${_land_lo/1e6:.1f}M–${_land_hi/1e6:.1f}M.",
        },
        {
            "item":     "PILT (baseline federal payment — stable)",
            "category": "Federal — Stable",
            "amount":   800_000,
            "unit":     "annual",
            "note":     "Estimated PILT for Skamania County (~$800K/yr). "
                        "Permanently authorized in 2012. Not subject to SRS lapse.",
        },
    ])

    _pressure_colors = {
        "Federal — SRS Risk":  "#e88020",
        "State — Buffer Rule": "#c0392b",
        "Federal — Stable":    "#1e64be",
    }

    _press_bars = (
        alt.Chart(_pressure_df)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("amount:Q", title="Dollar Impact",
                    axis=alt.Axis(format="$~s")),
            y=alt.Y("item:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=340)),
            color=alt.Color(
                "category:N",
                scale=alt.Scale(
                    domain=list(_pressure_colors.keys()),
                    range=list(_pressure_colors.values()),
                ),
                legend=alt.Legend(title="Pressure Category", orient="top-right"),
            ),
            tooltip=[
                alt.Tooltip("item:N",     title="Item"),
                alt.Tooltip("amount:Q",   title="Amount ($)", format="$,.0f"),
                alt.Tooltip("unit:N",     title="Frequency"),
                alt.Tooltip("note:N",     title="Notes"),
                alt.Tooltip("category:N", title="Category"),
            ],
        )
        .properties(height=200)
    )

    _press_text = (
        alt.Chart(_pressure_df)
        .mark_text(align="left", dx=6, fontSize=11, color="#333333")
        .encode(
            x=alt.X("amount:Q"),
            y=alt.Y("item:N", sort="-x"),
            text=alt.Text("amount:Q", format="$,.0f"),
        )
    )

    st.altair_chart(_press_bars + _press_text, width="stretch")

    _s_srs_gap  = f"${_srs_lapse_gap/1e6:.2f}M"
    _s_econ_mid = f"${_econ_mid/1e3:,.0f}K"
    _s_land_mid = f"${_land_mid/1e6:.1f}M"
    st.caption(
        f"**Reading this chart:** The SRS lapse gap ({_s_srs_gap}/yr during a lapse year) and the "
        f"buffer rule's annual economic impact ({_s_econ_mid}/yr at current slider settings) are "
        f"both annual flows. The land value reduction ({_s_land_mid}, one-time present value) is a "
        f"stock effect — it reduces the underlying asset value of private timberland permanently, "
        f"affecting financing capacity and estate planning for small forest landowners. "
        f"Adjust the sliders above to see how assumptions change the picture."
    )

    st.warning(
        "**What this chart does and doesn't show.**  \n"
        "The SRS gap and buffer rule costs are real and documented. The chart does **not** show: "
        "the water quality and habitat benefits of the buffer rule (which are real but harder to "
        "monetize); the fact that most of Skamania's non-fish streams are on federal land not "
        "subject to this rule; or the distributional question of who bears these costs "
        "(primarily small forest landowners, not county government directly). "
        "These numbers are starting points for conversation, not a verdict.",
        icon="⚠️",
    )

    st.divider()
    st.markdown("#### What a Quality Conversation Looks Like")
    st.markdown(
        """
The county's $3,000 cost-share for an amicus brief is a legitimate expression of concern.
But data-grounded conversations with the Forest Practices Board, DNR, and conservation
stakeholders can go further. Specific questions this data supports:

**1. What fraction of Skamania's unknown-continuity streams will be reclassified?**
The 14,535 miles of unclassified non-fish streams dwarf the 491 confirmed Np miles.
DNR should publish a field reclassification plan and timeline for western Washington counties
so landowners can plan capital improvements and harvest schedules accordingly.

**2. What is the county-level incidence of costs vs. the statewide distribution of benefits?**
The CBA's $320M–$1B statewide cost is borne primarily by landowners in timber-dependent counties.
The water temperature, habitat, and tribal cultural benefits are felt across the entire Columbia
and Puget Sound watersheds. An honest policy conversation accounts for that distributional asymmetry.

**3. Can FPA rules and SRS advocacy be coordinated?**
Skamania is facing simultaneous pressure from federal payment uncertainty (SRS) and state
harvest restrictions. A county that can quantify both pressures together — as this dashboard
does — has a stronger argument for federal payment reform, CFLRP funding, and state-level
mitigation programs than one presenting either issue in isolation.

**4. Are there mitigation mechanisms for small forest landowners?**
Washington's Department of Commerce and DNR both have programs supporting small forest
landowners. Conservation easements, forest carbon credits, and Working Forest agreements
can generate alternative revenue streams for acres taken out of harvest by the new buffers.
These alternatives deserve as much attention as the legal challenge.
        """
    )

# ════════════════════════════════════════════════════════════════════════════
if section == "❓ Questions & Sources":
    st.markdown("## Frequently Asked Questions")
    st.markdown(
        "Plain-English answers about this data and what it means for Skamania County."
    )

    with st.expander("Where does this data come from?"):
        st.markdown(
            """
The numbers come from the **USDA Forest Service's Forest Inventory and Analysis (FIA) program** —
the federal government's ongoing census of all forests in the United States.

FIA has been collecting data since the 1930s. For Washington State, field crews visit thousands
of permanent sample plots scattered across the landscape, measuring every tree they find.
This dashboard uses the publicly available Washington State download from the FIA Datamart.
            """
        )

    with st.expander("How does the Forest Service actually count the trees?"):
        st.markdown(
            """
**Field crews on the ground — not satellites or drones.**

Each FIA plot is a cluster of four small circular subplots, each about 24 feet in radius.
A two- or three-person crew walks every plot and physically measures each tree using a
diameter tape (like a tailor's measuring tape, but calibrated for tree trunks).

They record:
- **Diameter at breast height (DBH)** — measured at 4.5 feet off the ground
- **Tree height** — measured with a clinometer (an angle-measuring tool)
- **Species**, health, and status (live vs. dead)

Volume is then estimated using species-specific equations built from trees that were
actually felled and measured decades ago. No lasers — clipboard-and-tape forestry,
scaled up with statistics.
            """
        )

    with st.expander("If they only measured some plots, how do we get county-wide numbers?"):
        st.markdown(
            """
**Statistical sampling** — the same principle as a poll or a medical study.

FIA places plots on a systematic grid across the US, roughly one plot per 6,000 acres of forest.
Each plot's measurements are expanded to represent the surrounding landscape using **TPA_UNADJ**
(Trees Per Acre). If one tree represents 6,000 acres statistically, that single tree
"stands in" for the trees across all 6,000 acres in the estimate.

**Important caveat:** Because it's a sample, there is uncertainty in the totals.
The true county-wide volume could be 20–30% higher or lower.
These numbers are best used to understand *relative* differences — not precise inventory counts.
            """
        )

    with st.expander("Why does most of the map show federal land?"):
        st.markdown(
            """
Because Skamania County is dominated by the **Gifford Pinchot National Forest.**

Roughly **91% of the forested plots** in the FIA database for Skamania County fall on
National Forest land. Another ~5% is on Yakama Nation tribal trust land.
That leaves approximately **4–5% on privately taxable land.**

This is the core fiscal challenge: the county sits on an enormous natural resource base,
but the vast majority of it is owned and managed by the federal government,
generating no local property tax.
            """
        )

    with st.expander("What are SRS and PILT, and why does it matter?"):
        st.markdown(
            """
**Secure Rural Schools (SRS)** and **Payment in Lieu of Taxes (PILT)** are federal programs
that compensate counties for the tax revenue they cannot collect from federal land.

- **PILT** — A baseline annual payment calculated by formula, funded through annual appropriations.
  More stable but typically modest.
- **SRS** — Originally tied to timber receipts from National Forest sales. When timber harvests
  fell (spotted owl era and after), Congress replaced lost revenue with direct SRS payments.
  Has expired and been reauthorized multiple times, creating multi-year funding gaps.

When SRS payments are delayed or reduced, Skamania County faces immediate shortfalls in
**school funding, road maintenance, and emergency services** — the direct consequences of
having most of its land base off the property tax rolls.

The ownership breakdown chart on this dashboard shows visually how much of the county's
timber resource sits in this SRS-dependent category versus on the local tax rolls.
            """
        )

    with st.expander("Does the county actually collect taxes on the \"taxable\" timber land?"):
        st.markdown(
            """
**Yes, but at reduced rates.**

Washington State has a **Designated Forest Land (DFL)** program under RCW 84.33 that allows
owners of commercial timberland to have their land assessed at **current-use value** rather
than market value. This can reduce assessed value to a fraction of what the land would be
worth at market, significantly limiting what the county collects in property tax.

In practice, the ~4% of Skamania's forested plots on corporate or private land generates
real but modest local tax revenue — supplemented by a small excise tax on timber harvests
in lieu of the assessment gap.
            """
        )

    with st.expander("What does \"exclude wilderness & reserved areas\" do?"):
        st.markdown(
            """
Some National Forest land is designated as **wilderness** by Congress — areas where
commercial logging is permanently prohibited regardless of timber values.

Checking this box removes those plots from the map and volume calculations,
giving a picture of the timber that is at least *theoretically* available for management
(subject to all other federal plan requirements, ESA, etc.).

In Skamania County, about 135 of the 927 sample plots fall in reserved/wilderness areas —
roughly 15% of the federal plots.
            """
        )

    with st.expander("How accurate are the dollar value estimates?"):
        st.markdown(
            """
**They are rough benchmarks, not appraisals. Treat them as order-of-magnitude guidance.**

The price ranges shown are based on Pacific Northwest timber market data from roughly
2023–2025. Actual values depend on species mix, road access, market timing, harvest method,
and contract terms.

The purpose of showing dollar values here is to help commissioners and community members
understand the *relative* difference between size classes and market paths —
not to appraise specific timber sales. Any actual transaction would require a licensed
timber cruiser and formal appraisal.
            """
        )

    with st.expander("Why does the Biomass category show zero volume?"):
        st.markdown(
            """
This is a quirk of how the Forest Service measures trees.

The FIA program only records cubic foot volume for trees that meet a minimum merchantable size
(roughly 5" in diameter). For very small trees and saplings (the Biomass category, 0–5"),
the volume field is left blank. Calculating biomass from small trees requires a
different field protocol measuring weight, not board feet.

The Biomass tab shows where small trees *exist* (plot counts), but can't reliably show
how much material is there in volumetric terms.
            """
        )

    with st.expander("Can Skamania County actually sell this timber?"):
        st.markdown(
            """
**That depends on land ownership — and most of this forest isn't county-owned.**

The FIA data covers *all* forested land in Skamania County regardless of owner.
County government has direct authority only over county-owned parcels (a small fraction).

For timber on **National Forest land**: the county can advocate for and participate in
collaborative forest management, but the US Forest Service controls what gets harvested
and when — subject to its forest plan, ESA consultations, and public process.

For timber on **tribal land**: the county has no jurisdiction.

For **corporate and private timber**: the county's role is primarily through permitting
and tax assessment — not direct management.

This dashboard is best read as a picture of the *total resource base* — useful for
understanding economic potential, making the case for SRS reauthorization,
and supporting regional economic development conversations.
            """
        )

    with st.expander("Why don't stewardship contracts send money to county schools?"):
        st.markdown(
            """
**Because of how the money moves — not because the timber is worth less.**

Under a **traditional timber sale**, a purchaser pays the Forest Service for the timber.
Those payments become *gross receipts*, and under the 25% Fund formula (16 U.S.C. § 500),
25% of gross receipts flows to counties for roads and schools.

Under a **stewardship contract** (authorized permanently in 2014), the Forest Service
*trades* timber value against restoration work — thinning, road decommissioning, habitat
work — in a goods-for-services exchange. Because the timber value offsets the contractor's
service costs instead of being collected as receipts, there is little or nothing left to
distribute through the 25% Fund.

**Good Neighbor Authority (GNA)** sales work differently again: a state agency (in Washington,
DNR) administers work on federal land, and receipts are retained to fund further restoration
under the agreement — not distributed to counties.

This is the mechanical reason the "what share of the program is traditional sales?" question,
pressed by commissioners at the June 16 and June 30, 2026 meetings, is a schools-funding
question and not just a forestry preference. Stewardship work has genuine forest-health value —
the tradeoff is real on both sides. But a forest program can grow substantially in acres and
board feet while county revenue stays flat, if the growth comes through vehicles that bypass
the 25% Fund.

*The mix table in the Federal Revenue Scenario tab quantifies this for the Gifford Pinchot's
stated program levels.*
            """
        )

    with st.expander("What is the National Scenic Area Act argument commissioners are raising?"):
        st.markdown(
            """
**The claim:** when Congress created the Columbia River Gorge National Scenic Area in 1986
(P.L. 99-663), it removed land from the timber base and the county tax rolls. Commissioners
argue the Act contemplated that the **Gifford Pinchot and Mount Hood National Forests would
offset that loss** — making today's low traditional-sale volumes not just an economic
disappointment but a departure from the bargain struck when the Scenic Area was created.

This argument surfaced in the June 2026 Forest Service exchanges and connects to the same
tax-base math behind the county's May 2026 confrontation with Friends of the Columbia Gorge.

**What this dashboard can and can't say about it:** the fiscal premise is verifiable — the
Scenic Area did remove land from the tax rolls, and this dashboard documents how little of
the county's timber base generates local revenue. Whether the Act creates an *obligation*
on the two forests, and what kind, is a legal question about specific statutory text that
this dashboard does not settle. Anyone using this argument in a formal setting should have
the specific provision in hand — it is a citation-checkable claim, and it will be checked.

*Status: argument as presented in the June 2026 meeting record. The statutory basis has not
been independently verified for this dashboard.*
            """
        )

    with st.expander("What does this dashboard NOT show? — Honest limitations"):
        st.markdown(
            f"""
This dashboard was built to inform policy conversations, not to advocate for a single outcome.
Here is what it does **not** capture — and what a complete analysis would need to include.

---

**📅 The data spans {meta.get('invyr_min','?')}–{meta.get('invyr_max','?')}, not a single point in time**

FIA plots are revisited on a ~10-year rotating cycle. This dashboard includes all available
measurements without filtering to the current evaluation period. Volume figures may overstate
current standing inventory by 30–50%. A rigorous analysis would filter to EVALID 532201
(2012–2022 measurements only) and apply post-stratification weights.

---

**🌲 Gross volume, not net merchantable**

`VOLCFGRS` is the gross cubic foot volume of the entire stem — including defect, decay, and
breakage that a mill cannot use. Actual harvestable volume is 10–25% lower. The 21"+ size class
is most affected, as older trees often carry significant defect.

---

**💸 Alternative revenue strategies for Skamania County**

Active timber harvest is one path to county fiscal sustainability. This dashboard does not show:

- **Conservation easements** — landowners can receive payment to restrict development; the county
  benefits through maintained land use and some property tax continuity
- **Forest carbon markets** — Washington's Forest Carbon Initiative and voluntary carbon markets
  allow landowners (including potentially coordinated county/USFS agreements) to receive payment
  for carbon sequestration in lieu of harvest
- **Recreation economy** — the Gifford Pinchot attracts hikers, hunters, climbers, and river
  users. A detailed recreation economy analysis would show jobs and tax revenue from this sector
- **Federal payment reform** — advocacy for structural SRS reform or expanded PILT formulas
  may be more durable than relying on harvest receipts that fluctuate with timber markets

A comprehensive county fiscal strategy would evaluate all of these alongside timber.

---

**🔥 The fuel treatment science is contested for this forest type**

The "thinning = fire risk reduction" argument is strongest in **dry ponderosa pine forests**
on the east side of the Cascades. The Gifford Pinchot is a **mesic Douglas-fir / western hemlock
forest** with a different fire history and ecology. In wet west-side forests:

- Natural fire return intervals are measured in centuries, not decades
- Thinning can dry the understory and increase wind penetration, potentially increasing fire spread
  in some stand conditions
- Bark beetle outbreaks (a key driver of fuel accumulation in dry forests) are less central here

This doesn't mean thinning has no role — it means the case needs to be made stand by stand with
USFS silviculturists, not assumed from county-wide inventory.

---

**🦉 Ecological constraints are not mapped here**

The map shows FIA plot locations and timber volume. It does **not** show:

- Northern Spotted Owl critical habitat and nest sites
- Marbled Murrelet nesting areas
- Bull trout and salmon-bearing stream buffers required under forest plan standards
- Slope/terrain constraints on harvest method (helicopter vs. ground-based)
- Roadless area designations

Any real harvest proposal would need to overlay all of these before identifying a workable
operating area. The harvestable fraction of the inventory shown here could be substantially
smaller than the total volumes suggest.

---

*This dashboard is a starting point for informed conversation, not a substitute for a formal
timber cruise, NEPA analysis, or economic feasibility study.*
            """
        )
