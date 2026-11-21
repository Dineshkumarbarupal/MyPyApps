from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import eel

import auth_service
import github_service
import job_service
import session_manager
from database import execute, query_all, query_one
from media_service import ffmpeg_source, find_ffmpeg_location

log = logging.getLogger(__name__)
USER_DIR: Path | None = None
KEYRING = "youtube-video-analyser"


def configure_api(user_dir: Path) -> None:
    global USER_DIR
    USER_DIR = user_dir.resolve()


def _user():
    return session_manager.require_user()


def _output(user):
    row = query_one(
        "SELECT setting_value FROM user_settings WHERE user_id=? AND setting_key='output_dir'",
        (user["id"],),
    )
    path = Path(row["setting_value"]).expanduser() if row else USER_DIR / "data" / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _error(error: Exception) -> dict:
    if isinstance(error, (ValueError, PermissionError, RuntimeError)):
        # Validation and permission failures are normal user-facing outcomes, not server faults.
        log.info("API request rejected: %s", error)
        return {"ok": False, "error": str(error)}
    log.exception("Unexpected API request failure")
    return {"ok": False, "error": "Operation failed. See data/logs/application.log for details."}


@eel.expose
def api_me():
    return {"ok": True, "user": session_manager.get_user()}


@eel.expose
def api_register(name, email, password):
    try:
        user, code = auth_service.register(name, email, password)
        session_manager.set_user(user)
        return {"ok": True, "user": user, "recovery_code": code}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_login(email, password):
    try:
        user = auth_service.login(email, password)
        session_manager.set_user(user)
        return {"ok": True, "user": user}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_reset_password(email, code, password):
    try:
        new_code = auth_service.reset_password(email, code, password)
        return {"ok": True, "recovery_code": new_code}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_logout():
    session_manager.set_user(None)
    return {"ok": True}


@eel.expose
def api_start_batch(urls, options):
    try:
        user = _user()
        jobs = job_service.start_batch(user["id"], urls, options or {}, str(_output(user)))
        return {"ok": True, "job_ids": jobs, "message": f"{len(jobs)} video(s) added to the queue."}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_list_jobs():
    try:
        return {"ok": True, "jobs": job_service.list_jobs(_user()["id"])}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_get_settings():
    try:
        return {"ok": True, "output_dir": str(_output(_user()))}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_choose_directory():
    try:
        _user()
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title="Choose a local output folder")
        root.destroy()
        return {"ok": True, "path": chosen}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_save_directory(path):
    try:
        user = _user()
        selected = Path(path).expanduser().resolve()
        if not selected.exists() or not selected.is_dir():
            raise ValueError("Choose an existing folder.")
        execute(
            """INSERT INTO user_settings(user_id,setting_key,setting_value)
               VALUES(?,'output_dir',?)
               ON CONFLICT(user_id,setting_key) DO UPDATE SET
               setting_value=excluded.setting_value, updated_at=CURRENT_TIMESTAMP""",
            (user["id"], str(selected)),
        )
        return {"ok": True}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_token_status():
    try:
        user = _user()
        try:
            import keyring
            saved = bool(keyring.get_password(KEYRING, user["id"]))
        except Exception:
            saved = False
        return {"ok": True, "saved": saved}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_upload_job(job_id, repo, token="", remember=False):
    try:
        user = _user()
        secret = (token or "").strip()
        if remember and secret:
            try:
                import keyring
                keyring.set_password(KEYRING, user["id"], secret)
            except Exception:
                log.warning("OS keyring unavailable; token was not saved.")
        if not secret:
            try:
                import keyring
                secret = keyring.get_password(KEYRING, user["id"]) or ""
            except Exception:
                secret = ""

        job = job_service.get_job(user["id"], job_id)
        if job["status"] not in {"completed", "partial"}:
            raise ValueError("Wait for processing to finish before uploading.")

        output_root = Path(job["output_dir"] or _output(user)).expanduser().resolve()
        user_root = (output_root / user["id"]).resolve()
        artifacts = []
        for artifact in job["artifacts"]:
            candidate = Path(artifact["path"]).resolve()
            if user_root not in candidate.parents:
                raise PermissionError("Artifact path failed account-isolation validation.")
            artifacts.append(artifact)
        if not artifacts:
            raise ValueError("This job has no finished output files.")

        result = github_service.upload_artifacts(repo, secret, artifacts, user["display_name"], job_id)
        return {"ok": True, "uploaded": len(result["uploaded"]), "warning": "; ".join(result["warnings"])}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_open_output(path):
    try:
        user = _user()
        candidate = Path(path).expanduser().resolve()
        rows = query_all("SELECT artifacts_json FROM jobs WHERE user_id=?", (user["id"],))
        allowed = set()
        for row in rows:
            for item in json.loads(row["artifacts_json"] or "[]"):
                try:
                    allowed.add(Path(item["path"]).resolve())
                except (KeyError, TypeError):
                    continue
        if candidate not in allowed:
            raise PermissionError("File is not one of this account's saved job artifacts.")

        target = candidate.parent
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True}
    except Exception as exc:
        return _error(exc)


@eel.expose
def api_environment():
    try:
        _user()
        try:
            import yt_dlp  # noqa: F401
            ytdlp = True
        except ImportError:
            ytdlp = False
        try:
            import faster_whisper  # noqa: F401
            whisper = True
        except ImportError:
            whisper = False
        ffmpeg_path = find_ffmpeg_location()
        return {
            "ok": True,
            "ffmpeg": bool(ffmpeg_path),
            "ffmpeg_source": ffmpeg_source(),
            "ffmpeg_path": ffmpeg_path or "",
            "ytdlp": ytdlp,
            "whisper": whisper,
        }
    except Exception as exc:
        return _error(exc)
