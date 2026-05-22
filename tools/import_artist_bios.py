#!/usr/bin/env python3
"""Import artist biographies from external artist pages into a CSV.

Usage examples:
  py tools/import_artist_bios.py --input _data/artist-metadata.csv --output artist-metadata-with-bios.csv --dry-run
  py tools/import_artist_bios.py --input _data/artist-metadata.csv --output artist-metadata-with-bios.csv

Requirements: pandas, requests, beautifulsoup4, lxml
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from html import unescape
from typing import Optional, Tuple, List
from urllib.parse import urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag, NavigableString


ALLOWED_TAGS = {"p", "em", "i", "strong", "b", "a", "ul", "ol", "li", "br"}
HEADING_TAGS = [f"h{i}" for i in range(1, 7)]


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    # remove weird invisible characters
    s = s.replace("\u200b", "").replace("\ufeff", "").replace("\u00a0", " ")
    s = unescape(s)
    s = unicodedata.normalize("NFKC", s)
    return s.strip()


def get_first_url(field: str) -> Optional[str]:
    if not isinstance(field, str) or not field.strip():
        return None
    # fields may contain multiple URLs separated by | (pipe)
    parts = [p.strip() for p in field.split("|") if p.strip()]
    return parts[0] if parts else None


def extract_slug_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/home/artists/([^/\?#]+)", url)
    if m:
        return m.group(1)
    return None


def is_artist_page_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if not parsed.netloc or not parsed.path:
        return False
    m = re.match(r"^/home/artists/([^/]+)(?:/)?$", parsed.path)
    return bool(m)


def build_artist_page_url_from_slug(url: str) -> Optional[str]:
    slug = extract_slug_from_url(url)
    if not slug:
        return None
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "www.myjapanesehanga.com"
    path = f"/home/artists/{slug}.html"
    return urlunparse((scheme, netloc, path, "", "", ""))


def fetch_page(url: str, session: requests.Session, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
    """Return (final_url, html) or (None, None) on failure."""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.url, resp.text
    except requests.exceptions.SSLError:
        try:
            resp = session.get(url, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp.url, resp.text
        except Exception:
            return None, None
    except Exception:
        return None, None


def find_bio_heading(soup: BeautifulSoup) -> Optional[Tag]:
    # Look for headings with the word 'Biography' but avoid 'Biographical Data'
    for tag_name in HEADING_TAGS:
        for h in soup.find_all(tag_name):
            text = (h.get_text(" ") or "").strip()
            if re.search(r"\bBiography\b", text, re.IGNORECASE) and not re.search(r"Biographical Data", text, re.IGNORECASE):
                return h
    # sometimes 'Biography' appears in bold within a non-heading wrapper
    for b in soup.find_all(["b", "strong"]):
        txt = (b.get_text(" ") or "").strip()
        if re.fullmatch(r"Biography", txt, re.IGNORECASE):
            return b
    return None


def collect_bio_fragment(start_tag: Tag) -> List[Tag]:
    """Collect sibling tags after the heading until the next heading tag or similar sentinel."""
    fragments: List[Tag] = []
    for sib in start_tag.find_next_siblings():
        if isinstance(sib, Tag) and sib.name in HEADING_TAGS:
            break
        # stop on obvious section boundaries
        txt = (sib.get_text(" ") or "")
        if isinstance(sib, Tag) and sib.name == "hr":
            break
        fragments.append(sib)
    return fragments


def sanitize_fragment_html(fragment_tags: List[Tag]) -> str:
    # Parse the collected fragments as one small HTML document.
    # Converting tags to string then reparsing removes any references to the original soup.
    html_string = "".join(str(t) for t in fragment_tags)
    container = BeautifulSoup(html_string, "lxml")

    # Remove script/style
    for s in container(["script", "style"]):
        s.decompose()

    # Walk tags and remove/unwrap undesired tags
    for tag in container.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            # keep only href attribute on links
            if tag.name == "a":
                href = tag.get("href")
                tag.attrs = {}
                if href:
                    tag.attrs["href"] = href
            else:
                tag.attrs = {}

    html = container.decode_contents()
    return normalize_text(html)


def html_to_markdown(html_fragment: str) -> str:
    """Convert the minimal sanitized HTML fragment into Markdown.

    This is intentionally simple and targets the allowed tag set.
    """
    if not html_fragment:
        return ""
    soup = BeautifulSoup(html_fragment, "lxml")
    parts: List[str] = []

    def inline_text(node) -> str:
        if isinstance(node, NavigableString):
            return normalize_text(str(node))
        if isinstance(node, Tag):
            if node.name in ("em", "i"):
                return f"*{''.join(inline_text(c) for c in node.contents).strip()}*"
            if node.name in ("strong", "b"):
                return f"**{''.join(inline_text(c) for c in node.contents).strip()}**"
            if node.name == "a":
                text = ''.join(inline_text(c) for c in node.contents).strip()
                href = node.get("href") or ""
                return f"[{text}]({href})" if href else text
            # fallback: join textual children
            return ''.join(inline_text(c) for c in node.contents)
        return ""

    for elem in soup.contents:
        if isinstance(elem, NavigableString):
            text = normalize_text(str(elem))
            if text:
                parts.append(text)
            continue
        if not isinstance(elem, Tag):
            continue
        name = elem.name
        if name == "p":
            txt = ''.join(inline_text(c) for c in elem.contents).strip()
            if txt:
                parts.append(txt)
        elif name in ("ul", "ol"):
            is_ordered = name == "ol"
            for i, li in enumerate(elem.find_all("li", recursive=False), start=1):
                txt = ''.join(inline_text(c) for c in li.contents).strip()
                if is_ordered:
                    parts.append(f"{i}. {txt}")
                else:
                    parts.append(f"- {txt}")
        elif name == "br":
            parts.append("")
        else:
            # inline blocks like <div> may contain meaningful text
            txt = ''.join(inline_text(c) for c in elem.contents).strip()
            if txt:
                parts.append(txt)

    # Join paragraphs with blank line
    md = "\n\n".join([p for p in parts if p is not None])
    return normalize_text(md)


def detect_first_name_in_bio(fragment_tags: List[Tag]) -> Optional[str]:
    # look for first <b>/<strong> or linked name at start
    for t in fragment_tags:
        if isinstance(t, Tag):
            # check for bold/strong at the top
            b = t.find(["b", "strong"])
            if b and b.get_text(strip=True):
                return normalize_text(b.get_text())
            a = t.find("a")
            if a and a.get_text(strip=True):
                return normalize_text(a.get_text())
            # otherwise consider first paragraph text line (may include name)
            if t.name in ("p", "div"):
                txt = t.get_text(" ", strip=True)
                if txt:
                    # take first sentence or fragment up to a linebreak
                    return normalize_text(txt.split(".")[0])
    return None


def process_row(row: pd.Series, session: requests.Session, sleep: float = 0.5) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Return (bio_md, bio_html_clean, notes_list)

    notes_list contains strings to be appended to the 'notes' column when relevant.
    """
    notes: List[str] = []
    bio_md = None
    bio_html_clean = None

    # find a candidate URL: prefer explicit artist page link, fallback to a derived artist page URL from prints_links
    link_candidate = get_first_url(row.get("link", "") or "")
    prints_candidate = get_first_url(row.get("prints_links", "") or "")
    if link_candidate and is_artist_page_url(link_candidate):
        candidate = link_candidate
    elif link_candidate:
        candidate = link_candidate
    elif prints_candidate:
        candidate = build_artist_page_url_from_slug(prints_candidate) or prints_candidate
    else:
        notes.append("fetch failed")
        return None, None, notes

    if is_artist_page_url(candidate) and not candidate.endswith(".html"):
        candidate = candidate.rstrip("/") + ".html"

    expected_slug = extract_slug_from_url(candidate)

    final_url, html = fetch_page(candidate, session)
    if final_url is None or html is None:
        notes.append("fetch failed")
        return None, None, notes

    # simple slug mismatch detection: find artist slugs in page
    found_slugs = set(re.findall(r"/home/artists/([^/\?#\"']+)", html))
    if expected_slug and any(s != expected_slug for s in found_slugs):
        # if page references a different artist slug
        notes.append("slug mismatch")

    soup = BeautifulSoup(html, "lxml")
    # remove scripts/styles early
    for s in soup(["script", "style"]):
        s.decompose()

    heading = find_bio_heading(soup)
    if not heading:
        notes.append("bio not found")
        return None, None, notes

    fragments = collect_bio_fragment(heading)
    if not fragments:
        notes.append("bio not found")
        return None, None, notes

    # sanitize and produce html
    html_clean = sanitize_fragment_html(fragments)
    bio_html_clean = html_clean if html_clean else None

    # attempt conversion to markdown
    md = html_to_markdown(html_clean)
    if md:
        bio_md = md

    # detect possible wrong artist bio by comparing the first bold/linked name to our title
    first_name = detect_first_name_in_bio(fragments)
    expected_title = normalize_text(row.get("title", ""))
    if first_name and expected_title and expected_title.lower() not in first_name.lower() and first_name.lower() not in expected_title.lower():
        notes.append("possible wrong artist bio")

    # normalize text bodies
    if bio_md:
        bio_md = normalize_text(bio_md)
    if bio_html_clean:
        bio_html_clean = normalize_text(bio_html_clean)

    time.sleep(sleep)
    return bio_md, bio_html_clean, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import artist bios into CSV")
    parser.add_argument("--input", required=True, help="Input CSV (UTF-8)")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Don't write output; show sample and counts")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds to sleep between requests (throttle)")
    parser.add_argument("--sample", type=int, default=5, help="Sample size to show in dry-run")
    args = parser.parse_args(argv)

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    # ensure notes column exists
    if "notes" not in df.columns:
        df["notes"] = ""

    total = len(df)
    fetched_ok = 0
    bio_extracted = 0
    failures = {"fetch failed": 0, "bio not found": 0, "slug mismatch": 0, "possible wrong artist bio": 0}

    session = requests.Session()
    session.headers.update({"User-Agent": "ihl-csv-importer/1.0 (+https://github.com)"})

    samples: List[Tuple[str, str]] = []

    print(f"Processing {total} rows...")
    for idx, row in df.iterrows():
        objid = row.get("objectid") or row.get("id") or f"row-{idx}"
        print(f"[{idx+1}/{total}] {objid} ...", end=" ")
        try:
            bio_md, bio_html_clean, notes_list = process_row(row, session, sleep=args.sleep)
            if bio_md or bio_html_clean:
                fetched_ok += 1
            if bio_md:
                df.at[idx, "bio_md"] = bio_md
                bio_extracted += 1
            if bio_html_clean and not bio_md:
                df.at[idx, "bio_html_clean"] = bio_html_clean

            # merge notes
            if notes_list:
                existing = normalize_text(df.at[idx, "notes"])
                merged = existing
                for n in notes_list:
                    failures.setdefault(n, 0)
                    failures[n] = failures.get(n, 0) + 1
                    if merged:
                        merged = merged + "; " + n
                    else:
                        merged = n
                df.at[idx, "notes"] = merged

            # collect sample
            if (bio_md or bio_html_clean) and len(samples) < args.sample:
                snippet = (bio_md or bio_html_clean or "")[:800]
                samples.append((objid, snippet))

            print("done")
        except Exception as e:
            print(f"ERROR: {e}")
            df.at[idx, "notes"] = (normalize_text(df.at[idx, "notes"]) + "; fetch failed").lstrip("; ")
            failures["fetch failed"] = failures.get("fetch failed", 0) + 1

    # summary
    print("\nSummary:")
    print(f"  total rows: {total}")
    print(f"  pages fetched (had bio or html): {fetched_ok}")
    print(f"  bios extracted (bio_md): {bio_extracted}")
    print("  failures breakdown:")
    for k, v in failures.items():
        print(f"    {k}: {v}")

    if args.dry_run:
        print("\nDry-run: sample extracted bios:")
        for objid, snippet in samples:
            print(f"- {objid}: {snippet[:200].replace('\n',' ')}...")
        print("\nNo output written (dry-run).")
        return 0

    # write output CSV as UTF-8
    df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"Wrote output CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
