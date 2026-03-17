# Wahpedia Capture & Builder

## Project Overview
This project is a multi-stage toolkit for archiving and interacting with Warhammer 40,000 10th Edition data from [Wahapedia](https://wahapedia.ru/). It provides a pipeline from raw web scraping to a functional, static army builder web application.

## Core Components
1. **Scraper (`src/`):** A Selenium-based automation tool that handles cookie acceptance, page cleaning (removing ads/UI), and capturing high-quality screenshots of datasheets.
2. **Exporter (`scripts/export_datasheet_json.py`):** A robust parser using BeautifulSoup to extract structured data (stats, weapons, abilities, keywords) from Wahapedia HTML into JSON format.
3. **Builder Catalogs (`scripts/build_builder_catalog.py`):** A transformation layer that normalizes the raw JSON into builder-optimized catalogs. It handles complex points logic, wargear allocations, and unit composition.
4. **Army Builder (`docs/builder/`):** A static, client-side web application (HTML/JS) that consumes the generated catalogs. It features roster management, points totaling, and a printable datacard renderer.

## Tech Stack
- **Backend/Tooling:** Python 3.9+, Selenium, BeautifulSoup4, Requests.
- **Frontend:** Vanilla JavaScript (ES6), HTML5, CSS3.
- **Data Formats:** JSON (structured datasheets and builder catalogs).

## Key Workflows

### 1. Data Capture & Export
To fetch and convert data for a specific faction (e.g., `aeldari`):
```bash
# Export HTML datasheets to structured JSON
python scripts/export_datasheet_json.py --output-slug aeldari
```

### 2. Building the Army Builder Site
To refresh the catalogs used by the static app in `docs/builder/`:
```bash
# Rebuild all catalogs and the manifest
python scripts/build_builder_catalog.py --clean

# Or use the wrapper to export and build in one step
python scripts/build_builder_site.py --export-output-slug aeldari --clean
```

### 3. Verification & Testing
The project includes a regression suite to ensure parsing accuracy:
```bash
# Run catalog regression checks (validates stats, points, and wargear)
python scripts/check_builder_regressions.py

# Run backend tests
python -m pytest tests/
```

### 4. Running the Builder Locally
The builder must be served over HTTP due to CORS restrictions on `fetch`:
```bash
python -m http.server 8000
# Visit http://localhost:8000/docs/builder/
```

## Directory Structure
- `src/`: Selenium scraper implementation and utilities.
- `scripts/`: Data processing, export, and build scripts.
- `docs/builder/`: Source code for the static army builder application.
- `out/json/`: Raw structured data extracted from Wahapedia.
- `out/builder/`: Processed catalogs and reports used by the builder.
- `tests/`: Comprehensive test suite for both Python scripts and JavaScript frontend.

## Development Conventions
- **Data Normalization:** Heavy use of regex in `scripts/build_builder_catalog.py` to handle the variety of wargear and points formats on Wahapedia.
- **Testing:** New parsing logic should be accompanied by test cases in `tests/test_builder_catalog.py`.
- **Static Assets:** The `docs/builder/data/` directory contains a copy of the catalogs to allow the app to be hosted on GitHub Pages or similar static providers.
