import sqlite3

from database import DB_PATH, initialize_database, query_one


def test_initialize_database_adds_output_dir_to_existing_jobs_table(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr("database.DB_PATH", database_path)

    # Simulate a database created by the previous schema, before output_dir existed.
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE jobs(
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                options_json TEXT NOT NULL DEFAULT '{}',
                artifacts_json TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """INSERT INTO jobs(id,user_id,url,status)
               VALUES('existing-job','existing-user','https://youtu.be/dQw4w9WgXcQ','queued')"""
        )

    initialize_database()

    row = query_one("SELECT id, output_dir FROM jobs WHERE id=?", ("existing-job",))
    assert row == {"id": "existing-job", "output_dir": ""}

    # Migration must be safe to run on every application startup.
    initialize_database()
    columns = {row["name"] for row in sqlite3.connect(database_path).execute("PRAGMA table_info(jobs)")}
    assert "output_dir" in columns
