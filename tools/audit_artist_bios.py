#!/usr/bin/env python3
"""Audit artist biography text for likely cross-artist contamination."""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup


CJK_RE = re.compile(r"[\u3040-\u9fff]")


def latin_name(title: str) -> str:
    return CJK_RE.split(title or "", maxsplit=1)[0].strip()


def bio_text(row: dict[str, str]) -> str:
    if row.get("bio_text"):
        return row["bio_text"]
    if row.get("bio_md"):
        return row["bio_md"]
    if row.get("bio_html"):
        soup = BeautifulSoup(row["bio_html"], "lxml")
        return soup.get_text(" ", strip=True)
    if row.get("bio_html_clean"):
        soup = BeautifulSoup(row["bio_html_clean"], "lxml")
        return soup.get_text(" ", strip=True)
    return ""


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def primary_name(text: str) -> str:
    return re.sub(r"\([^)]*\)", "", text or "").strip()


def ascii_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def compact_norm(text: str) -> str:
    folded = ascii_fold(text)
    return re.sub(r"[\s.。・,，()（）-]+", "", normalized(folded))


def same_artist_name(expected: str, found: str) -> bool:
    expected_compact = compact_norm(primary_name(expected))
    found_compact = compact_norm(primary_name(found))
    if not expected_compact or not found_compact:
        return False
    return expected_compact in found_compact or found_compact in expected_compact


def remove_record_heading(text: str, own_name: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines()]
    if lines and own_name and own_name in lines[0]:
        return "\n".join(lines[1:]).strip()
    return text or ""


def inner_heading_name(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    match = re.search(
        r"(?:Biographical Data\s+)?(?:Biography|Profile)\s+(.{3,90}?)(?:\s+\(|\s+Sources?:|\s+Source:|$)",
        compact,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" -*") if match else ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Audit artist bios for likely wrong-artist text")
    parser.add_argument("csv_path", nargs="?", default="_data/artist-metadata.csv")
    args = parser.parse_args()

    path = Path(args.csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    names = []
    for row in rows:
        name = latin_name(row.get("title", ""))
        if len(name) >= 6:
            names.append((row.get("objectid", ""), row.get("title", ""), name, normalized(name), compact_norm(name)))

    problems: list[tuple[str, str, str, str, str]] = []
    for row in rows:
        oid = row.get("objectid", "")
        title = row.get("title", "")
        own_name = latin_name(title)
        own_norm = normalized(own_name)
        text = bio_text(row)
        body_after_heading = remove_record_heading(text, own_name)
        text_norm = normalized(body_after_heading[:2500])
        opening_norm = normalized(text[:500])

        if text and own_norm and own_norm not in opening_norm:
            problems.append((oid, title, "own name absent from opening", own_name, text[:180].replace("\n", " ")))
            continue

        inner_name = inner_heading_name(body_after_heading[:1200])
        if inner_name and own_norm and not same_artist_name(own_name, inner_name):
            matched = inner_name
            for other_oid, other_title, other_name, other_norm, other_compact in names:
                if other_oid != oid and same_artist_name(other_name, inner_name):
                    matched = f"{other_oid}: {other_title}"
                    break
            if matched != inner_name or "possible wrong artist bio" in row.get("notes", ""):
                problems.append((oid, title, "inner biography/profile heading names another artist", matched, text[:180].replace("\n", " ")))

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["objectid", "title", "issue", "matched", "bio_prefix"])
    writer.writerows(problems)
    print(f"\nAudited {len(rows)} rows; possible problems: {len(problems)}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
