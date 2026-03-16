![screenshot](./docs/assets/img/screenshot.png)

## Overview

> A web scrapping tool that allows you to collect data cards from the Wahapedia website.

Wahapedia data cards collector is a web scrapping tool that allows you to collect data cards from the [Wahapedia website](https://wahapedia.ru/). The tool is written in Python and uses the [Selenium](https://www.selenium.dev/) library to automate the process of collecting data cards.

## Getting Started

- [Overview](#overview)
- [Getting Started](#getting-started)
  - [Documentation](#documentation)
  - [Setting up](#setting-up)
    - [Prerequisites](#prerequisites)
    - [Install](#install)
    - [Build \& Run](#build--run)
    - [Usage](#usage)
  - [Future improvements](#future-improvements)
  - [Contributing](#contributing)
  - [License](#license)

### Documentation

Under the `src` directory, you will find the following files:

- `scraper.py`: Contains the `WebScraper` class that allows you to fetch the data cards from the Wahapedia website.
- `utils.py`: Contains the `Utils` class that adds functionalities functions to the web scraper.
- `__main__.py`: Contains the main function that allows you to run the tool using the command `python src`.

The code has been typed and documented inlined, so you can check the code for more information. You can also [open an issue](https://github.com/MorganKryze/Wahapedia-data-cards-collector/issues) regarding any inquiries you may have.

Once you setup the tool locally, an `/out` directory will be created. This directory will contain the following folders:

- `factions`: Contains the data cards fetched from the Wahapedia website.
- `source`: Contains the `index.json` file that lists all the factions and cards to fetch (and the `temp.json` when a job has not been completed).

### Setting up

#### Prerequisites

- Python 3.9 or higher
- Git
- Firefox

> [!NOTE]
> The tool uses Firefox as the default browser to run the web scrapping process. You can change the browser by modifying the `src/scraper.py` file:
>
> ```python
> # src/scraper.py
> 1 from selenium.webdriver import FirefoxOptions as Options, Firefox as Browser
> 2 ...
> ```

#### Install

Clone the repository:

```bash
git clone https://github.com/MorganKryze/Wahapedia-data-cards-collector.git
```

You may move to the project directory if you intend to run the tool:

```bash
cd Wahapedia-data-cards-collector
```

#### Build & Run

First we need to create a virtual environment:

```bash
python -m venv wahapedia
```

Then we need to activate the virtual environment:

```bash
source wahapedia/bin/activate
```

Then we need to install the dependencies:

```bash
pip install -r requirements.txt
```

Then we need to run the tool:

```bash
python src
```

#### Usage

The tool is only designed to:

- Create or update an index file (index.json) that lists all the factions and cards to fetch.
- Fetch the data cards from the Wahapedia website for all factions.
- Fetch the data cards from the Wahapedia website for a specific faction.
- Export a datasheet page into structured JSON that can be rendered in other formats.

> [!NOTE]
> The tool will create a `temp.json` file in the `/out/source` directory if a job has not been completed that will be used to resume the job. You can delete this file if you want to start a new job.

![demo](./docs/assets/img/demo.gif)

#### Exporting JSON

The screenshot captures are useful for archival, but Wahapedia datasheets are also present as HTML. The repository now includes a parser that exports those pages into JSON so you can build alternate renderers.

Export a single datasheet:

```bash
python scripts/export_datasheet_json.py \
  --url http://wahapedia.ru/wh40k10ed/factions/aeldari/Avatar-of-Khaine
```

Export every datasheet listed in an existing faction manifest:

```bash
python scripts/export_datasheet_json.py --output-slug aeldari
```

That writes per-card JSON files under `out/json/<faction>/` plus an `index.json` bundle for the faction.

You can also render a simple HTML example from one of those JSON files:

```bash
python scripts/render_card_html.py \
  --json out/json/aeldari/Avatar-of-Khaine.json
```

Validate exports across one or more manifests and write a report:

```bash
python scripts/validate_datasheet_exports.py --workers 6
```

That writes a report to `out/validation/datasheet-export-report.json` with per-faction failures and warning records.

#### Builder Catalogs And Static App

The repo can also derive roster-oriented builder catalogs from the exported datasheet JSON and serve a static army builder UI from `docs/builder/`.

Build the builder catalogs from the current `out/json` exports:

```bash
python scripts/build_builder_catalog.py --clean
```

Run the non-mutating regression check if you want to verify that catalog counts still match `out/json` and that the current warning baseline has not regressed:

```bash
python scripts/check_builder_regressions.py
```

That writes:

- `out/builder/manifest.json`
- `out/builder/catalogs/<faction>.json`
- `out/builder/reports/build-report.json`
- `docs/builder/data/manifest.json`
- `docs/builder/data/catalogs/<faction>.json`

The `docs/builder/data/` copy exists so the static app can work when only `docs/` is being hosted.

If you want a single wrapper that can refresh exports first and then rebuild the builder catalogs:

```bash
python scripts/build_builder_site.py --clean
```

You can optionally refresh one or more factions before building:

```bash
python scripts/build_builder_site.py \
  --export-output-slug aeldari \
  --export-output-slug adeptus-custodes \
  --clean
```

Serve the repo over HTTP and open the builder:

```bash
python -m http.server 8000
```

Then visit:

- `http://127.0.0.1:8000/docs/builder/index.html`

The builder reads `docs/builder/data/manifest.json`, lets you browse a faction catalog, add units to a roster, choose points/config options, total the roster, and print the rendered datacards.

The generated builder report currently tracks two quality buckets directly:

- units with missing exported stats
- units whose points/config labels could not be normalized confidently

`python scripts/check_builder_regressions.py` currently expects both counts to stay at `0`.

> [!IMPORTANT]
> Do not open `docs/builder/index.html` directly from disk with `file://`. The app uses `fetch`, so it must be served over HTTP.

### Future improvements

- Move to an api-based solution.

### Contributing

If you want to contribute to the project, you can follow the steps described in the [CONTRIBUTING](./.github/CONTRIBUTING) file.

### License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE) file for details.

> [!WARNING]
> This project does not aim to appropriate the content of the [Wahapedia website](https://wahapedia.ru/), but to provide a tool to collect public data cards for personal use only. The owner of this repository will not be held responsible for the use of the data collected by this tool.
