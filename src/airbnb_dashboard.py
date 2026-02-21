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
    .wrap { max-width: 1300px; margin: 32px auto; padding: 0 20px; }
    .card { background:white; border-radius:14px; box-shadow:0 6px 25px rgba(20,30,60,.08); padding:20px; }
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
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Airbnb Listings Dashboard</h1>
      <div class="muted">Pulled from SQLite: <code>{{ db_path }}</code> · {{ total_rows }} listings · {{ groups|length }} sections</div>

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
        total_rows = sum(len(g["rows"]) for g in groups)
        return render_template_string(HTML, groups=groups, total_rows=total_rows, db_path=args.db_path)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
