from __future__ import annotations
import base64,re
from pathlib import Path
from urllib.parse import quote,urlparse
import requests
API="https://api.github.com";MAX_SIZE=20*1024*1024
def parse_repository_url(value):
    p=urlparse((value or "").strip())
    if p.scheme!="https" or p.hostname not in {"github.com","www.github.com"}:raise ValueError("Use an HTTPS GitHub repository URL.")
    parts=[x for x in p.path.strip("/").split("/") if x]
    if len(parts)<2:raise ValueError("Repository URL must include owner and repository name.")
    owner,repo=parts[0],parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",repo):raise ValueError("Invalid repository URL.")
    return owner,repo
def upload_artifacts(repository_url,token,artifacts,account_label,job_id):
    owner,repo=parse_repository_url(repository_url)
    if not token or len(token)<20:raise ValueError("A GitHub personal access token is required.")
    h={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    r=requests.get(f"{API}/repos/{owner}/{repo}",headers=h,timeout=25)
    if r.status_code in (401,403,404):raise PermissionError("GitHub access failed. Check token and repository permissions.")
    r.raise_for_status();info=r.json()
    if info.get("permissions",{}).get("push") is False:raise PermissionError("Token/account does not have repository write access.")
    branch=info.get("default_branch") or "main";label=re.sub(r"[^A-Za-z0-9_.-]","_",account_label)[:60] or "account";uploaded=[];warnings=[]
    for a in artifacts:
        f=Path(a["path"]).resolve()
        if not f.is_file():warnings.append(f.name+": file missing");continue
        if f.stat().st_size>MAX_SIZE:warnings.append(f.name+": exceeds 20 MiB; use Git LFS or object storage");continue
        path=f"YouTube Video Analyser/{label}/{job_id}/{f.name}";endpoint=f"{API}/repos/{owner}/{repo}/contents/{quote(path,safe='/')}"
        old=requests.get(endpoint,headers=h,params={"ref":branch},timeout=25);sha=old.json().get("sha") if old.status_code==200 else None
        if old.status_code not in (200,404):old.raise_for_status()
        payload={"message":"Add YouTube Video Analyser artifact: "+f.name,"content":base64.b64encode(f.read_bytes()).decode(),"branch":branch}
        if sha:payload["sha"]=sha
        result=requests.put(endpoint,headers=h,json=payload,timeout=90)
        if result.status_code in (401,403):raise PermissionError("GitHub upload denied. Grant Contents: Read and write.")
        result.raise_for_status();uploaded.append(path)
    return {"uploaded":uploaded,"warnings":warnings}
