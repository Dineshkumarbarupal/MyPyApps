from __future__ import annotations
import os,sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator,Any
USER_DIR=Path(__file__).resolve().parents[1]
DATA_DIR=Path(os.getenv("YTA_DATA_DIR",USER_DIR/"data")).expanduser()
DB_PATH=Path(os.getenv("YTA_DB_PATH",DATA_DIR/"app.sqlite3")).expanduser()
SCHEMA=USER_DIR/"db"/"schema.sql"
def connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH,timeout=20,check_same_thread=False);c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON");c.execute("PRAGMA busy_timeout=20000");return c
@contextmanager
def database()->Iterator[sqlite3.Connection]:
    c=connect()
    try:yield c;c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
def initialize_database():
    with database() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA.read_text(encoding="utf-8"))
        columns={row["name"] for row in c.execute("PRAGMA table_info(jobs)").fetchall()}
        if "output_dir" not in columns:
            c.execute("ALTER TABLE jobs ADD COLUMN output_dir TEXT NOT NULL DEFAULT ''")
def query_one(sql:str,params:tuple[Any,...]=()):
    with database() as c:
        row=c.execute(sql,params).fetchone();return dict(row) if row else None
def query_all(sql:str,params:tuple[Any,...]=()):
    with database() as c:return [dict(r) for r in c.execute(sql,params).fetchall()]
def execute(sql:str,params:tuple[Any,...]=()):
    with database() as c:return c.execute(sql,params).rowcount
