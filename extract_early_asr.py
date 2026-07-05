"""
extract_early_asr.py  — pull Skamania County SRS payment amounts from
FY2010–FY2012 USFS ASR 10-03 PDFs using pdfminer page-by-page extraction.

Skamania County has ~180,000 acres of Gifford Pinchot NF within its borders.
Payment amounts in range $500K–$5M are reasonable for county-level SRS.
"""

import sys
import re
import urllib.request
import io

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTLayoutContainer

PDFS = {
    2012: "https://www.fs.usda.gov/sites/default/files/2012-asr-10-03-report-stelprdb5407129.pdf",
    2011: "https://www.fs.usda.gov/sites/default/files/2011-asr-10-03-report-stelprdb5349603.pdf",
    2010: "https://www.fs.usda.gov/sites/default/files/2010-asr-10-03-report-stelprdb5251046.pdf",
}

# Skamania County Gifford Pinchot NF acres (from USFS land area data)
# Used to validate: payment / acres should be in a plausible $/acre range
SKAMANIA_MIN_ACRES = 150_000
SKAMANIA_MAX_ACRES = 250_000
PLAUSIBLE_DOLLAR_MIN = 300_000
PLAUSIBLE_DOLLAR_MAX = 6_000_000

DOLLAR_RE = re.compile(r'\$?\s*([\d,]+(?:\.\d{2})?)')


def fetch_pdf_bytes(url: str) -> bytes:
    print(f"  Fetching {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"    {len(data):,} bytes")
    return data


def extract_dollar_values(pdf_bytes: bytes) -> list[float]:
    """Return all dollar amounts from PDF that are in the plausible SRS range."""
    found = []
    pdf_file = io.BytesIO(pdf_bytes)
    for page_layout in extract_pages(pdf_file):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                text = element.get_text()
                for match in DOLLAR_RE.finditer(text):
                    raw = match.group(1).replace(",", "")
                    try:
                        val = float(raw)
                        if PLAUSIBLE_DOLLAR_MIN <= val <= PLAUSIBLE_DOLLAR_MAX:
                            found.append(val)
                    except ValueError:
                        pass
    return found


def find_skamania_in_text(pdf_bytes: bytes) -> list[tuple[str, float]]:
    """
    Extract text element-by-element; find elements containing 'Skamania'
    and look at nearby dollar-valued elements on the same page.
    Returns list of (context, amount) tuples.
    """
    results = []
    pdf_file = io.BytesIO(pdf_bytes)
    for page_num, page_layout in enumerate(extract_pages(pdf_file), start=1):
        # Gather all text elements with their x,y positions
        elements = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                text = element.get_text().strip()
                if text:
                    elements.append((element.x0, element.y0, element.x1, element.y1, text))

        # Check if 'Skamania' is on this page
        ska_elems = [(x0, y0, x1, y1, t) for x0, y0, x1, y1, t in elements
                     if 'skamania' in t.lower()]
        if not ska_elems:
            continue

        print(f"\n  [Page {page_num}] Found {len(ska_elems)} element(s) mentioning Skamania:")
        for x0, y0, x1, y1, t in ska_elems:
            print(f"    ({x0:.0f},{y0:.0f}) '{t[:80]}'")

        # Look for dollar amounts on the same page in reasonable range
        # In FIA-style tabular PDFs, the payment amount is typically to the right
        # or in a nearby row (similar y0 ±20 pts)
        for ska_x0, ska_y0, ska_x1, ska_y1, ska_t in ska_elems:
            # Find elements with similar vertical position (same table row)
            row_elems = [
                (x0, y0, t) for x0, y0, x1, y1, t in elements
                if abs(y0 - ska_y0) < 25
            ]
            print(f"    Row elements near y={ska_y0:.0f}:")
            for x0, y0, t in sorted(row_elems, key=lambda e: e[0]):
                print(f"      x={x0:.0f}  '{t[:60]}'")
                # Check for plausible dollar amount
                for match in DOLLAR_RE.finditer(t):
                    raw = match.group(1).replace(",", "")
                    try:
                        val = float(raw)
                        if PLAUSIBLE_DOLLAR_MIN <= val <= PLAUSIBLE_DOLLAR_MAX:
                            results.append((f"p{page_num}: {ska_t[:40]}", val))
                            print(f"        *** CANDIDATE: ${val:,.2f} ***")
                    except ValueError:
                        pass

    return results


def main():
    for fy, url in sorted(PDFS.items()):
        print(f"\n{'='*60}")
        print(f"FY{fy}")
        print(f"{'='*60}")
        try:
            pdf_bytes = fetch_pdf_bytes(url)
        except Exception as e:
            print(f"  ERROR fetching: {e}")
            continue

        results = find_skamania_in_text(pdf_bytes)

        if results:
            print(f"\n  SUMMARY for FY{fy}:")
            for ctx, val in results:
                print(f"    ${val:>14,.2f}  from: {ctx}")
        else:
            print(f"\n  No Skamania rows found in FY{fy}")
            # Fallback: print all plausible dollar values
            all_vals = extract_dollar_values(pdf_bytes)
            print(f"  All plausible dollar values ({len(all_vals)}):")
            for v in sorted(set(all_vals), reverse=True)[:20]:
                print(f"    ${v:>14,.2f}")


if __name__ == "__main__":
    main()
