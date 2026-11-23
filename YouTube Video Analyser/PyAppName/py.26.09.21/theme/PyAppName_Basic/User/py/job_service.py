from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from database import execute, query_all, query_one
from media_service import process_video, validate_youtube_url

logger = logging.getLogger(__name__)
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yta-media")


def _update(job_id, **fields):
    allowed = {"title", "status", "progress", "message", "artifacts_json", "error"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    if changes:
        assignment = ", ".join(key + "=?" for key in changes)
        execute(
            "UPDATE jobs SET " + assignment + ",updated_at=CURRENT_TIMESTAMP WHERE id=?",
            tuple(changes.values()) + (job_id,),
        )


def _run(job_id, user_id, url, options, output_dir):
    try:
        _update(job_id, status="processing", progress=1, message="Preparing video")
        result = process_video(
            url,
            options,
            str(Path(output_dir) / user_id),
            lambda percent, message: _update(job_id, progress=percent, message=message),
        )
        _update(
            job_id,
            title=result["title"],
            status=result["status"],
            progress=100 if result["status"] == "completed" else 98,
            message="; ".join(result["warnings"]) or "Selected outputs are ready",
            artifacts_json=json.dumps(result["artifacts"], ensure_ascii=False),
            error="; ".join(result["warnings"]),
        )
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        _update(job_id, status="failed", progress=0, message="Processing failed", error=str(exc))


def start_batch(user_id, urls_text, options, output_dir):
    urls = list(dict.fromkeys(line.strip() for line in (urls_text or "").splitlines() if line.strip()))
    if not urls:
        raise ValueError("Paste at least one YouTube URL.")
    if len(urls) > 10:
        raise ValueError("A batch can contain up to 10 unique URLs.")
    if not options.get("authorized"):
        raise PermissionError("Confirm that you own the videos or have permission to download/process them.")
    if not any(options.get(key) for key in ("transcript", "video", "audio")):
        raise ValueError("Select at least one output.")
    if options.get("cookies_browser") not in (None, "", "chrome", "edge", "firefox"):
        raise ValueError("Unsupported browser cookie source. Choose Chrome, Edge or Firefox.")
    for url in urls:
        validate_youtube_url(url)

    # Persist the exact output location on each job. Upload and recovery flows rely on it.
    resolved_output_dir = str(Path(output_dir).expanduser().resolve())
    job_ids = []
    for url in urls:
        job_id = str(uuid.uuid4())
        execute(
            """INSERT INTO jobs(id,user_id,url,status,options_json,output_dir)
               VALUES(?,?,?,'queued',?,?)""",
            (job_id, user_id, url, json.dumps(options), resolved_output_dir),
        )
        job_ids.append(job_id)
        pool.submit(_run, job_id, user_id, url, dict(options), resolved_output_dir)
    return job_ids


def list_jobs(user_id, limit=50):
    rows = query_all(
        "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    for row in rows:
        row["artifacts"] = json.loads(row.pop("artifacts_json") or "[]")
        row.pop("options_json", None)
    return rows


def get_job(user_id, job_id):
    row = query_one("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user_id))
    if not row:
        raise ValueError("Job was not found in this account.")
    row["artifacts"] = json.loads(row.pop("artifacts_json") or "[]")
    row.pop("options_json", None)
    return row
