# Screem Printer Crawler

A powerful Python script powered by **Playwright** that crawls a given website, discovers all its internal pages, and captures full-page screenshots across multiple viewport resolutions. It is designed to quickly verify the responsiveness, visual presentation, and layout of web applications.

## Features

- **Concurrent Crawling**: Leverages an asynchronous producer-consumer architecture to process multiple pages in parallel.
- **SPA Support**: Intelligently handles Single Page Application routes by properly preserving hash-based navigation paths (e.g., `#/about`).
- **Configurable Resolutions**: Easily define custom screen sizes (Mobile, Tablet, Desktop, Ultrawide, etc.) via `config.json`.
- **Organized Output**: Screenshots are neatly organized into folders named after the pages, with the images named by the resolution.
- **Auto-Backups**: Automatically renames the previous `screenshots/` directory on every new execution to avoid losing past test results.
- **CLI & Interactive Mode**: Run it with command-line arguments or via a guided interactive prompt.
- **Rate Limiting Protection**: Built-in delays to prevent IP bans or server overload.

## Prerequisites

- Python 3.8+

## Installation

1. Clone this repository or download the files.
2. (Optional but recommended) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install the Playwright Chromium browser:
   ```bash
   playwright install chromium
   ```

## Usage

### Interactive Mode
Simply run the script without any arguments:
```bash
python screenshot_crawler.py
```
It will prompt you for the target URL and the maximum number of pages to crawl.

### CLI Mode
You can also run it directly passing the arguments:
```bash
python screenshot_crawler.py -u https://example.com -m 50
```

- `-u`, `--url`: The target website URL.
- `-m`, `--max-pages`: Maximum number of internal pages to visit (overrides `config.json`).
- `-i`, `--interactive`: Force interactive mode.

## Configuration

All configuration is stored in `config.json`:
- `max_pages`: Default limit of pages to crawl.
- `max_concurrent_pages`: Number of browser instances to run in parallel.
- `delay_between_pages_seconds`: Delay between page visits.
- `delay_between_resolutions_ms`: Delay to allow CSS animations/SPA rendering before taking a screenshot.
- `resolutions`: An array of devices and screen sizes to test.

## Output

The script generates a `screenshots/` directory containing subfolders for each discovered page. Inside each subfolder, you'll find the full-page screenshots for every configured resolution.
