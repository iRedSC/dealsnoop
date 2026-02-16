#!/usr/bin/env python3
"""
Debug utility for Facebook Marketplace listings.

Fetches listing HTML (like dealsnoop), dumps structure to files for analysis.
Use to debug element extraction issues (e.g. car listings putting location in title).

Usage:
  python scripts/debug_listings.py fetch <query> [--output-dir DIR] [--city CODE] [--limit N]
  python scripts/debug_listings.py search <pattern> [--in FILE]
  python scripts/debug_listings.py compare <dir1> <dir2>
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup
from selenium import webdriver

from dealsnoop.engines.base import get_browser


def _relaxed_validate_listing(link) -> tuple[bool, str | None]:
    """
    Validate listing link without cache (for debug - include all marketplace items).
    Returns (is_valid, listing_id or None).
    """
    img_tag = link.find("img")
    if img_tag is None:
        return False, None
    attrs = getattr(img_tag, "attrs", {})
    if "alt" not in attrs:
        return False, None

    href = link.get("href")
    if not isinstance(href, str):
        return False, None
    if "/marketplace/item/" not in href:
        return False, None
    match = re.search(r"/marketplace/item/(\d+)", href)
    if not match:
        return False, None
    return True, match.group(1)


def _extract_listing_data(link) -> dict:
    """Extract structured data from a listing link for dump."""
    text = "\n".join(link.stripped_strings)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    line_count = len(lines)
    title_candidate = lines[-2] if line_count >= 2 else (lines[-1] if lines else "")
    location_candidate = lines[-1] if lines else ""

    # Truncate HTML snippet for JSON (full HTML saved separately)
    html_str = str(link)
    html_snippet_preview = html_str[:500] + "..." if len(html_str) > 500 else html_str

    _, listing_id = _relaxed_validate_listing(link)
    href = link.get("href", "")

    return {
        "id": listing_id,
        "href": href,
        "line_count": line_count,
        "lines": lines,
        "title_candidate": title_candidate,
        "location_candidate": location_candidate,
        "html_snippet_preview": html_snippet_preview,
    }


def cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch marketplace listings and dump to files."""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    listings_dir = output_dir / "listings"
    listings_dir.mkdir(exist_ok=True)

    city_code = args.city
    query = args.query
    limit = args.limit
    sort = "creation_time_descend"

    url = (
        f"https://www.facebook.com/marketplace/{city_code}/search"
        f"?query={query}&sortBy={sort}&daysSinceListed=7&exact=false&radius_in_km=50"
    )

    print(f"Fetching: {url}")
    browser = get_browser()
    try:
        browser.get(url)
        time.sleep(3)  # Allow JS to render

        html = browser.page_source
        full_html_path = output_dir / "full_page.html"
        full_html_path.write_text(html, encoding="utf-8")
        print(f"Saved full HTML to {full_html_path}")

        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a")
        print(f"Found {len(all_links)} total anchor tags")

        listings_data = []
        seen_ids = set()
        count = 0

        for link in all_links:
            if count >= limit:
                break
            valid, listing_id = _relaxed_validate_listing(link)
            if not valid or not listing_id or listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            data = _extract_listing_data(link)
            listings_data.append(data)

            # Save individual listing HTML
            listing_html_path = listings_dir / f"listing_{listing_id}.html"
            listing_html_path.write_text(str(link), encoding="utf-8")

            count += 1
            print(f"  [{count}] id={listing_id} lines={data['line_count']} "
                  f"title_candidate={data['title_candidate'][:40]!r}...")

        dump_path = output_dir / "listings_dump.json"
        dump_path.write_text(
            json.dumps(listings_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nSaved {len(listings_data)} listings to {dump_path}")
        return 0
    finally:
        browser.quit()


def cmd_search(args: argparse.Namespace) -> int:
    """Search for pattern in dumped JSON or HTML files."""
    pattern = re.compile(args.pattern, re.IGNORECASE)
    search_path = Path(args.in_file) if args.in_file else Path(".")
    if not search_path.exists():
        print(f"Error: path {search_path} does not exist", file=sys.stderr)
        return 1

    matches = []
    if search_path.is_file():
        files = [search_path]
    else:
        files = list(search_path.rglob("*.json")) + list(search_path.rglob("*.html"))

    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    matches.append((str(f), i, line.strip()[:120]))
        except Exception as e:
            print(f"Warning: could not read {f}: {e}", file=sys.stderr)

    for path, line_no, content in matches:
        print(f"{path}:{line_no}: {content}")
    print(f"\nFound {len(matches)} matches")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two listing dump directories."""
    dir1 = Path(args.dir1)
    dir2 = Path(args.dir2)
    dump1 = dir1 / "listings_dump.json"
    dump2 = dir2 / "listings_dump.json"

    if not dump1.exists():
        print(f"Error: {dump1} not found", file=sys.stderr)
        return 1
    if not dump2.exists():
        print(f"Error: {dump2} not found", file=sys.stderr)
        return 1

    data1 = json.loads(dump1.read_text(encoding="utf-8"))
    data2 = json.loads(dump2.read_text(encoding="utf-8"))

    def stats(data: list) -> dict:
        line_counts = [d["line_count"] for d in data]
        return {
            "count": len(data),
            "line_count_min": min(line_counts) if line_counts else 0,
            "line_count_max": max(line_counts) if line_counts else 0,
            "line_count_avg": sum(line_counts) / len(line_counts) if line_counts else 0,
            "sample_lines": [d["lines"] for d in data[:3]],
        }

    s1 = stats(data1)
    s2 = stats(data2)

    print(f"=== {dir1} vs {dir2} ===\n")
    print(f"{dir1.name}: {s1['count']} listings, "
          f"lines per listing: min={s1['line_count_min']} max={s1['line_count_max']} "
          f"avg={s1['line_count_avg']:.1f}")
    print(f"{dir2.name}: {s2['count']} listings, "
          f"lines per listing: min={s2['line_count_min']} max={s2['line_count_max']} "
          f"avg={s2['line_count_avg']:.1f}")

    print("\n--- Sample structure (first 3 listings) ---")
    print(f"\n{dir1.name}:")
    for i, sample in enumerate(s1["sample_lines"], 1):
        print(f"  Listing {i}: {sample}")
    print(f"\n{dir2.name}:")
    for i, sample in enumerate(s2["sample_lines"], 1):
        print(f"  Listing {i}: {sample}")

    print("\n--- Current heuristic (title=lines[-2], location=lines[-1]) ---")
    for label, data in [(dir1.name, data1), (dir2.name, data2)]:
        print(f"\n{label}:")
        for d in data[:3]:
            print(f"  id={d['id']}: title={d['title_candidate'][:50]!r} "
                  f"location={d['location_candidate'][:40]!r}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Debug utility for Facebook Marketplace listing structure"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch listings and dump to files")
    p_fetch.add_argument("query", help="Search query (e.g. 'Honda Civic' or 'mountain bike')")
    p_fetch.add_argument("--output-dir", "-o", default="debug_output", help="Output directory")
    p_fetch.add_argument(
        "--city",
        "-c",
        default="107976589222439",
        help="City code (default: Harrisburg, PA)",
    )
    p_fetch.add_argument("--limit", "-n", type=int, default=10, help="Max listings to extract")
    p_fetch.set_defaults(func=cmd_fetch)

    # search
    p_search = subparsers.add_parser("search", help="Search for pattern in dump files")
    p_search.add_argument("pattern", help="Regex pattern to search")
    p_search.add_argument(
        "--in",
        dest="in_file",
        default=None,
        help="File or directory to search (default: current dir)",
    )
    p_search.set_defaults(func=cmd_search)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare two listing dump directories")
    p_compare.add_argument("dir1", help="First output directory (e.g. debug_cars)")
    p_compare.add_argument("dir2", help="Second output directory (e.g. debug_bikes)")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
