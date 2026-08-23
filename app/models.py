"""Backwards-compatible shim: storage lives in app/db.py (stdlib sqlite3)."""
from .db import (all_generations, get_conn, get_credibility_map,  # noqa: F401
                 insert_article, insert_cluster, insert_generation,
                 list_generations, update_generation)
