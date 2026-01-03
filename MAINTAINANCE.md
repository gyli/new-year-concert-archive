## Files

- `index.html` - The complete single-page website (all HTML, CSS, and JavaScript)
- `data.json` - Concert data with years, conductors, and programme pieces
- `concert_ids.json` - Mapping of years to URL IDs for data fetching
- `fetch_nyc_info.py` - Script to fetch programme data from official website

## Data Fetching

To fetch and update data for a specific year:

```bash
python3 fetch_nyc_info.py <year>
```

For example:
```bash
python3 fetch_nyc_info.py 2024
```

This script:
- Fetches concert data for the specified year from the Vienna Philharmonic website
- Displays piece and composer information
- Updates `data.json` with fetched data
- Saves year→URL ID mappings to `concert_ids.json`

Use `--no-update` flag to fetch and display data without updating `data.json`:
```bash
python3 fetch_nyc_info.py 2024 --no-update
```

## Data Format

The `data.json` file structure:

```json
{
  "concerts": [
    {
      "year": 2024,
      "conductor": "Conductor Name",
      "pieces": [
        {
          "name": "Piece Name",
          "composer": "Composer Name",
          "links": {
            "youtube": "https://www.youtube.com/watch?v=...",
            "amazon": "https://www.amazon.com/..."
          }
        }
      ]
    }
  ]
}
```
