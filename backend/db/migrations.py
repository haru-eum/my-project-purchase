"""앱 시작 시 DB 정합성 보정."""

import sqlite3

INDUSTRY_TAB_ORDER = ["Automotive", "Pharma", "Energy"]

MIGRATION_MAP = {
    1: "Automotive", 2: "Automotive", 3: "Automotive", 4: "Automotive",
    5: "Energy", 6: "Energy", 7: "Energy",
    8: "Pharma", 9: "Pharma", 10: "Pharma",
    11: "Automotive", 12: "Energy", 13: "Energy",
}


def ensure_material_category_integrity(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    categories = [
        row[0] for row in cur.execute("SELECT DISTINCT category FROM RawMaterials").fetchall()
    ]
    if any(cat in INDUSTRY_TAB_ORDER for cat in categories):
        return
    for material_id, category in MIGRATION_MAP.items():
        cur.execute(
            "UPDATE RawMaterials SET category = ? WHERE material_id = ?",
            (category, material_id),
        )
    conn.commit()
