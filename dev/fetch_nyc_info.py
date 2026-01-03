#!/usr/bin/env python3
"""
Script to fetch New Year's Concert data for a specific year.
Given a year, returns piece and composer info and updates data.json.
"""

import json
import re
import subprocess
import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def quick_check_url(url):
    """check if URL exists - but be lenient to not miss valid pages."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '1', '--head', '--silent', url],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        # Be lenient - accept if we get any response (some pages might redirect)
        return len(result.stdout) > 50
    except Exception:
        return True  # If check fails, try fetching anyway

def fetch_html_fast(url):
    """Fetch HTML with minimal timeout."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '3', '--fail', '--silent', url],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=4
        )
        if result.returncode == 0 and len(result.stdout) > 500:
            return result.stdout
        return None
    except Exception:
        return None

def is_new_years_concert_page(html):
    """Fast check if page is New Year's Concert."""
    if not html or len(html) < 500:
        return False

    # Quick checks first (most common patterns)
    html_lower = html.lower()
    if 'new year' not in html_lower or 'concert' not in html_lower:
        return False

    # Check for January 1st pattern
    if not re.search(r'january\s+1[,\s]+\d{4}', html, re.IGNORECASE):
        return False

    return True

def parse_concert_page(html_content):
    """Parse concert page - optimized."""
    if not html_content:
        return None

    # Extract year (try most common pattern first)
    year = None
    year_match = re.search(r'monday, january 1, (\d{4})', html_content, re.IGNORECASE)
    if year_match:
        year = int(year_match.group(1))
    else:
        year_match = re.search(r'january 1[,\s]+(\d{4})', html_content, re.IGNORECASE)
        if year_match:
            year = int(year_match.group(1))

    if not year:
        return None

    # Extract conductor - try multiple patterns for different page formats
    conductor = None

    # Pattern 1: Modern format <h3>CONDUCTOR</h3><p>...</p>
    conductor_match = re.search(r'<h3>conductor</h3>\s*<p>([^<]+)</p>', html_content, re.IGNORECASE)
    if conductor_match:
        conductor = conductor_match.group(1).strip()

    # Pattern 2: data-conductor attribute
    if not conductor:
        conductor_match = re.search(r'data-conductor="([^"]+)"', html_content, re.IGNORECASE)
        if conductor_match:
            conductor = conductor_match.group(1).strip()

    # Pattern 3: Older format <span class="subhead">Conductor</span> followed by conductor name
    if not conductor:
        conductor_match = re.search(
            r'<span[^>]*class="[^"]*subhead[^"]*"[^>]*>conductor</span>\s*<span[^>]*>([^<]+)</span>',
            html_content,
            re.IGNORECASE | re.DOTALL
        )
        if conductor_match:
            conductor = conductor_match.group(1).strip()

    # Pattern 4: Alternative span format
    if not conductor:
        conductor_match = re.search(r'conductor[:\s]*</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
        if conductor_match:
            conductor = conductor_match.group(1).strip()

    if not conductor:
        return None

    # Extract composers list
    composers_match = re.search(r'data-composers="([^"]+)"', html_content)
    composers_list = []
    if composers_match:
        composers_str = composers_match.group(1)
        composers_list = [c.strip() for c in composers_str.split(';') if c.strip()]

    # Extract programme pieces
    pieces = []
    programme_spans = re.findall(
        r'<span[^>]*cast-programm[^>]*>\s*<em>([^<]+)</em>',
        html_content,
        re.IGNORECASE
    )

    def clean_html(text):
        return text.replace('&quot;', '"').replace('&amp;', '&').replace('&#39;', "'").strip()

    for i, piece_name in enumerate(programme_spans):
        piece_name = clean_html(piece_name)
        if piece_name and len(piece_name) > 2:
            composer = composers_list[i] if i < len(composers_list) else "Unknown"
            pieces.append({
                "name": piece_name,
                "composer": composer,
                "links": {}
            })

    if not pieces:
        return None

    return {
        "year": year,
        "conductor": conductor,
        "pieces": pieces
    }

def check_concert_id(concert_id):
    """Check a single concert ID - optimized."""
    url = f"https://www.wienerphilharmoniker.at/en/konzerte/new-years-concert/{concert_id}/"

    # Fetch page directly (parallel processing makes this efficient)
    html = fetch_html_fast(url)
    if not html:
        return None

    # Quick check if it's a New Year's Concert page
    if not is_new_years_concert_page(html):
        return None

    # Parse the page
    data = parse_concert_page(html)
    if data and data.get('pieces'):
        return (concert_id, data)

    return None

def scan_range_parallel(start_id, end_id, max_workers=50, batch_size=500, id_mappings=None):
    """Scan range in parallel with batching."""
    if id_mappings is None:
        id_mappings = {}

    found = {}
    total = end_id - start_id + 1
    tested = 0
    start_time = time.time()

    print(f"Scanning IDs {start_id} to {end_id} ({total} IDs) with {max_workers} workers")

    # Process in batches to show progress
    for batch_start in range(start_id, end_id + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, end_id)
        batch_ids = range(batch_start, batch_end + 1)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {executor.submit(check_concert_id, cid): cid for cid in batch_ids}

            for future in as_completed(future_to_id):
                tested += 1

                if tested % 200 == 0:
                    elapsed = time.time() - start_time
                    rate = tested / elapsed if elapsed > 0 else 0
                    eta = (total - tested) / rate if rate > 0 else 0
                    print(f"Progress: {tested}/{total} ({tested*100//total}%) | "
                          f"Found: {len(found)} | Rate: {rate:.1f}/s | ETA: {eta:.0f}s")

                try:
                    result = future.result(timeout=1)
                    if result:
                        concert_id, data = result
                        year = data['year']
                        if year not in found:
                            found[year] = data
                            id_mappings[str(year)] = concert_id
                            print(f"✓ Found: {year} (ID {concert_id}) - "
                                  f"{len(data['pieces'])} pieces - {data['conductor']}")
                except Exception:
                    pass

    return found

def find_concert_id_by_year(year, id_mappings):
    """Find concert ID for a given year, searching if not in mappings."""
    year_str = str(year)

    # First check if we have it in mappings
    if year_str in id_mappings:
        return id_mappings[year_str]

    # If not found, try to find it by scanning a reasonable range
    print(f"Concert ID not found in mappings for year {year}. Searching...")

    # Estimate ID range based on year (rough approximation)
    # Recent years (2010+) tend to be in 2000-11000 range
    if year >= 2010:
        search_start = 2000
        search_end = 11000
    elif year >= 2000:
        search_start = 2000
        search_end = 6000
    else:
        search_start = 4000
        search_end = 8000

    # Scan in parallel to find the ID
    found_id = None
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_id = {executor.submit(check_concert_id, cid): cid
                        for cid in range(search_start, search_end + 1)}

        for future in as_completed(future_to_id):
            if found_id:
                future.cancel()
                continue
            try:
                result = future.result(timeout=1)
                if result:
                    concert_id, data = result
                    if data['year'] == year:
                        print(f"Found concert ID {concert_id} for year {year}")
                        found_id = concert_id
                        # Cancel remaining futures
                        for f in future_to_id:
                            if f != future:
                                f.cancel()
                        break
            except Exception:
                pass

    return found_id

def fetch_year_data(year):
    """Fetch concert data for a specific year."""
    print(f"Fetching data for year {year}...")

    # Load existing mappings
    try:
        with open('concert_ids.json', 'r', encoding='utf-8') as f:
            mappings_data = json.load(f)
            id_mappings = mappings_data.get('mappings', {})
    except FileNotFoundError:
        id_mappings = {}

    # Find or search for concert ID
    concert_id = find_concert_id_by_year(year, id_mappings)

    if not concert_id:
        print(f"Error: Could not find concert ID for year {year}", file=sys.stderr)
        return None

    # Fetch the concert data
    result = check_concert_id(concert_id)
    if not result:
        print(f"Error: Could not fetch data for year {year} (ID: {concert_id})", file=sys.stderr)
        return None

    _, data = result

    # Update mappings if needed
    year_str = str(year)
    if year_str not in id_mappings:
        id_mappings[year_str] = concert_id
        mappings_data = {
            "mappings": id_mappings,
            "last_updated": datetime.now().isoformat()
        }
        with open('concert_ids.json', 'w', encoding='utf-8') as f:
            json.dump(mappings_data, f, indent=2)
        print(f"Saved concert ID {concert_id} for year {year} to mappings")

    return data

def update_data_json(concert_data):
    """Update data.json with the fetched concert data."""
    year = concert_data['year']

    # Load existing data
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    except FileNotFoundError:
        existing_data = {"concerts": []}

    # Find if year already exists
    existing_years = {c['year']: i for i, c in enumerate(existing_data['concerts'])}

    if year in existing_years:
        idx = existing_years[year]
        existing_data['concerts'][idx]['conductor'] = concert_data.get('conductor')
        existing_data['concerts'][idx]['pieces'] = concert_data.get('pieces', [])
        print(f"Updated existing entry for year {year}")
    else:
        existing_data['concerts'].append(concert_data)
        print(f"Added new entry for year {year}")

    # Sort by year
    existing_data['concerts'].sort(key=lambda x: x['year'])

    # Save updated data
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

    print(f"Updated data.json with data for year {year}")

def print_concert_info(concert_data):
    """Print piece and composer information for a concert."""
    year = concert_data['year']
    conductor = concert_data.get('conductor', 'Unknown')
    pieces = concert_data.get('pieces', [])

    print(f"\n{'='*70}")
    print(f"New Year's Concert {year}")
    print(f"{'='*70}")
    print(f"Conductor: {conductor}")
    print(f"\nProgramme ({len(pieces)} pieces):")
    print("-" * 70)

    for i, piece in enumerate(pieces, 1):
        composer = piece.get('composer', 'Unknown')
        name = piece.get('name', 'Unknown')
        print(f"{i:2d}. {name}")
        print(f"    Composer: {composer}")

    print(f"{'='*70}\n")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Fetch New Year's Concert data for a specific year"
    )
    parser.add_argument(
        'year',
        type=int,
        help='Year of the New Year\'s Concert (e.g., 2024)'
    )
    parser.add_argument(
        '--no-update',
        action='store_true',
        help='Fetch and display data without updating data.json'
    )

    args = parser.parse_args()

    print("=" * 70)
    print(f"Fetching New Year's Concert data for year {args.year}")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch data for the specified year
    concert_data = fetch_year_data(args.year)

    if not concert_data:
        print(f"Error: Failed to fetch data for year {args.year}", file=sys.stderr)
        sys.exit(1)

    # Print the information
    print_concert_info(concert_data)

    # Update data.json unless --no-update flag is set
    if not args.no_update:
        update_data_json(concert_data)
        print(f"Successfully updated data.json with data for year {args.year}")
    else:
        print("Skipping data.json update (--no-update flag set)")

    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
