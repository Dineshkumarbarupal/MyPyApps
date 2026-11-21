from __future__ import annotations
import logging,os,shutil,subprocess,sys
from pathlib import Path
import eel
import auth_service,github_service,job_service,session_manager
from database import query_one,execute
log=logging.getLogger(__name__);USER_DIR=None;KEYRING="youtube-video-analyser"
def configure_api(user_dir):
    global USER_DIR;USER_DIR=user_dir.resolve()
def _user():return session_manager.require_user()
def _output(user):
    row=query_one("SELECT setting_value FROM user_settings WHERE user_id=? AND setting_key='output_dir'",(user["id"],))
    path=Path(row["setting_value"]).expanduser() if row else USER_DIR/"data"/"exports"
    path.mkdir(parents=True,exist_ok=True);return path.resolve()
def _error(e):
    log.exception("API request failed")
    return {"ok":False,"error":str(e) if isinstance(e,(ValueError,PermissionError,RuntimeError)) else "Operation failed. See data/logs/application.log."}
@eel.expose
def api_me():return {"ok":True,"user":session_manager.get_user()}
@eel.expose
def api_register(name,email,password):
    try:
        user,code=auth_service.register(name,email,password);session_manager.set_user(user);return {"ok":True,"user":user,"recovery_code":code}
    except Exception as e:return _error(e)
@eel.expose
def api_login(email,password):
    try:
        user=auth_service.login(email,password);session_manager.set_user(user);return {"ok":True,"user":user}
    except Exception as e:return _error(e)
@eel.expose
def api_reset_password(email,code,password):
    try:auth_service.reset_password(email,code,password);return {"ok":True}
    except Exception as e:return _error(e)
@eel.expose
def api_logout():session_manager.set_user(None);return {"ok":True}
@eel.expose
def api_start_batch(urls,options):
    try:
        u=_user();ids=job_service.start_batch(u["id"],urls,options or {},str(_output(u)))
        return {"ok":True,"job_ids":ids,"message":f"{len(ids)} video(s) added to the queue."}
    except Exception as e:return _error(e)
@eel.expose
def api_list_jobs():
    try:return {"ok":True,"jobs":job_service.list_jobs(_user()["id"])}
    except Exception as e:return _error(e)
@eel.expose
def api_get_settings():
    try:return {"ok":True,"output_dir":str(_output(_user()))}
    except Exception as e:return _error(e)
@eel.expose
def api_choose_directory():
    try:
        _user();import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk();root.withdraw();root.attributes("-topmost",True);chosen=filedialog.askdirectory(title="Choose a local output folder");root.destroy()
        return {"ok":True,"path":chosen}
    except Exception as e:return _error(e)
@eel.expose
def api_save_directory(path):
    try:
        u=_user();p=Path(path).expanduser().resolve()
        if not p.exists() or not p.is_dir():raise ValueError("Choose an existing folder.")
        execute("INSERT INTO user_settings(user_id,setting_key,setting_value) VALUES(?,'output_dir',?) ON CONFLICT(user_id,setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=CURRENT_TIMESTAMP",(u["id"],str(p)))
        return {"ok":True}
    except Exception as e:return _error(e)
@eel.expose
def api_token_status():
    try:
        u=_user()
        try:import keyring;saved=bool(keyring.get_password(KEYRING,u["id"]))
        except Exception:saved=False
        return {"ok":True,"saved":saved}
    except Exception as e:return _error(e)
@eel.expose
def api_upload_job(job_id,repo,token="",remember=False):
    try:
        u=_user();secret=(token or "").strip()
        if remember and secret:
            try:import keyring;keyring.set_password(KEYRING,u["id"],secret)
            except Exception:log.warning("OS keyring unavailable; token not saved")
        if not secret:
            try:import keyring;secret=keyring.get_password(KEYRING,u["id"]) or ""
            except Exception:secret=""
        job=job_service.get_job(u["id"],job_id)
        if job["status"] not in {"completed","partial"}:raise ValueError("Wait for processing to finish before uploading.")
        user_root=(_output(u)/u["id"]).resolve();artifacts=[]
        for a in job["artifacts"]:
            candidate=Path(a["path"]).resolve()
            if user_root not in candidate.parents:raise PermissionError("Artifact path failed account-isolation validation.")
            artifacts.append(a)
        if not artifacts:raise ValueError("This job has no finished output files.")
        result=github_service.upload_artifacts(repo,secret,artifacts,u["display_name"],job_id)
        return {"ok":True,"uploaded":len(result["uploaded"]),"warning":"; ".join(result["warnings"])}
    except Exception as e:return _error(e)
@eel.expose
def api_open_output(path):
    try:
        u=_user();candidate=Path(path).expanduser().resolve();root=(_output(u)/u["id"]).resolve()
        if root not in candidate.parents and candidate!=root:raise PermissionError("File is outside this account's output folder.")
        target=candidate if candidate.is_dir() else candidate.parent
        if sys.platform=="win32":os.startfile(str(target))
        elif sys.platform=="darwin":subprocess.Popen(["open",str(target)])
        else:subprocess.Popen(["xdg-open",str(target)])
        return {"ok":True}
    except Exception as e:return _error(e)
@eel.expose
def api_environment():
    try:
        _user()
        try:import yt_dlp;ytdlp=True
        except ImportError:ytdlp=False
        try:import faster_whisper;whisper=True
        except ImportError:whisper=False
        return {"ok":True,"ffmpeg":shutil.which("ffmpeg") is not None,"ytdlp":ytdlp,"whisper":whisper}
    except Exception as e:return _error(e)
