#!/usr/bin/env python3
"""Simple UI to view Airbnb extracted listings from SQLite DB.

Run:
  python src/airbnb_dashboard.py --db-path data/airbnb_search_results.db --port 8080
Then open http://localhost:8080
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from flask import Flask, render_template_string

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Airbnb Listings Dashboard</title>
  <style>
    body { font-family: Inter, system-ui, -apple-system, sans-serif; background:#f7f8fb; margin:0; color:#1d2330; }
    .wrap { max-width: 1200px; margin: 32px auto; padding: 0 20px; }
    .card { background:white; border-radius:14px; box-shadow:0 6px 25px rgba(20,30,60,.08); padding:20px; }
    h1 { margin: 0 0 6px; }
    .muted { color:#677189; margin-bottom: 18px; }
    table { width:100%; border-collapse: collapse; font-size:14px; }
    th, td { padding: 10px 8px; border-bottom:1px solid #eef1f6; text-align:left; }
    th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:#5b667e; }
    .pill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:600; }
    .active { background:#dff7e8; color:#18794e; }
    .inactive { background:#fde7e9; color:#a61b2b; }
    a { color:#2457d6; text-decoration:none; }
    a:hover { text-decoration:underline; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Airbnb Listings Dashboard</h1>
      <div class="muted">Pulled from SQLite: <code>{{ db_path }}</code> · {{ rows|length }} listings</div>
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
            <th>Source</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {% for r in rows %}
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
            <td style="max-width:260px; overflow-wrap:anywhere;">{{ r['source_url'] }}</td>
            <td>{{ r['last_seen_at'] }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
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


def load_rows(db_path: str) -> list[dict]:
    db_file = Path(db_path)
    if not db_file.exists():
        return []

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT listing_id, listing_url, source_url, rating, review_count,
                   date_range_text, total_price, nights, price_per_night,
                   active, last_seen_at
            FROM listings
            ORDER BY active DESC, rating DESC, review_count DESC, listing_id ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    args = parse_args()
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML, rows=load_rows(args.db_path), db_path=args.db_path)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
