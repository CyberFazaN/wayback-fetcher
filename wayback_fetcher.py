#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import sys
import argparse
import locale
import os
import re
import json
import csv
import datetime
import time
import traceback
from types import FunctionType, MethodType
from collections import defaultdict
import urllib.parse
import concurrent.futures
import httpx
import gettext
import logging
from pprint import pformat

__author__ = "FazaN"

def get_logger(name=__name__):
    """
    Return a logger with the given name. If no logger with that name exists,
    create one. The logger will have a StreamHandler with a basic format string.
    If the logger already has handlers, do not add another one.
    """
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    if not logger.hasHandlers():
        logger.addHandler(handler)
    return logger

def format_exception(exc: Exception|None, with_traceback: bool = False, limit: int|None = None) -> str|None:
    if exc is None:
        return None
    if with_traceback:
        return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=limit))
    else:
        return f"{exc.__class__.__module__}.{exc.__class__.__qualname__}: {exc}"

def md5sum(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()

def get_lang() -> str:
    """
    Peek language flags in sys.argv before argparse and try to get system locale.
    """
    _force_ru = '-ru' in sys.argv or '--russian' in sys.argv
    _force_en = '-en' in sys.argv or '--english' in sys.argv
    _sysloc = locale.getlocale()[0] or ''
    if _force_ru and _force_en:
        print("Warning: cannot use both -ru and -en; defaulting to English.")
        return 'en'
    return 'ru' if (_force_ru or (not _force_en and _sysloc.lower().startswith('ru'))) else 'en'

def init_gettext(lang) -> gettext.NullTranslations:
    """
    Initialize gettext with the given language.

    Args:
        lang (str): The language code to use for translations.

    Returns:
        gettext.NullTranslations: The translation object to use for
        translating strings.
    """
    trans = gettext.translation('wayback_fetcher', localedir='locale', languages=[lang], fallback=True)
    return trans

def validate_domain(domain: str, _t: MethodType|FunctionType = lambda x: x) -> str:
    """
    Validate the given domain against the regex pattern for domain names.
    
    Args:
        domain (str): The domain to validate.
        _t (MethodType|FunctionType): A translation function for internationalization.
            Defaults to lambda x: x.
    
    Returns:
        str: The validated domain in lowercase.
    
    Raises:
        argparse.ArgumentTypeError: If the domain does not match the regex pattern.
    """
    pattern = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")
    if not pattern.match(domain):
        raise argparse.ArgumentTypeError(_t("Must be a valid domain: {domain}").format(domain=domain))
    return domain.lower()

def boolean_answer(answer: str, default: bool) -> bool:
    """
    Return a boolean value based on the given answer string.

    Args:
        answer (str): The answer string to evaluate.
        default (bool): The default value to return if the answer is empty.

    Returns:
        bool: The boolean value represented by the answer string.
    """
    if not answer:
        return default
    return answer.lower().startswith('y') or answer.lower().startswith('д')

def range_limited_int(minimum: int, maximum: int, _t: MethodType|FunctionType = lambda x: x) -> FunctionType:
    """
    Return a function that checks that an argument is an integer within a range.

    The returned function takes a single argument, `arg`, and returns an integer
    value. If `arg` is not an integer, an `ArgumentTypeError` is raised. If the integer value
    of `arg` is outside the range [minimum, maximum], an `ArgumentTypeError` is
    raised.

    Args:
        minimum (int): The minimum value of the range.
        maximum (int): The maximum value of the range.
        _t (MethodType|FunctionType): A translation function for
            internationalization. Defaults to lambda x: x.

    Returns:
        FunctionType: A function that takes an argument and returns an integer
            value if the argument is within the specified range, or raises an
            `ArgumentTypeError` if the argument is not an integer or is outside
            the specified range.
    """
    def checker(arg):
        try:
            value = int(arg)
        except ValueError:
            raise argparse.ArgumentTypeError(_t("Must be an integer"))
        if not (minimum <= value <= maximum):
            raise argparse.ArgumentTypeError(_t("Value must be between {minimum} and {maximum}").format(minimum=minimum, maximum=maximum))
        return value
    return checker

def parse_args(_t: MethodType|FunctionType = lambda x: x) -> argparse.Namespace:
    """
    Parse the command line arguments for the Wayback Fetcher script.

    This function returns an argparse.Namespace object containing the parsed
    command line arguments.

    Args:
        _t (MethodType|FunctionType): A translation function for
            internationalization. Defaults to lambda x: x.

    Returns:
        argparse.Namespace: The parsed command line arguments.

    Raises:
        SystemExit: If the domain is not specified.
    """
    _logger = get_logger()
    now = datetime.datetime.now().strftime("%d-%m-%Y_%H:%M:%S")
    default_output = os.path.join("output", f"<domain>_{now}")
    p = argparse.ArgumentParser(
        description=_t("Download files from WayBack Machine archive for a given domain with optional filtration.")
    )

    main_group = p.add_argument_group(_t("Main options"))
    main_group.add_argument(
        'domain', nargs='?', type=lambda d: validate_domain(d, _t),
        help=_t("Target domain (e.g. example.com).")
    )
    main_group.add_argument(
        '-l','--limit', type=int, default=150000,
        help=_t("Max records to fetch from API.")
    )
    main_group.add_argument(
        '-http', '--http', action='store_true',
        help=_t("Use HTTP instead of HTTPS for WayBack connection.")
    )
    main_group.add_argument(
        '-o','--output-folder', default=default_output,
        help=_t("Output folder. Default: {default_output}").format(default_output=default_output)
    )
    main_group.add_argument(
        '-of','--output-format', choices=['csv','json','both'], default='both',
        help=_t("Output format. Both means CSV+JSON.")
    )
    main_group.add_argument(
        '-v','--verbose', action='store_true',
        help=_t("Verbose mode.")
    )

    filter_group = p.add_argument_group(_t("Filtering options"))
    filter_group.add_argument(
        '-e','--extensions',
        help=_t("Comma-separated list of extensions.")
    )
    filter_group.add_argument(
        '-m','--mimetypes',
        help=_t("Comma-separated list of mimetypes.")
    )
    filter_group.add_argument(
        '-r', '--regex',
        help=_t("Regular expression for filtering file by their URL-paths.")
    )
    filter_group.add_argument(
        '-sc','--statuscodes', default='200',
        help=_t("Comma-separated list of HTTP status codes for archive filter.")
    )

    dl_group = p.add_argument_group(_t("Download options"))
    dl_group.add_argument(
        '-dw','--download', action='store_true',
        help=_t("Download all matching files. Alias for -dfl -dc.")
    )
    dl_group.add_argument(
        '-df','--download-first', action='store_true',
        help=_t("Download first archived file.")
    )
    dl_group.add_argument(
        '-dl','--download-last', action='store_true',
        help=_t("Download last archived file.")
    )
    dl_group.add_argument(
        '-dfl','--download-firstlast', action='store_true',
        help=_t("Download both first and last archived files.")
    )
    dl_group.add_argument(
        '-dc','--download-current', action='store_true',
        help=_t("Download current version of file from origin.")
    )
    dl_group.add_argument(
        '-s','--structured', action='store_true',
        help=_t("Save files in a structured way.")
    )
    dl_group.add_argument(
        '-t','--threads', type=range_limited_int(1, 64, _t), default=1,
        help=_t("Threads for downloading (1–64).")
    )
    dl_group.add_argument(
        '-dt','--download-timeout', type=int,
        help=_t("Timeout for all downloads. Alias for -dtw x -dto x.")
    )
    dl_group.add_argument(
        '-dtw','--download-timeout-wayback', type=int, default=120,
        help=_t("Timeout for wayback downloads.")
    )
    dl_group.add_argument(
        '-dto','--download-timeout-origin', type=int, default=60,
        help=_t("Timeout for origin downloads.")
    )
    dl_group.add_argument(
        '-dr','--download-retries', type=int, default=2,
        help=_t("Number of retries for failed downloads.")
    )
    dl_group.add_argument(
        '-drd','--download-retries-delay', type=int, default=5,
        help=_t("Delay between retries (seconds).")
    )
    dl_group.add_argument(
        '-dd','--deduplicate', action='store_true',
        help=_t("Deduplicate downloaded files (the latest copy will survive).")
    )

    lang_group = p.add_argument_group(_t("Localization"))
    lang_group.add_argument(
        '-ru', '--russian', action='store_true',
        help=_t("Force Russian output.")
    )
    lang_group.add_argument(
        '-en', '--english', action='store_true',
        help=_t("Force English output.")
    )

    args = p.parse_args()

    if args.verbose:
        _logger.setLevel(logging.DEBUG)
    args.statuscodes = [int(c) for c in args.statuscodes.split(",")]
    if not args.domain:
        _logger.critical(_t("Domain is required."))
        sys.exit(1)
    if args.download:
        args.download_first = True
        args.download_last = True
        args.download_current = True
    if args.download_firstlast:
        args.download_first = True
        args.download_last = True
    if args.download_timeout:
        args.download_timeout_wayback = args.download_timeout
        args.download_timeout_origin = args.download_timeout
    args.output_folder = os.path.join("output", f"{args.domain}_{now}")
    args.output_format = set([args.output_format] if args.output_format != 'both' else ['csv', 'json'])
    args.extensions = [e.strip().lower() if e.startswith('.') else '.' + e.strip().lower() for e in (args.extensions or '').split(',') if e.strip()]
    args.mimetypes = [m.strip().lower() for m in (args.mimetypes or '').split(',') if m.strip()]
    return args

def fetch_index(domain: str, limit: int, statuscodes: list[int], http: bool = False, _t: MethodType|FunctionType = lambda x: x) -> tuple[list[dict], list]:
    """Fetch the archive index from the Wayback Machine using the CDX API.

    Args:
        domain (str): The domain to fetch the archive index for.
        limit (int): The maximum number of records to fetch.
        statuscodes (list[int]): The HTTP status codes to filter the results by.
        _t (MethodType|FunctionType, optional): A translation function for internationalization. Defaults to lambda x: x.

    Returns:
        tuple[list[dict], list]: A tuple containing the list of records and the list of headers.
    """
    _logger = get_logger()
    api = f"{'http' if http else 'https'}://web.archive.org/cdx/search/cdx"
    
    params: dict = {
        "url": domain,
        "matchType": "prefix",
        "output": "json",
        "fl": "original,mimetype,timestamp,endtimestamp,groupcount,uniqcount",
        "collapse": "urlkey",
        "limit": str(limit),
    }
    if statuscodes:
        params['filter'] = [f"statuscode:{c}" for c in statuscodes]

    client = httpx.Client(timeout=120)
    print(_t("Fetching archive index..."))
    try:
        resp = client.get(api, params=params)
        resp.raise_for_status()
    except Exception as e:
        _logger.critical(_t('Error while fetching archive index ({exception})').format(exception=format_exception(e)))
        sys.exit(1)

    data = resp.json()
    headers = data[0] if data else []
    records = []
    for row in data[1:]:
        rec = dict(zip(headers, row))
        rec["groupcount"] = int(rec.get("groupcount", "0"))
        rec["uniqcount"]  = int(rec.get("uniqcount",  "0"))
        records.append(rec)
    return records, headers

def filter_records(records: list[dict], exts: list[str]|None = None, mtypes: list[str]|None = None, regex: str|None = None) -> tuple[list[dict], list[dict]]:
    """
    Filter the list of records based on the given criteria.

    Args:
        records (list[dict]): The list of records to filter.
        exts (list[str]|None, optional): The list of file extensions to filter by. Defaults to None.
        mtypes (list[str]|None, optional): The list of MIME types to filter by. Defaults to None.
        regex (str|None, optional): The regular expression to filter by. Defaults to None.

    Returns:
        tuple[list[dict], list[dict]]: A tuple containing the list of filtered records and the list of non-unique records.
    """
    if not exts and not mtypes and not regex:
        filtered = records
    else:
        filtered = []
        for r in records:
            path = urllib.parse.urlparse(r["original"]).path
            ext = os.path.splitext(path)[1].lower()
            mt  = r["mimetype"].lower()
            if (exts and ext and ext in exts) or (mtypes and mt and mt in mtypes) or (regex and re.search(regex, path)):
                filtered.append(r)
    nonuniq = [r for r in filtered if r["uniqcount"] >= 2]
    return filtered, nonuniq

def save_metadata(folder: str, name: str, headers: list[str], data: list[dict], formats: list[str]):
    """
    Save metadata to the specified folder in the given formats.

    Args:
        folder (str): The folder to save the metadata to.
        name (str): The base name of the file to save.
        headers (list[str]): The list of header names.
        data (list[dict]): The data (list of dictionaries) to save.
        formats (list[str]): The list of formats to save the data in. Currently, only 'csv' and 'json' are supported.

    Returns:
        None
    """
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, name)
    if 'csv' in formats:
        with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(data)
    if 'json' in formats:
        with open(f"{base}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def build_filepath(rec: dict, out_files: str, structured: bool, which: str) -> str:
    """
    Build the filepath for a given record.

    Args:
        rec (dict): A record with the "original" key containing the URL.
        out_files (str): The base output folder.
        structured (bool): Whether to use a structured output format.
        which (str): The filename suffix, e.g. 'first', 'last', 'current'.

    Returns:
        str: The filepath for the given record.
    """
    url_path = urllib.parse.urlparse(rec["original"]).path.lstrip("/")
    name, ext = os.path.splitext(url_path)
    suffix = f"-{which}"
    if structured:
        dirpath = os.path.join(out_files, os.path.dirname(url_path))
        os.makedirs(dirpath, exist_ok=True)
        filename = f"{os.path.basename(name)}{suffix}{ext}"
        return os.path.join(dirpath, filename)
    flat = name.replace("/", "_")
    filename = f"{flat}{suffix}{ext}"
    os.makedirs(out_files, exist_ok=True)
    return os.path.join(out_files, filename)

def extract_base_and_suffix(filepath: str) -> tuple[str, str]:
    """
    Extract the base filename and the timestamp suffix from a filepath.
    Valid filepath is /path/to/file-YYYYMMDDhhmmss.ext or /path/to/file-current.ext

    Args:
        filepath (str): The filepath to extract the base and suffix from.

    Returns:
        tuple[str, str]: A tuple containing the base filename and the suffix.
    """
    dirname = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    m = re.match(r"^(.*?)-((?:current)|(?:\d{14}))(\.\w+)?$", filename)
    if m:
        name = m.group(1)
        ext = m.group(3) or ''
        base = os.path.join(dirname, f"{name}{ext}") if name or ext else dirname
        suffix = m.group(2)
        return base, suffix
    return filepath, ""

def delete_files(files: list[str], _t: MethodType|FunctionType = lambda x: x) -> None:
    """
    Delete the given files.

    Args:
        files (list[str]): A list of filepaths to delete.
        _t (MethodType|FunctionType): A translation function for internationalization. Defaults to lambda x: x.

    Returns:
        None
    """
    _logger = get_logger()
    for f in files:
        _logger.debug(_t("Deleting: {filepath}").format(filepath=f))
        os.remove(f)

def find_duplicates(downloads: list[tuple[str, str|None, str|None, bool, str|None]], _t: MethodType|FunctionType = lambda x: x) -> list[str]:
    """
    Find duplicate files in a list of downloads based on MD5 sums, and return a list of files to delete (excluding most recent copy).

    Args:
        downloads (list[tuple[str, str|None, str|None, bool, str|None]]): A list of download records, where each record is a tuple of (url, filepath, md5sum, success, error).
        _t (MethodType|FunctionType): A translation function for internationalization. Defaults to lambda x: x.

    Returns:
        list[str]: A list of files to delete.
    """
    _logger = get_logger()
    groups = defaultdict(list)
    for _url, filepath, md5sum, _success, _error in downloads:
        if not filepath or not md5sum:
            continue
        base, suffix = extract_base_and_suffix(filepath)
        groups[(md5sum, base)].append((filepath, suffix))
    
    files_to_delete = []
    
    def freshness_score(suffix):
        if suffix == "current":
            return float('inf')
        elif suffix.isdigit():
            return int(suffix)
        else:
            return 0

    for _key, filelist in groups.items():
        if len(filelist) < 2:
            continue  # no duplicates
        # Sort by freshness (most recent copy first)
        filelist_sorted = sorted(filelist, key=lambda x: freshness_score(x[1]), reverse=True)
        latest = filelist_sorted[0][0]
        duplicates = [f[0] for f in filelist_sorted[1:]]
        _logger.debug(_t("File {latest} has {duplicates_count} duplicates: {duplicates}").format(latest=latest, duplicates_count=len(duplicates), duplicates=duplicates))
        files_to_delete.extend(duplicates)

    return files_to_delete

def download_file(url: str, filepath: str, timeout: int, retries: int = 1, retries_delay: int = 5, calc_md5sum: bool = False, _t: MethodType|FunctionType = lambda x: x) -> tuple[str, str|None, str|None, bool, str|None]:
    """
    Download a file from a given URL and save it to the given filepath.

    Args:
        url (str): The URL to download from.
        filepath (str): The filepath to save the file to.
        timeout (int): The timeout for the HTTP request.
        retries (int): The number of times to retry the download if it fails with 5xx or timeout.
        retries_delay (int): The delay in seconds between retries.
        _t (MethodType|FunctionType): A translation function for internationalization.
            Defaults to lambda x: x.

    Returns:
        tuple[str, str|None, str|None, bool, str|None]: A tuple containing the URL, download filepath,
            MD5 checksum of a downloaded file, a boolean indicating whether the download was successful,
            and an error message if it was not.
    """
    _logger = get_logger()
    retries = retries if retries > 0 else 1
    last_exception, i = None, 0
    for i in range(1, retries + 1):
        try:
            r = httpx.get(url, timeout=timeout)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            _logger.debug(_t("Saved: {url} -> {filepath}").format(url=url, filepath=filepath))
            return url, filepath, md5sum(r.content), True, None
        except Exception as e:
            last_exception = e
            if i == retries or not any((isinstance(e, httpx.TimeoutException), (isinstance(e, httpx.HTTPStatusError) and 500 <= e.response.status_code < 600), isinstance(e, httpx.ConnectError))):
                _logger.warning(_t("Error while downloading {url} ({exception})").format(url=url, exception=format_exception(e)))
                break
            _logger.debug(_t("Error ({exception}) while downloading {url}, retrying").format(url=url, exception=format_exception(e)))
            time.sleep(retries_delay)
    return url, None, None, False, f"{format_exception(last_exception)}, retries: {i}"

def exit(output_folder: bool=False, _t: MethodType|FunctionType = lambda x: x):
    """
    Print a message indicating the end of the script, and exit with code 0.

    Args:
        output_folder (bool): Whether to print a message indicating the output
            folder.
        _t (MethodType|FunctionType): A translation function for
            internationalization. Defaults to lambda x: x.
    """
    if output_folder:
        print('\n', _t("Output saved to {output_folder}").format(output_folder=output_folder), sep='')
    else:
        print('\n', _t("Nothing to save."), sep='')
    print(_t("WayBack File Fetcher finished."))
    sys.exit(0)

def main():
    """
    The main entry point of the script.

    This function initializes the logging, loads the translations, parses the
    command line arguments, fetches the index from the Wayback Machine, filters
    the records based on the given criteria, saves the metadata to the given
    folder, and downloads the files based on the given criteria.

    :returns: None
    """
    translation = init_gettext(lang:=get_lang())
    _t = translation.gettext
    _logger = get_logger()
    args = parse_args(_t)
    print("==== WayBack File Fetcher ====")
    print(_t("Author: FazaN (https://t.me/CyberFazaN)"))
    _logger.debug(_t("Using language: {lang_code}").format(lang_code=lang))
    _logger.debug(_t("Given arguments: {args}").format(args=pformat(vars(args))))

    records, headers = fetch_index(args.domain, args.limit, args.statuscodes, args.http, _t)
    if not records:
        _logger.warning(_t("WayBack Machine returned empty result. Probably, the archive is empty."))
        return exit(False, _t)

    filtered, nonuniq = filter_records(records, args.extensions, args.mimetypes, args.regex)

    save_metadata(args.output_folder, "full-index", headers, records, args.output_format)
    if filtered and filtered != records:
        save_metadata(args.output_folder, "targets", headers, filtered, args.output_format)
    if nonuniq:
        save_metadata(args.output_folder, "multiple-versions", headers, nonuniq, args.output_format)
    
    print(_t("Index fetched! Summary:"))
    print(_t("Total: {total}, Targets: {targets}, With multiple versions: {multiple}").format(total=len(records), targets=len(filtered), multiple=len(nonuniq)))

    if args.download_first or args.download_last or args.download_current:
        if len(filtered) == 0:
            _logger.warning(_t("Nothing to download: no target records found."))
            return exit(args.output_folder, _t)
        if not any([args.extensions, args.mimetypes, args.regex]):
            _logger.warning(_t("No filtering applied. This will download whole archive. It may take a long time."))
            answer = boolean_answer(input(f'{_t("Do you want to continue?")} {_t("(y/N)")}> ').strip().lower(), False)
            if not answer:
                _logger.info(_t("Aborted."))
                return exit(args.output_folder, _t)
            
        out_files = os.path.join(args.output_folder, "files")
        os.makedirs(out_files, exist_ok=True)
            
        tasks = []
        for rec in filtered:
            if args.download_first:
                url = f"{'http' if args.http else 'https'}://web.archive.org/web/{rec['timestamp']}im_/{rec['original']}"
                path = build_filepath(rec, out_files, args.structured, rec['timestamp'])
                tasks.append((url, path, args.download_timeout_wayback))
            if args.download_last and (not args.download_first or rec['endtimestamp'] != rec['timestamp']):
                url = f"{'http' if args.http else 'https'}://web.archive.org/web/{rec['endtimestamp']}im_/{rec['original']}"
                path = build_filepath(rec, out_files, args.structured, rec['endtimestamp'])
                tasks.append((url, path, args.download_timeout_wayback))
            if args.download_current:
                url = rec['original']
                path = build_filepath(rec, out_files, args.structured, "current")
                tasks.append((url, path, args.download_timeout_origin))
        
        print("\n", _t("Start downloading desired files ({files_count})...").format(files_count=len(tasks)), sep='')
        if len(tasks) > len(filtered):
            print(_t("Note that quantity of files to download is higher than quantity of target records.\nThis is normal as we will download multiple versions of these files.\n"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as ex:
            futures = [
                ex.submit(download_file, url, path, to, args.download_retries, args.download_retries_delay, args.deduplicate, _t)
                for url, path, to in tasks
            ]
            concurrent.futures.wait(futures)
        
        results = [f.result() for f in futures]
        unsuccessful_downloads = [{"URL": r[0], "Error": r[4]} for r in results if not r[3]]
        successful_downloads = [r for r in results if r[3]]
        
        print('\n', _t("Download complete."), sep='')
        print(_t("Successfully downloaded {successful_count} files.").format(successful_count=len(successful_downloads)))
        print(_t("Failed to download {unsuccessful_count} files.").format(unsuccessful_count=len(unsuccessful_downloads)))
        if unsuccessful_downloads:
            save_metadata(args.output_folder, "unsuccessful-downloads", ["URL", "Error"], unsuccessful_downloads, args.output_format)
        
        if args.deduplicate:
            print("\n", _t("Searching for duplicates in downloaded files ({files_count})...").format(files_count=len(successful_downloads)), sep='')
            duplicates = find_duplicates(successful_downloads)
            print(_t("Found {duplicates_count} duplicates. Deleting...").format(duplicates_count=len(duplicates)))
            delete_files(duplicates, _t)
            print(_t("Deduplication complete."))
        
    return exit(args.output_folder, _t)


if __name__ == "__main__":
    main()
    