"""ترحيل قاعدة البيانات: يضيف عمودَي full_text و full_text_fetched_at.

آمن للتكرار (idempotent) — يتحقق من وجود العمود قبل إضافته.

التشغيل محليًا مرة واحدة:
    python scripts/migrate_fulltext.py --db data/midya.db --table articles

عدّل مسار القاعدة واسم الجدول حسب مشروعك.
"""
from __future__ import annotations

import argparse
import sqlite3

COLUMNS = [
    ("full_text", "TEXT"),
    ("full_text_fetched_at", "TEXT"),
]


def column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def migrate(db_path: str, table: str) -> None:
    if not table.isidentifier():
        raise ValueError(f"اسم جدول غير صالح: {table!r}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    if not cur.fetchone():
        conn.close()
        raise SystemExit(f"الجدول {table!r} غير موجود في {db_path}")

    added = []
    for col, col_type in COLUMNS:
        if not column_exists(cur, table, col):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            added.append(col)

    conn.commit()
    conn.close()
    print("أُضيف:", ", ".join(added) if added else "لا شيء — الأعمدة موجودة مسبقًا")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="مسار ملف قاعدة SQLite")
    parser.add_argument("--table", default="articles", help="اسم جدول المقالات")
    args = parser.parse_args()
    migrate(args.db, args.table)
