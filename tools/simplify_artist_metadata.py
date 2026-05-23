#!/usr/bin/env python3
"""Simplify artist metadata biographies.

The source CSV accumulated large HTML fragments and Markdown with inline links.
This script keeps the artist metadata spreadsheet human-editable by converting
biographies to plain text and moving external links into a separate references
field.
"""
from __future__ import annotations

import argparse
import csv
import re
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


DROP_COLUMNS = {"prints_html", "bio_html", "bio_html_clean", "bio_md"}
RENAME_COLUMNS = {
    'momjh link (add href, "for a biography of this artist see More of My Japanese Hanga") Biography': "momjh_biography_url",
}
BAD_MARKERS = ("Â", "Ã", "â", "Å", "æ", "ç", "è", "�")
REFERENCE_SEP = " | "
URL_RE = re.compile(r"https?://[^\s<>)\]}\"']+")
COMMON_REPLACEMENTS = {
    "Â": "",
    "Å": "ō",
    "Å": "Ō",
    "â": "–",
    "â": "—",
    "â": "‘",
    "â": "’",
    "â": "“",
    "â": "”",
}
CONFIRMED_WRONG_BIO_MARKERS = {
    "ihl_artist_026": ("Kojima Sh", "Kojima Shōgetsu", "小島"),
    "ihl_artist_141": ("Koga Misao", "古賀操", "古賀みさお"),
    "ihl_artist_181": ("Utagawa Kuniteru 歌川 国輝(初代)", "active ca. 1820-1860"),
    "ihl_artist_191": ("Nagashima Shungyō", "永 嶌 春暁", "Nagashima Shungyo"),
}


def repair_mojibake(text: str) -> str:
    """Repair common UTF-8-as-Windows-1252/Latin-1 mojibake when detectable."""
    if not text:
        return ""
    for bad, good in COMMON_REPLACEMENTS.items():
        text = text.replace(bad, good)

    candidates = {text}
    for encoding in ("cp1252", "latin1"):
        try:
            candidates.add(text.encode(encoding).decode("utf-8"))
        except UnicodeError:
            pass

    def score(candidate: str) -> tuple[int, int, int]:
        bad_count = sum(candidate.count(marker) for marker in BAD_MARKERS)
        replacement_count = candidate.count("\ufffd")
        cjk_count = sum(1 for ch in candidate if "\u3040" <= ch <= "\u9fff")
        return (bad_count + replacement_count * 2, -cjk_count, len(candidate))

    return min(candidates, key=score)


def clean_url(url: str) -> str:
    url = unescape(url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.netloc == "www.google.com" and parsed.path == "/url":
        q = parse_qs(parsed.query).get("q")
        if q:
            return unquote(q[0]).strip()
    return url


def normalize_space(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = repair_mojibake(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def has_bad_markers(text: str) -> bool:
    return any(marker in (text or "") for marker in BAD_MARKERS)


def markdown_links(markdown: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for label, url in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown or ""):
        clean = clean_url(url)
        if clean.startswith(("http://", "https://")):
            refs.append((normalize_space(label), clean))
    return refs


def readable_url_label(url: str) -> str:
    parsed = urlparse(clean_url(url))
    if not parsed.netloc:
        return url
    path = parsed.path.strip("/")
    if path:
        path = unquote(path).replace("-", " ")
        path = re.sub(r"\.(html?|pdf)$", "", path, flags=re.IGNORECASE)
        path = path.split("/")[-1] or parsed.netloc
        path = normalize_space(path)
        if len(path) > 60:
            path = f"{path[:57].rstrip()}..."
        return f"{parsed.netloc}: {path}"
    return parsed.netloc


def extract_plain_urls(text: str) -> tuple[str, list[tuple[str, str]]]:
    refs: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0).rstrip(".,;:")
        trailing = match.group(0)[len(raw):]
        url = clean_url(raw)
        refs.append((readable_url_label(url), url))
        return trailing

    text = URL_RE.sub(replace, text or "")
    text = re.sub(r"[ \t]+([,.;:])", r"\1", text)
    text = re.sub(r" {2,}", " ", text)
    return normalize_space(text), refs


def strip_markdown(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", markdown or "")
    text = re.sub(r"[*_`]+", "", text)
    return normalize_space(text)


def clean_bio_text(row: dict[str, str], bio_text: str) -> str:
    bio_text = normalize_space(bio_text)
    title = normalize_space(row.get("title", ""))
    date = normalize_space(row.get("date", ""))
    heading = f"{title} ({date})" if title and date else title

    # If the scraper only produced damaged Markdown, rebuild the damaged
    # opening artist-name line from the trusted title/date columns.
    title_missing = title and title not in bio_text[:300]
    if heading and (has_bad_markers(bio_text[:1000]) or title_missing):
        match = re.search(r"\bSources?:", bio_text[:1000], flags=re.IGNORECASE)
        if match:
            bio_text = f"{heading}\n\n{bio_text[match.start():]}"
        elif not bio_text.startswith(title):
            bio_text = f"{heading}\n\n{bio_text}"

    bio_text = re.sub(r"^(Biographical Data\s+)?Biography\s+", "", bio_text, flags=re.IGNORECASE)
    bio_text = re.sub(r"\b(Sources?:)(?=\S)", r"\1 ", bio_text)
    bio_text = re.sub(r"(?<=[a-z\)])(?=[A-Z][a-z])", " ", bio_text)
    if row.get("objectid") == "ihl_artist_371":
        bio_text = bio_text.replace('characters 3"Yonehide"', 'characters 米英 "Yonehide"')
        bio_text = bio_text.replace("Matsuno Yonejir.", "Matsuno Yonejirō.")
        bio_text = bio_text.replace("Matsuno Yoneijir,", "Matsuno Yonejirō,")
        bio_text = re.sub(r"Artist's Signature and Seal.*$", "", bio_text).strip()
    return normalize_space(bio_text)


def clean_notes(notes: str, title: str, bio_text: str) -> str:
    parts = [part.strip() for part in (notes or "").split(";") if part.strip()]
    cleaned: list[str] = []
    for part in parts:
        cleaned.append(part)
    return "; ".join(cleaned)


def append_note(notes: str, note: str) -> str:
    parts = [part.strip() for part in (notes or "").split(";") if part.strip()]
    if note not in parts:
        parts.append(note)
    return "; ".join(parts)


def has_confirmed_wrong_bio(row: dict[str, str], bio_text: str) -> bool:
    markers = CONFIRMED_WRONG_BIO_MARKERS.get(row.get("objectid", ""))
    if not markers:
        return False
    body = re.sub(r"^.*?(?:\n\n|\r\n\r\n| {2,})", "", bio_text or "", count=1, flags=re.DOTALL)
    return any(marker in body for marker in markers)


def node_text(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return normalize_space(str(node))
    if not isinstance(node, Tag):
        return ""
    if node.name == "br":
        return "\n"
    return normalize_space(" ".join(part for part in (node_text(child) for child in node.children) if part))


def html_to_text_and_refs(html: str) -> tuple[str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()

    refs: list[tuple[str, str]] = []
    for link in soup.find_all("a"):
        href = clean_url(link.get("href", ""))
        if href.startswith(("http://", "https://")):
            refs.append((normalize_space(link.get_text(" ", strip=True)) or href, href))
        link.unwrap()

    blocks: list[str] = []
    block_tags = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div", "blockquote"])
    if not block_tags:
        text = normalize_space(soup.get_text("\n"))
        return text, refs

    seen = set()
    for tag in block_tags:
        if any(parent in seen for parent in tag.parents):
            continue
        text = node_text(tag)
        if not text:
            continue
        if tag.name == "li":
            text = f"- {text}"
        blocks.append(text)
        seen.add(tag)

    text = normalize_space("\n\n".join(blocks))
    return text, refs


def dedupe_refs(refs: Iterable[tuple[str, str]]) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for label, url in refs:
        url = clean_url(url)
        if not url or url in seen:
            continue
        seen.add(url)
        label = normalize_space(label)
        parts.append(f"{label}{REFERENCE_SEP}{url}" if label and label != url else url)
    return " ; ".join(parts)


def simplify_row(row: dict[str, str]) -> dict[str, str]:
    row = {RENAME_COLUMNS.get(key, key): value for key, value in row.items()}

    refs: list[tuple[str, str]] = []
    html_source = row.get("bio_html") or row.get("bio_html_clean")
    if html_source:
        bio_text, refs = html_to_text_and_refs(html_source)
    elif row.get("bio_text"):
        bio_text = row.get("bio_text", "")
        refs = []
    else:
        bio_text = strip_markdown(row.get("bio_md", ""))
        refs = markdown_links(row.get("bio_md", ""))

    if not bio_text and row.get("text"):
        bio_text = normalize_space(row["text"])
    bio_text = clean_bio_text(row, bio_text)
    bio_text, plain_url_refs = extract_plain_urls(bio_text)
    refs.extend(plain_url_refs)

    for key in ("momjh_biography_url", "link", "link_original"):
        url = clean_url(row.get(key, ""))
        if url.startswith(("http://", "https://")):
            refs.append((key, url))

    new_row: dict[str, str] = {}
    for key, value in row.items():
        if key in DROP_COLUMNS:
            continue
        new_row[key] = normalize_space(value) if key != "prints_links" else value.strip()

    new_row["bio_text"] = bio_text
    new_row["bio_references"] = dedupe_refs(refs)
    new_row["notes"] = clean_notes(new_row.get("notes", ""), new_row.get("title", ""), bio_text)
    if has_confirmed_wrong_bio(new_row, bio_text) or "removed wrong artist bio" in new_row.get("notes", ""):
        title = normalize_space(new_row.get("title", ""))
        date = normalize_space(new_row.get("date", ""))
        new_row["bio_text"] = f"{title} ({date})" if title and date else normalize_space(new_row.get("text", ""))
        new_row["notes"] = append_note(new_row.get("notes", ""), "removed wrong artist bio")
    return new_row


def output_columns(input_columns: list[str]) -> list[str]:
    columns = [RENAME_COLUMNS.get(col, col) for col in input_columns if col not in DROP_COLUMNS]
    for col in ("bio_text", "bio_references"):
        if col not in columns:
            columns.append(col)
    return columns


def main() -> int:
    parser = argparse.ArgumentParser(description="Simplify _data/artist-metadata.csv")
    parser.add_argument("--input", default="_data/artist-metadata.csv")
    parser.add_argument("--output", default="_data/artist-metadata.csv")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit("Input CSV has no header")
        rows = [simplify_row(row) for row in reader]
        columns = output_columns(reader.fieldnames)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")
    print("Columns:", ", ".join(columns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
