# Open Gorge: Skamania Feedstock Inventory Dashboard

An interactive public-education dashboard on Skamania County's forest resource base and the
fiscal questions surrounding it: USDA Forest Inventory & Analysis (FIA) timber inventory by
size class and ownership, Secure Rural Schools / 25% Fund payment history, the traditional-sale
vs. stewardship contract revenue question, the Portside Terminal 2 mass-timber market
opportunity, and Washington's Type Np stream buffer rule.

Built to support better-quality conversations between county commissioners, the Forest Service,
school districts, landowners, and residents — real numbers with stated assumptions and
uncertainty, in place of competing generalizations.

A project of [SkamaniaDispatch](https://github.com/kate-rose/skamania-dispatch) / Open Gorge.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Then open http://localhost:8501.

The app reads `skamania_feedstock.json` (checked in, ~680KB) — no raw data download needed.

## Regenerate the data (optional)

`process_fia.py` rebuilds `skamania_feedstock.json` from the USDA FIA Datamart Washington
state CSV export. Download `WA_CSV.zip` from the [FIA Datamart](https://apps.fs.usda.gov/fia/datamart/datamart.html),
extract `WA_PLOT.csv`, `WA_TREE.csv`, and `WA_COND.csv` into `extracted/`, then:

```bash
.venv/bin/python process_fia.py
```

`extract_early_asr.py` documents how the FY2010–2012 county payment figures were extracted
from archived USFS ASR-10-03 PDF reports.

## Data sources

| Source | Used for |
|---|---|
| USDA FS FIA Datamart (WA_CSV) | Plot-level timber inventory, ownership, size classes |
| USFS ASR-10-03 Final Payment Detail Reports (FY2010–FY2025) | SRS / 25% Fund payment history |
| WA DNR FP Hydro REST API | Stream classification miles (Skamania bounding box) |
| WA Forest Practices Board Type Np Rule CBA (IEc, April 2025) | Buffer rule per-mile cost/benefit figures |
| Skamania BOCC meeting record (June 16 & 30, 2026) | GP program figures — marked *pending written confirmation* in-app |

## Honest limitations

The dashboard states its limitations in-app (see the FAQ tab and the Expert Methodology
expander): multi-cycle FIA data may overstate current inventory by 30–50%; volumes are gross,
not net merchantable; price ranges are regional benchmarks, not appraisals; meeting-record
figures are flagged pending written confirmation. It is a conversation-support tool,
not a budget forecast.
