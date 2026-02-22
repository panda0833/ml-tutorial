#!/usr/bin/env python3
"""Simple UI to view Airbnb extracted listings from SQLite DB with demand calendar."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import re
import sqlite3
from pathlib import Path

from flask import Flask, render_template_string

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
DATE_RANGE_RE = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\s*[–-]\s*(\d{1,2})\b")

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Airbnb Listings Dashboard</title>
  <style>
    body { font-family: Inter, system-ui, -apple-system, sans-serif; background:#f7f8fb; margin:0; color:#1d2330; }
    .wrap { max-width: 1300px; margin: 32px auto; padding: 0 20px; }
    .card { background:white; border-radius:14px; box-shadow:0 6px 25px rgba(20,30,60,.08); padding:20px; margin-bottom:18px; }
    h1 { margin: 0 0 6px; }
    h2 { margin: 22px 0 10px; font-size: 18px; color:#223252; }
    .muted { color:#677189; margin-bottom: 18px; }
    table { width:100%; border-collapse: collapse; font-size:14px; margin-bottom: 22px; }
    th, td { padding: 10px 8px; border-bottom:1px solid #eef1f6; text-align:left; vertical-align:top; }
    th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:#5b667e; }
    .pill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; }
    .active { background:#dff7e8; color:#18794e; }
    .inactive { background:#fde7e9; color:#a61b2b; }
    a { color:#2457d6; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .section-meta { font-size:12px; color:#5f6d89; margin-bottom:8px; }

    .legend { display:flex; gap:10px; align-items:center; font-size:12px; color:#5f6d89; margin-bottom:12px; }
    .dot { width:12px; height:12px; border-radius:3px; display:inline-block; }
    .c0{background:#eef2f8;} .c1{background:#d8e9ff;} .c2{background:#9ec5ff;} .c3{background:#5a94f0;} .c4{background:#1f5ecb;}

    .months { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap:14px; }
    .month { border:1px solid #edf0f5; border-radius:10px; padding:10px; }
    .month h3 { margin: 0 0 8px; font-size:14px; color:#32425f; }
    .dow, .week { display:grid; grid-template-columns: repeat(7, 1fr); gap:4px; }
    .dow div { font-size:11px; color:#6d7892; text-align:center; }
    .day {
      height:34px; border-radius:6px; font-size:11px; display:flex; align-items:center; justify-content:center;
      border:1px solid #e8edf5; position:relative;
    }
    .empty { background:transparent; border-color:transparent; }
    .daynum { font-weight:600; }
    .count { position:absolute; bottom:2px; right:3px; font-size:9px; color:#21304e; opacity:.85; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Airbnb Listings Dashboard</h1>
      <div class="muted">Pulled from SQLite: <code>{{ db_path }}</code> · {{ total_rows }} listings · {{ groups|length }} sections</div>
    </div>

    <div class="card">
      <h2>Demand heat calendar (from active listing date ranges)</h2>
      <div class="legend">
        <span><span class="dot c0"></span> Low/no demand</span>
        <span><span class="dot c1"></span> Mild</span>
        <span><span class="dot c2"></span> Medium</span>
        <span><span class="dot c3"></span> High</span>
        <span><span class="dot c4"></span> Very high</span>
      </div>
      {% if calendars %}
      <div class="months">
        {% for m in calendars %}
          <div class="month">
            <h3>{{ m.label }}</h3>
            <div class="dow"><div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div><div>Sun</div></div>
            {% for week in m.weeks %}
              <div class="week">
                {% for d in week %}
                  {% if d.empty %}
                    <div class="day empty"></div>
                  {% else %}
                    <div class="day c{{ d.band }}" title="{{ d.iso }} demand={{ d.count }}">
                      <span class="daynum">{{ d.day }}</span>
                      <span class="count">{{ d.count }}</span>
                    </div>
                  {% endif %}
                {% endfor %}
              </div>
            {% endfor %}
          </div>
        {% endfor %}
      </div>
      {% else %}
        <div class="muted">No date-range demand data available yet.</div>
      {% endif %}
    </div>

    <div class="card">
      {% for g in groups %}
        <h2>{{ g.label }}</h2>
        <div class="section-meta">Source: <code>{{ g.source_url }}</code> · {{ g.rows|length }} listings</div>
        <table>
          <thead>
            <tr>
              <th>Active</th>
              <th>Listing</th>
              <th>Rating</th>
              <th>Reviews</th>
              <th>Price / Night</th>
              <th>Total Price</th>
              <th>Nights</th>
              <th>Date Range</th>
              <th>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {% for r in g.rows %}
            <tr>
              <td>
                {% if r['active'] %}
                  <span class="pill active">Active</span>
                {% else %}
                  <span class="pill inactive">Inactive</span>
                {% endif %}
              </td>
              <td><a href="{{ r['listing_url'] }}" target="_blank" rel="noreferrer">{{ r['listing_id'] }}</a></td>
              <td>{{ r['rating'] if r['rating'] is not none else '—' }}</td>
              <td>{{ r['review_count'] if r['review_count'] is not none else '—' }}</td>
              <td>{% if r['price_per_night'] is not none %}${{ '%.2f'|format(r['price_per_night']) }}{% else %}—{% endif %}</td>
              <td>{% if r['total_price'] is not none %}${{ r['total_price'] }}{% else %}—{% endif %}</td>
              <td>{{ r['nights'] if r['nights'] is not none else '—' }}</td>
              <td>{{ r['date_range_text'] or '—' }}</td>
              <td>{{ r['last_seen_at'] }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      {% endfor %}
    </div>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-path", default="data/airbnb_search_results.db")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    return p.parse_args()


def _expand_date_range(text: str, year: int) -> list[dt.date]:
    m = DATE_RANGE_RE.search(text or "")
    if not m:
        return []
    mon_abbr, start_day, end_day = m.groups()
    month = MONTHS.get(mon_abbr)
    if not month:
        return []

    start = dt.date(year, month, int(start_day))
    end = dt.date(year, month, int(end_day))
    if end < start:
        return []

    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += dt.timedelta(days=1)
    return dates


def _band(count: int, max_count: int) -> int:
    if max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio <= 0:
        return 0
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def build_calendars(rows: list[dict]) -> list[dict]:
    current_year = dt.date.today().year
    demand: dict[dt.date, int] = {}

    for r in rows:
        if not r.get("active"):
            continue
        for d in _expand_date_range(r.get("date_range_text") or "", current_year):
            demand[d] = demand.get(d, 0) + 1

    if not demand:
        return []

    min_date = min(demand)
    max_date = max(demand)
    max_count = max(demand.values())

    calendars: list[dict] = []
    ym = dt.date(min_date.year, min_date.month, 1)
    end_ym = dt.date(max_date.year, max_date.month, 1)

    cal = calendar.Calendar(firstweekday=0)  # Monday
    while ym <= end_ym:
        weeks = []
        for week in cal.monthdatescalendar(ym.year, ym.month):
            w = []
            for day in week:
                if day.month != ym.month:
                    w.append({"empty": True})
                else:
                    c = demand.get(day, 0)
                    w.append({
                        "empty": False,
                        "day": day.day,
                        "iso": day.isoformat(),
                        "count": c,
                        "band": _band(c, max_count),
                    })
            weeks.append(w)

        calendars.append({
            "label": ym.strftime("%B %Y"),
            "year": ym.year,
            "month": ym.month,
            "weeks": weeks,
        })

        # next month
        if ym.month == 12:
            ym = dt.date(ym.year + 1, 1, 1)
        else:
            ym = dt.date(ym.year, ym.month + 1, 1)

    return calendars


def load_grouped_rows(db_path: str) -> list[dict]:
    db_file = Path(db_path)
    if not db_file.exists():
        return []

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
        source_label_expr = "COALESCE(source_label, source_url)" if "source_label" in cols else "source_url"
        rows = conn.execute(
            f"""
            SELECT listing_id, listing_url, source_url,
                   {source_label_expr} AS source_label,
                   rating, review_count, date_range_text, total_price,
                   nights, price_per_night, active, last_seen_at
            FROM listings
            ORDER BY source_label ASC, active DESC, rating DESC, review_count DESC, listing_id ASC
            """
        ).fetchall()

    groups: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        label = d.get("source_label") or d.get("source_url") or "Unknown source"
        if label not in groups:
            groups[label] = {"label": label, "source_url": d.get("source_url"), "rows": []}
        groups[label]["rows"].append(d)

    return list(groups.values())


def main() -> None:
    args = parse_args()
    app = Flask(__name__)

    @app.route("/")
    def index():
        groups = load_grouped_rows(args.db_path)
        all_rows = [r for g in groups for r in g["rows"]]
        total_rows = len(all_rows)
        calendars = build_calendars(all_rows)
        return render_template_string(
            HTML,
            groups=groups,
            total_rows=total_rows,
            db_path=args.db_path,
            calendars=calendars,
        )

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
