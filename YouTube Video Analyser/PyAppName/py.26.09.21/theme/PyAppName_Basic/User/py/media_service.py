from __future__ import annotations
import html,logging,os,re,shutil,tempfile
from pathlib import Path
from urllib.parse import urlparse,parse_qs
logger=logging.getLogger(__name__)
HOSTS={"youtube.com","www.youtube.com","m.youtube.com","youtu.be"}
def validate_youtube_url(value):
    p=urlparse((value or "").strip());host=(p.hostname or "").lower()
    if p.scheme!="https" or host not in HOSTS:raise ValueError("Only HTTPS YouTube video URLs are accepted.")
    if host=="youtu.be":vid=p.path.strip("/").split("/")[0]
    elif p.path=="/watch":vid=parse_qs(p.query).get("v",[""])[0]
    else:
        parts=[x for x in p.path.split("/") if x];vid=parts[1] if len(parts)>1 and parts[0] in {"shorts","embed","live"} else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid or ""):raise ValueError("The URL does not contain a valid YouTube video ID.")
    return vid
def clean_vtt(content):
    lines=[];previous=""
    for raw in content.replace("\r","").split("\n"):
        line=raw.strip()
        if not line or line=="WEBVTT" or line.startswith(("NOTE","STYLE","REGION")) or "-->" in line or re.fullmatch(r"\d+",line):continue
        line=html.unescape(re.sub(r"<[^>]+>","",line)).strip();line=re.sub(r"\s+"," ",line)
        if line and line!=previous:lines.append(line);previous=line
    return "\n".join(lines)
def _safe_title(title,vid):
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",title or "youtube-video")
    return re.sub(r"\s+"," ",value).strip(" .")[:90] or vid
def process_video(url,options,output_dir,progress=None):
    import yt_dlp
    vid=validate_youtube_url(url);progress=progress or (lambda p,m:None)
    root=Path(output_dir).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    with yt_dlp.YoutubeDL({"quiet":True,"no_warnings":True,"skip_download":True,"socket_timeout":30,"retries":2}) as y:info=y.extract_info(url,download=False)
    title=info.get("title") or "YouTube video";folder=root/(_safe_title(title,vid)+" ["+vid+"]");folder.mkdir(parents=True,exist_ok=True)
    artifacts=[];warnings=[]
    def hook(stage,base,span):
        def report(d):
            if d.get("status")=="downloading":
                total=d.get("total_bytes") or d.get("total_bytes_estimate");done=d.get("downloaded_bytes",0)
                progress(base+span*min(99,done/total*100 if total else 0)/100,stage)
        return report
    if options.get("transcript"):
        try:
            cap=folder/"captions";cap.mkdir(exist_ok=True);progress(4,"Looking for captions")
            params={"quiet":True,"no_warnings":True,"skip_download":True,"writesubtitles":True,"writeautomaticsub":True,"subtitleslangs":["en","hi","en.*","hi.*"],"subtitlesformat":"vtt/best","outtmpl":str(cap/"caption.%(ext)s"),"socket_timeout":30,"retries":2}
            with yt_dlp.YoutubeDL(params) as y:y.download([url])
            transcript=""
            for f in sorted(cap.glob("*.vtt")):
                transcript=clean_vtt(f.read_text(encoding="utf-8",errors="replace"))
                if transcript:break
            source="YouTube captions"
            if not transcript and options.get("whisper_fallback",True):transcript=_whisper(url,progress);source="Faster-Whisper"
            if transcript:
                target=folder/"transcript.txt";target.write_text(f"Title: {title}\nVideo URL: {url}\nSource: {source}\n\n{transcript}\n",encoding="utf-8")
                artifacts.append({"kind":"transcript","path":str(target),"name":target.name})
            else:warnings.append("No captions available. Optional Faster-Whisper fallback can be installed.")
        except Exception as e:logger.exception("Caption extraction failed");warnings.append("Transcript: "+str(e))
    if options.get("video"):
        try:
            progress(10,"Downloading video")
            params={"quiet":True,"no_warnings":True,"format":"bv*+ba/b","merge_output_format":"mp4","outtmpl":str(folder/"video.%(ext)s"),"progress_hooks":[hook("Downloading video",10,80)],"socket_timeout":30,"retries":3,"continuedl":True}
            with yt_dlp.YoutubeDL(params) as y:y.download([url])
            results=[x for x in folder.glob("video.*") if x.is_file() and x.suffix not in {".part",".ytdl"}]
            if results:
                f=max(results,key=lambda x:x.stat().st_size);artifacts.append({"kind":"video","path":str(f),"name":f.name})
            else:warnings.append("Video download did not produce a final file.")
        except Exception as e:logger.exception("Video download failed");warnings.append("Video: "+str(e))
    if options.get("audio"):
        try:
            if not shutil.which("ffmpeg"):raise RuntimeError("FFmpeg not found on PATH; install FFmpeg to create MP3.")
            progress(12,"Downloading audio")
            params={"quiet":True,"no_warnings":True,"format":"bestaudio/best","outtmpl":str(folder/"audio.%(ext)s"),"postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],"progress_hooks":[hook("Downloading audio",12,80)],"socket_timeout":30,"retries":3,"continuedl":True}
            with yt_dlp.YoutubeDL(params) as y:y.download([url])
            target=folder/"audio.mp3"
            if target.exists():artifacts.append({"kind":"audio","path":str(target),"name":target.name})
            else:warnings.append("MP3 conversion did not produce a file.")
        except Exception as e:logger.exception("Audio download failed");warnings.append("Audio: "+str(e))
    count=sum(bool(options.get(k)) for k in ("transcript","video","audio"))
    status="completed" if len(artifacts)>=count else ("partial" if artifacts else "failed")
    progress(100 if status=="completed" else 98,"Completed" if status=="completed" else "Finished with warnings")
    return {"title":title,"status":status,"artifacts":artifacts,"warnings":warnings}
def _whisper(url,progress):
    try:from faster_whisper import WhisperModel
    except ImportError:return ""
    import yt_dlp
    tmp=Path(tempfile.mkdtemp(prefix="yta-whisper-"))
    try:
        with yt_dlp.YoutubeDL({"quiet":True,"format":"bestaudio/best","outtmpl":str(tmp/"audio.%(ext)s")}) as y:y.download([url])
        f=next((x for x in tmp.glob("audio.*") if x.is_file()),None)
        if not f:return ""
        model=WhisperModel(os.getenv("YTA_WHISPER_MODEL","small"),device="cpu",compute_type="int8")
        segments,_=model.transcribe(str(f),vad_filter=True)
        return "\n".join(s.text.strip() for s in segments if s.text.strip())
    finally:shutil.rmtree(tmp,ignore_errors=True)
