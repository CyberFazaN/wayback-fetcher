# WayBack File Fetcher
CLI tool for discovering and downloading files from the WayBack Machine archive. 

[Русская версия README](https://github.com/CyberFazaN/wayback-fetcher/blob/main/README-RU.md)

# Description

WayBack File Fetcher is a command-line utility for discovering and downloading files and indexes from the WayBack Machine archive for a given domain, with flexible filtering options.  

## Features

- Retrieve and save archive indices for a chosen domain using the WayBack Machine CDX API.
- Filter results by file extension, MIME type, HTTP status, and/or regular expression.
- Download the first, last, and/or current (live) version of each file.
- Save metadata in CSV and/or JSON formats, and choose between flat or structured directory output.
- Multithreaded downloading (configurable thread count).
- Localization support (English and Russian).

## Installation

### Poetry

1. **Clone the repository:**
   
   ```bash
   git clone https://github.com/CyberFazaN/wayback-fetcher.git
   cd wayback-fetcher
   ```
   
2. **Create a virtual environment and install dependencies:**
   
   ```bash
   poetry install
   ```
   
3. **(Optional) Activate the virtual environment:**
   ```bash
   poetry env activate
   ```

### CLI Usage

Make sure your `pyproject.toml` includes this section to register the CLI command:
```toml
[tool.poetry.scripts]
wayback-fetcher = "wayback_fetcher:main"
```

You can then run the script as:
```bash
poetry run wayback-fetcher [arguments]
```

### Running Outside of the Poetry Environment

This script is expected to work correctly with **Python 3.8 or higher** (tested on Python 3.13+) and requires the `httpx` module to be installed in your environment.

You can run the script directly as follows:

```bash
python wayback_fetcher.py [arguments]
# Or directly
./wayback_fetcher.py [arguments]
```

If you have installed the dependencies using Poetry, you can also invoke the script using the Python interpreter from the virtual environment  created by Poetry:

```bash
/path/to/wayback_fetcher_directory/.venv/bin/python /path/to/wayback_fetcher_directory/wayback_fetcher.py [arguments]
```



## Quick Start

```bash
poetry run wayback-fetcher example.com -e pdf,jpg --download-firstlast --threads 4
```

## Command-line Arguments

| Argument                             | Long/Type                 | Description                                                  |
| ------------------------------------ | ------------------------- | ------------------------------------------------------------ |
| `domain`                             | str                       | Target domain (e.g. `example.com`).                          |
| `-l`, `--limit`                      | int (default: 150000)     | Maximum number of records to fetch from the WayBack Machine API. |
| `-http`, `--http`                    | (flag)                    | Use HTTP instead of HTTPS for archive requests.              |
| `-o`, `--output-folder`              | str                       | Directory to save results. Default: `output/<domain>_<date>`. |
| `-of`, `--output-format`             | csv, json, both (default) | Output format for metadata files (can choose both).          |
| `-v`, `--verbose`                    | (flag)                    | Enable verbose (DEBUG) output.                               |
| **Filtering:**                       |                           |                                                              |
| `-e`, `--extensions`                 | str                       | Comma-separated list of file extensions (e.g. `.pdf,.jpg` or `pdf,jpg`). |
| `-m`, `--mimetypes`                  | str                       | Comma-separated list of file MIME types.                     |
| `-r`, `--regex`                      | str                       | Regular expression for filtering file by their URL-paths.    |
| `-sc`, `--statuscodes`               | str (default: 200)        | Comma-separated list of HTTP status codes for archive filter. |
| **Download options:**                |                           |                                                              |
| `-dw`, `--download`                  | (flag)                    | Download all matching files (alias for `-dfl -dc`).          |
| `-df`, `--download-first`            | (flag)                    | Download the first archived version of each file.            |
| `-dl`, `--download-last`             | (flag)                    | Download the last archived version of each file.             |
| `-dfl`, `--download-firstlast`       | (flag)                    | Download both first and last versions (avoids duplicates).   |
| `-dc`, `--download-current`          | (flag)                    | Download the current version of the file from the live site. |
| `-s`, `--structured`                 | (flag)                    | Save files in a structured (site-like) directory tree (default: all files in one directory). |
| `-t`, `--threads`                    | int (1–64, default: 1)    | Number of threads for downloading.                           |
| `-dt`, `--download-timeout`          | int                       | Timeout for all downloads (seconds, applies to both archive and origin). |
| `-dtw`, `--download-timeout-wayback` | int (default: 120)        | Timeout for archive downloads (seconds).                     |
| `-dto`, `--download-timeout-origin`  | int (default: 60)         | Timeout for downloads from the original site (seconds).      |
| `-dr`, `--download-retries`          | int (default: 2)          | Number of retries for failed downloads.                      |
| `-drd`, `--download-retries-delay`   | int (default: 5)          | Delay between retries (seconds).                             |
| `-dd`, `--deduplicate`               | (flag)                    | Deduplicate downloaded files (the latest copy will survive). |
| **Localization:**                    |                           |                                                              |
| `-ru`, `--russian`                   | (flag)                    | Force Russian interface output.                              |
| `-en`, `--english`                   | (flag)                    | Force English interface output.                              |

---

## Filtering Logic

WayBack File Fetcher supports several filtering options to narrow down the set of files to be indexed and downloaded:

| `-sc`, `--statuscodes` | A comma-separated list of HTTP status codes (default: `200`). |
| ---------------------- | ------------------------------------------------------------ |
| `-e`, `--extensions`   | A comma-separated list of file extensions (e.g., `.pdf,.jpg` or `pdf,jpg`). |
| `-m`, `--mimetypes`    | A comma-separated list of file MIME types (e.g., `application/pdf,image/jpeg`). |
| `-r`, `--regex`        | A regular expression to match against the file path.         |


The **statuscodes** filter is **applied first** at the indexing stage: only archive records with a response code  matching one of the specified status codes are considered for further  processing.

A record passes the filtering if **its status code matches** one of the specified codes **and** at least one of the following conditions is true:

- Its file extension is in the list of allowed extensions; **or**
- Its MIME type matches one of the specified types; **or**
- Its path matches the given regular expression (the expression is evaluated using `re.search` on the URL path portion, e.g., `/test/files/mydoc.pdf` in `https://example.com/test/files/mydoc.pdf`).

In summary, the overall filtering logic is:

```python
status_code in allowed_status_codes
    and (
        file_extension in allowed_extensions
        or mime_type in allowed_mimetypes
        or regex matches url_path
    )
```

If none of the extension, MIME type, or regex filters are specified, the `targets` file containing filtered results will **not** be created in the output directory. If any download option is enabled, all records matching the status code filter will be treated as download targets (after user confirmation).

## Usage Examples

**Download all PDF and JPEG files from a site:**
```bash
poetry run wayback-fetcher example.com -e pdf,jpg --download-firstlast
```

**Download only current (live) JS files:**
```bash
poetry run wayback-fetcher example.com -e js --download-current
```

**Download all XML files by MIMEType, save metadata as JSON only:**
```bash
poetry run wayback-fetcher example.com -e "application/xml,text/xml" -of json --download
```

**Download all files matching regex `/backup/.*zip$`:**
```bash
poetry run wayback-fetcher example.com -r '/backup/.*zip$' --download
```

---

## Output Files

- **full-index** — All records returned by the WayBack Machine API (filtered by HTTP Status Codes).
- **targets** — Only records matching your filters.
- **multiple-versions** — Records with two or more unique file copies in the archive.
- **unsuccessful-downloads** — Files that failed to download.
- **files** — Directory containing successfully downloaded files.

Results can be saved in CSV, JSON, or both formats as specified by `-of`.

---

## Localization

The script’s language is determined by system locale, or can be forced with `-ru` or `-en`.

---

## License

MIT License (see LICENSE)

---

## Author

FazaN — [https://t.me/CyberFazaN](https://t.me/CyberFazaN)
