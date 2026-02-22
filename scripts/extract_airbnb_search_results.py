#!/usr/bin/env python3
"""Extract Airbnb listing cards from one or more search results pages.

Also persists normalized listing records into SQLite for UI/reporting use.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
import re
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOM_ID_RE = re.compile(r"/rooms/(\d+)")
RATING_PAREN_RE = re.compile(r"(\d(?:\.\d+)?)\s*\((\d[\d,]*)\)")
RATING_VERBOSE_RE = re.compile(r"(\d(?:\.\d+)?) out of 5 average rating,\s*(\d[\d,]*) reviews", re.I)
DATE_RANGE_RE = re.compile(r"\b([A-Z][a-z]{2}\s+\d{1,2}\s*[–-]\s*\d{1,2})\b")
PRICE_FOR_NIGHTS_RE = re.compile(r"\$([\d,]+)\s*for\s*(\d+)\s*nights?", re.I)
PRICE_LINE_RE = re.compile(r"\$([\d,]+)")
NIGHTS_LINE_RE = re.compile(r"for\s*(\d+)\s*nights?", re.I)
CAPACITY_RE = re.compile(
    r"(\d+)\s+guests?\s*·\s*(\d+)\s+bedrooms?\s*·\s*(\d+)\s+beds?\s*·\s*([\d.]+)\s+baths?",
    re.IGNORECASE,
)
CAPACITY_RE_NO_BEDS = re.compile(
    r"(\d+)\s+guests?\s*·\s*(\d+)\s+bedrooms?\s*·\s*([\d.]+)\s+baths?",
    re.IGNORECASE,
)
CAL_DAY_RE = re.compile(r"calendar-day-(\d{2}/\d{2}/\d{4})")

logger = logging.getLogger("airbnb_search_extractor")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    listing_url TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_label TEXT,
    source_display TEXT,
    center_lat REAL,
    center_lng REAL,
    rating REAL,
    review_count INTEGER,
    date_range_text TEXT,
    total_price INTEGER,
    nights INTEGER,
    price_per_night REAL,
    active INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

COMPETITIVE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listing_competitive_stats (
    listing_url TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    rating REAL,
    review_count INTEGER,
    guests INTEGER,
    bedrooms INTEGER,
    beds INTEGER,
    bathrooms REAL,
    forward_days INTEGER,
    days_booked INTEGER,
    days_not_booked INTEGER,
    vacancy_pct REAL,
    occupancy_pct REAL,
    booked_ranges TEXT,
    available_ranges TEXT,
    min_stay_note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="Single Airbnb search results URL")
    p.add_argument("--urls-file", help="Path to text file containing one search URL per line")
    p.add_argument("--output", required=True, help="Output JSON path")
    p.add_argument("--db-path", default="data/airbnb_search_results.db", help="SQLite DB path")
    p.add_argument("--max-scrolls", type=int, default=30, help="Maximum number of scroll iterations")
    p.add_argument("--stop-after-stable-scrolls", type=int, default=4, help="Stop after this many scrolls with no new listing URLs")
    p.add_argument("--scroll-delay-seconds", type=float, default=1.5)
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Optional pre-extract delay")
    p.add_argument("--timeout-ms", type=int, default=90_000)
    p.add_argument("--start-date", help="Forward-calendar start date (YYYY-MM-DD). Defaults to first day of next month.")
    p.add_argument("--skip-competitive-details", action="store_true", help="Skip per-listing competitive stats extraction")
    p.add_argument("--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()
    if not args.url and not args.urls_file:
        p.error("Provide either --url or --urls-file")
    return args


def source_label_from_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    query = qs.get("query", [None])[0]
    if query:
        return unquote(query)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "s":
        return unquote(parts[1]).replace("--", " ")
    return parsed.netloc


def source_center_from_url(url: str) -> tuple[float | None, float | None]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    ne_lat = qs.get("ne_lat", [None])[0]
    ne_lng = qs.get("ne_lng", [None])[0]
    sw_lat = qs.get("sw_lat", [None])[0]
    sw_lng = qs.get("sw_lng", [None])[0]
    try:
        if all([ne_lat, ne_lng, sw_lat, sw_lng]):
            return (float(ne_lat) + float(sw_lat)) / 2.0, (float(ne_lng) + float(sw_lng)) / 2.0
    except ValueError:
        return None, None
    return None, None


def reverse_geocode_label(lat: float | None, lng: float | None, fallback: str) -> str:
    if lat is None or lng is None:
        return fallback
    req = Request(
        f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lng}",
        headers={"User-Agent": "ml-tutorial-airbnb-extractor/1.0"},
    )
    try:
        with urlopen(req, timeout=4) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return f"{fallback}, map {lat:.4f},{lng:.4f}"

    addr = payload.get("address", {}) if isinstance(payload, dict) else {}
    area = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("town")
    city = addr.get("city") or addr.get("town") or addr.get("village")
    if city and area and area.lower() != city.lower():
        return f"{city}, {area}"
    if city:
        return city
    return f"{fallback}, map {lat:.4f},{lng:.4f}"


def short_source(url: str) -> str:
    label = source_label_from_url(url)
    return f"{label[:42]}..." if len(label) > 45 else label


def _sleep_with_jitter(base: float) -> None:
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, 0.75))


def _to_int(num_text: str | None) -> int | None:
    if not num_text:
        return None
    return int(num_text.replace(",", ""))


def _parse_card_fields(card_text: str) -> dict[str, Any]:
    rating = None
    review_count = None

    m = RATING_PAREN_RE.search(card_text)
    if m:
        rating = float(m.group(1))
        review_count = _to_int(m.group(2))
    else:
        m2 = RATING_VERBOSE_RE.search(card_text)
        if m2:
            rating = float(m2.group(1))
            review_count = _to_int(m2.group(2))

    date_range = None
    dm = DATE_RANGE_RE.search(card_text)
    if dm:
        date_range = dm.group(1).replace(" - ", "-").replace(" – ", "–")

    total_price = None
    nights = None
    pm = PRICE_FOR_NIGHTS_RE.search(card_text)
    if pm:
        total_price = _to_int(pm.group(1))
        nights = int(pm.group(2))
    else:
        p_line = PRICE_LINE_RE.search(card_text)
        n_line = NIGHTS_LINE_RE.search(card_text)
        if p_line:
            total_price = _to_int(p_line.group(1))
        if n_line:
            nights = int(n_line.group(1))

    price_per_night = None
    if total_price is not None and nights:
        price_per_night = round(total_price / nights, 2)

    return {
        "rating": rating,
        "review_count": review_count,
        "date_range_text": date_range,
        "total_price": total_price,
        "nights": nights,
        "price_per_night": price_per_night,
    }


def _load_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    if args.url:
        urls.append(args.url)
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return list(dict.fromkeys(urls))


def _extract_from_search_page(page, url: str, args: argparse.Namespace) -> dict[str, Any]:
    source_label = source_label_from_url(url)
    center_lat, center_lng = source_center_from_url(url)
    source_display = reverse_geocode_label(center_lat, center_lng, source_label)
    logger.info("Processing source: %s", short_source(url))

    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
    _sleep_with_jitter(args.delay_seconds)

    seen_listing_ids: set[str] = set()
    stable_scrolls = 0
    for _ in range(args.max_scrolls):
        page.mouse.wheel(0, 3000)
        _sleep_with_jitter(args.scroll_delay_seconds)

        hrefs = page.eval_on_selector_all(
            'a[href*="/rooms/"]',
            'els => els.map(el => el.href)',
        )
        current_ids = {
            m.group(1)
            for h in hrefs
            for m in [ROOM_ID_RE.search(h or "")]
            if m
        }
        if len(current_ids) == len(seen_listing_ids):
            stable_scrolls += 1
        else:
            stable_scrolls = 0
            seen_listing_ids = current_ids

        if stable_scrolls >= args.stop_after_stable_scrolls:
            break

    raw_cards = page.evaluate(
        """
        () => {
          const anchors = [...document.querySelectorAll('a[href*="/rooms/"]')];
          return anchors.map(a => {
            const card = a.closest('[itemprop="itemListElement"], [data-testid="card-container"], div[role="group"]') || a.parentElement;
            return {
              href: a.href,
              card_text: (card?.innerText || '').trim()
            };
          });
        }
        """
    )

    by_listing: dict[str, dict[str, Any]] = {}
    for row in raw_cards:
        href = row.get("href") or ""
        m = ROOM_ID_RE.search(href)
        if not m:
            continue
        listing_id = m.group(1)
        listing_url = f"https://www.airbnb.com/rooms/{listing_id}"

        parsed = _parse_card_fields(row.get("card_text", ""))
        existing = by_listing.get(listing_id)
        score = sum(
            v is not None
            for v in [
                parsed["rating"],
                parsed["review_count"],
                parsed["date_range_text"],
                parsed["total_price"],
                parsed["nights"],
            ]
        )
        existing_score = -1
        if existing:
            existing_score = sum(
                v is not None
                for v in [
                    existing.get("rating"),
                    existing.get("review_count"),
                    existing.get("date_range_text"),
                    existing.get("total_price"),
                    existing.get("nights"),
                ]
            )
        if not existing or score > existing_score:
            by_listing[listing_id] = {
                "listing_id": listing_id,
                "listing_url": listing_url,
                **parsed,
                "card_text": row.get("card_text", "")[:500],
            }
            logger.info("[%s] listing_id=%s", short_source(url), listing_id)

    return {
        "source_url": url,
        "source_label": source_label,
        "source_display": source_display,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "count": len(by_listing),
        "results": sorted(by_listing.values(), key=lambda x: int(x["listing_id"])),
    }


def compress_ranges(dates: list[str]) -> list[str]:
    if not dates:
        return []
    dts = [dt.date.fromisoformat(d) for d in sorted(dates)]
    out: list[tuple[dt.date, dt.date]] = []
    start = prev = dts[0]
    for cur in dts[1:]:
        if cur - prev == dt.timedelta(days=1):
            prev = cur
            continue
        out.append((start, prev))
        start = prev = cur
    out.append((start, prev))
    return [f"{a.isoformat()} to {b.isoformat()}" if a != b else a.isoformat() for a, b in out]


def _extract_competitive_details(page, listing_url: str, start_date: dt.date, timeout_ms: int) -> dict[str, Any]:
    page.goto(listing_url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1200)

    rating = None
    review_count = None
    for block in page.locator('script[type="application/ld+json"]').all_text_contents():
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            agg = obj.get("aggregateRating")
            if isinstance(agg, dict):
                rating = agg.get("ratingValue", rating)
                review_count = agg.get("reviewCount", review_count)

    text = page.evaluate('document.body ? document.body.innerText : ""')
    guests = bedrooms = beds = bathrooms = None
    m = CAPACITY_RE.search(text)
    if m:
        guests, bedrooms, beds, bathrooms = m.groups()
    else:
        m2 = CAPACITY_RE_NO_BEDS.search(text)
        if m2:
            guests, bedrooms, bathrooms = m2.groups()

    opened = False
    for sel in ['button[data-testid="homes-pdp-cta-btn"]', "button:has-text('Check availability')"]:
        try:
            page.locator(sel).first.click(timeout=10_000)
            opened = True
            break
        except Exception:
            continue

    if not opened:
        return {
            "rating": rating,
            "review_count": _to_int(str(review_count)) if review_count is not None else None,
            "guests": _to_int(guests),
            "bedrooms": _to_int(bedrooms),
            "beds": _to_int(beds),
            "bathrooms": float(bathrooms) if bathrooms else None,
            "min_stay_note": "calendar button not found",
        }

    for sel in ['button[data-testid="calendar-next-button"]', 'button[aria-label*="Next"]', 'button[aria-label*="next"]']:
        try:
            page.locator(sel).first.click(timeout=2_000)
            break
        except Exception:
            continue
    page.wait_for_timeout(700)

    raw_days = page.eval_on_selector_all(
        '[data-testid^="calendar-day-"]',
        "els => els.map(el => [el.getAttribute('data-testid'), el.getAttribute('data-is-day-blocked'), el.getAttribute('aria-label') || el.parentElement?.getAttribute('aria-label') || ''])",
    )
    by_date: dict[str, bool] = {}
    min_stay_note = None
    for testid, blocked, aria_label in raw_days:
        mday = CAL_DAY_RE.match(testid or "")
        if not mday:
            continue
        date_iso = dt.datetime.strptime(mday.group(1), "%m/%d/%Y").date().isoformat()
        if dt.date.fromisoformat(date_iso) < start_date:
            continue
        by_date[date_iso] = blocked == "true"
        label = (aria_label or "").lower()
        if "minimum stay" in label:
            min_stay_note = "minimum stay restrictions present"

    dates = sorted(by_date)
    booked = [d for d in dates if by_date[d]]
    available = [d for d in dates if not by_date[d]]
    total = len(dates)
    days_booked = len(booked)
    days_not_booked = len(available)
    return {
        "rating": float(rating) if rating is not None else None,
        "review_count": _to_int(str(review_count)) if review_count is not None else None,
        "guests": _to_int(guests),
        "bedrooms": _to_int(bedrooms),
        "beds": _to_int(beds),
        "bathrooms": float(bathrooms) if bathrooms else None,
        "forward_days": total,
        "days_booked": days_booked,
        "days_not_booked": days_not_booked,
        "vacancy_pct": round((days_not_booked / total) * 100, 1) if total else None,
        "occupancy_pct": round((days_booked / total) * 100, 1) if total else None,
        "booked_ranges": compress_ranges(booked),
        "available_ranges": compress_ranges(available),
        "min_stay_note": min_stay_note,
    }


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    conn.execute(COMPETITIVE_SCHEMA_SQL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
    if "source_label" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN source_label TEXT")
    if "source_display" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN source_display TEXT")
    if "center_lat" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN center_lat REAL")
    if "center_lng" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN center_lng REAL")


def persist_results_to_db(payload: dict[str, Any], db_path: str) -> None:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_file) as conn:
        _ensure_schema(conn)

        for source in payload.get("sources", []):
            source_url = source.get("source_url")
            source_label = source.get("source_label") or source_label_from_url(source_url or "")
            source_display = source.get("source_display") or source_label
            center_lat = source.get("center_lat")
            center_lng = source.get("center_lng")
            if not source_url:
                continue

            conn.execute("UPDATE listings SET active = 0 WHERE source_url = ?", (source_url,))
            for row in source.get("results", []):
                conn.execute(
                    """
                    INSERT INTO listings (
                        listing_url, listing_id, source_url, source_label, rating, review_count,
                        source_display, center_lat, center_lng, date_range_text, total_price, nights,
                        price_per_night, active, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(listing_url) DO UPDATE SET
                        listing_id=excluded.listing_id,
                        source_url=excluded.source_url,
                        source_label=excluded.source_label,
                        source_display=excluded.source_display,
                        center_lat=excluded.center_lat,
                        center_lng=excluded.center_lng,
                        rating=excluded.rating,
                        review_count=excluded.review_count,
                        date_range_text=excluded.date_range_text,
                        total_price=excluded.total_price,
                        nights=excluded.nights,
                        price_per_night=excluded.price_per_night,
                        active=1,
                        last_seen_at=CURRENT_TIMESTAMP
                    """,
                    (
                        row.get("listing_url"),
                        row.get("listing_id"),
                        source_url,
                        source_label,
                        row.get("rating"),
                        row.get("review_count"),
                        source_display,
                        center_lat,
                        center_lng,
                        row.get("date_range_text"),
                        row.get("total_price"),
                        row.get("nights"),
                        row.get("price_per_night"),
                    ),
                )


def persist_competitive_to_db(rows: list[dict[str, Any]], db_path: str) -> None:
    if not rows:
        return
    with sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        for r in rows:
            conn.execute(
                """
                INSERT INTO listing_competitive_stats (
                    listing_url, listing_id, source_url, rating, review_count,
                    guests, bedrooms, beds, bathrooms,
                    forward_days, days_booked, days_not_booked,
                    vacancy_pct, occupancy_pct, booked_ranges, available_ranges,
                    min_stay_note, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(listing_url) DO UPDATE SET
                    listing_id=excluded.listing_id,
                    source_url=excluded.source_url,
                    rating=excluded.rating,
                    review_count=excluded.review_count,
                    guests=excluded.guests,
                    bedrooms=excluded.bedrooms,
                    beds=excluded.beds,
                    bathrooms=excluded.bathrooms,
                    forward_days=excluded.forward_days,
                    days_booked=excluded.days_booked,
                    days_not_booked=excluded.days_not_booked,
                    vacancy_pct=excluded.vacancy_pct,
                    occupancy_pct=excluded.occupancy_pct,
                    booked_ranges=excluded.booked_ranges,
                    available_ranges=excluded.available_ranges,
                    min_stay_note=excluded.min_stay_note,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    r.get("listing_url"),
                    r.get("listing_id"),
                    r.get("source_url"),
                    r.get("rating"),
                    r.get("review_count"),
                    r.get("guests"),
                    r.get("bedrooms"),
                    r.get("beds"),
                    r.get("bathrooms"),
                    r.get("forward_days"),
                    r.get("days_booked"),
                    r.get("days_not_booked"),
                    r.get("vacancy_pct"),
                    r.get("occupancy_pct"),
                    json.dumps(r.get("booked_ranges") or []),
                    json.dumps(r.get("available_ranges") or []),
                    r.get("min_stay_note"),
                ),
            )
        conn.commit()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    urls = _load_urls(args)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.start_date:
        start_date = dt.date.fromisoformat(args.start_date)
    else:
        today = dt.date.today()
        start_date = dt.date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)

    per_source: list[dict[str, Any]] = []
    competitive_rows: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(locale="en-US")
        for url in urls:
            page = context.new_page()
            try:
                per_source.append(_extract_from_search_page(page, url, args))
            except Exception as exc:  # noqa: BLE001
                per_source.append({
                    "source_url": url,
                    "source_label": source_label_from_url(url),
                    "error": str(exc),
                    "count": 0,
                    "results": [],
                })
                logger.error("Failed source %s: %s", short_source(url), exc)
            finally:
                page.close()
            _sleep_with_jitter(args.delay_seconds)

        if not args.skip_competitive_details:
            for source in per_source:
                src_url = source.get("source_url")
                for row in source.get("results", []):
                    listing_url = row.get("listing_url")
                    if not listing_url:
                        continue
                    logger.info("[competitive] %s :: %s", short_source(src_url or ""), row.get("listing_id"))
                    lp = context.new_page()
                    try:
                        details = _extract_competitive_details(lp, listing_url, start_date=start_date, timeout_ms=args.timeout_ms)
                        competitive_rows.append({
                            "listing_url": listing_url,
                            "listing_id": row.get("listing_id"),
                            "source_url": src_url,
                            **details,
                        })
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Failed competitive details for %s: %s", listing_url, exc)
                    finally:
                        lp.close()
                    _sleep_with_jitter(args.delay_seconds)
        browser.close()

    payload = {
        "sources": per_source,
        "total_sources": len(per_source),
        "total_listings": sum(s.get("count", 0) for s in per_source),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    persist_results_to_db(payload, args.db_path)
    if not args.skip_competitive_details:
        persist_competitive_to_db(competitive_rows, args.db_path)
    logger.info(
        "Wrote %s (%s sources, %s listings); updated database %s",
        out_path,
        payload["total_sources"],
        payload["total_listings"],
        args.db_path,
    )


if __name__ == "__main__":
    main()
