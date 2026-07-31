"""Load and apply the analytical views in `backend/sql/views/`.

    python -m app.sql_views apply
    python -m app.sql_views drop
    python -m app.sql_views list

One entry point used by both production and the test fixture, so the views under
test are byte-for-byte the views that serve the API. A second, test-only
definition would be the fastest way to ship a metric that passes its test and is
wrong in production.

Files are applied in filename order. The numeric prefix groups them by domain and
makes the order deterministic; no view currently depends on another, so ordering is
for readability rather than correctness.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal

VIEW_DIR = Path(__file__).resolve().parent.parent / "sql" / "views"


def view_files() -> list[Path]:
    return sorted(VIEW_DIR.glob("*.sql"))


def view_names() -> list[str]:
    """View name from filename: `10_v_headcount_monthly.sql` -> `v_headcount_monthly`."""
    names = []
    for path in view_files():
        stem = path.stem
        names.append(stem.split("_", 1)[1] if stem[0].isdigit() else stem)
    return names


def apply_views(session: Session) -> list[str]:
    """Drop every view, then recreate all of them. Idempotent.

    The drop is not optional. `CREATE OR REPLACE VIEW` can replace a view's *body* but
    cannot change its column list — adding, removing or reordering a column fails with
    `cannot change name of view column "x" to "y"`, which is a confusing way to be told
    the shape moved. Since view shapes change often while metrics are being built,
    dropping first makes the loader indifferent to that. Views are cheap metadata, so
    rebuilding all of them costs nothing measurable.
    """
    drop_views(session)
    applied: list[str] = []
    for path in view_files():
        sql = path.read_text(encoding="utf-8")
        session.execute(text(sql))
        applied.append(path.name)
    session.commit()
    return applied


def drop_views(session: Session) -> None:
    """Drop in reverse order, CASCADE so a dependent view cannot block the drop."""
    for name in reversed(view_names()):
        session.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
    session.commit()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage analytical SQL views.")
    parser.add_argument("action", choices=["apply", "drop", "list"])
    args = parser.parse_args(argv)

    if args.action == "list":
        for path in view_files():
            print(path.name)
        return 0

    with SessionLocal() as session:
        if args.action == "apply":
            applied = apply_views(session)
            print(f"applied {len(applied)} views")
            for name in applied:
                print(f"  {name}")
        else:
            drop_views(session)
            print(f"dropped {len(view_names())} views")
    return 0


if __name__ == "__main__":
    sys.exit(main())
