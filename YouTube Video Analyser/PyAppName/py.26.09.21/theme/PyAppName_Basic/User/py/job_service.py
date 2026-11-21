from __future__ import annotations
import json,logging,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from database import execute,query_all,query_one
from media_service import process_video,validate_youtube_url
logger=logging.getLogger(__name__);pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix="yta-media")
def _update(job_id,**fields):
    allowed={"title","status","progress","message","artifacts_json","error"};changes={k:v for k,v in fields.items() if k in allowed}
    if changes:
        sql=", ".join(k+"=?" for k in changes);execute("UPDATE jobs SET "+sql+",updated_at=CURRENT_TIMESTAMP WHERE id=?",tuple(changes.values())+(job_id,))
def _run(job_id,user_id,url,options,outdir):
    try:
        _update(job_id,status="processing",progress=1,message="Preparing video")
        result=process_video(url,options,str(Path(outdir)/user_id),lambda p,m:_update(job_id,progress=p,message=m))
        _update(job_id,title=result["title"],status=result["status"],progress=100 if result["status"]=="completed" else 98,message="; ".join(result["warnings"]) or "Selected outputs are ready",artifacts_json=json.dumps(result["artifacts"]),error="; ".join(result["warnings"]))
    except Exception as e:
        logger.exception("Job %s failed",job_id);_update(job_id,status="failed",progress=0,message="Processing failed",error=str(e))
def start_batch(user_id,urls_text,options,output_dir):
    urls=list(dict.fromkeys(x.strip() for x in (urls_text or "").splitlines() if x.strip()))
    if not urls:raise ValueError("Paste at least one YouTube URL.")
    if len(urls)>10:raise ValueError("A batch can contain up to 10 unique URLs.")
    if not options.get("authorized"):raise PermissionError("Confirm that you own the videos or have permission to process them.")
    if not any(options.get(k) for k in ("transcript","video","audio")):raise ValueError("Select at least one output.")
    for url in urls:validate_youtube_url(url)
    ids=[]
    for url in urls:
        jid=str(uuid.uuid4())
        execute("INSERT INTO jobs(id,user_id,url,status,options_json,output_dir) VALUES(?,?,?,'queued',?,?)",(jid,user_id,url,json.dumps(options),str(Path(output_dir).expanduser().resolve())))
        ids.append(jid);pool.submit(_run,jid,user_id,url,dict(options),output_dir)
    return ids
def list_jobs(user_id,limit=50):
    rows=query_all("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",(user_id,limit))
    for row in rows:row["artifacts"]=json.loads(row.pop("artifacts_json") or "[]");row.pop("options_json",None)
    return rows
def get_job(user_id,job_id):
    row=query_one("SELECT * FROM jobs WHERE id=? AND user_id=?",(job_id,user_id))
    if not row:raise ValueError("Job was not found in this account.")
    row["artifacts"]=json.loads(row.pop("artifacts_json") or "[]");row.pop("options_json",None);return row
