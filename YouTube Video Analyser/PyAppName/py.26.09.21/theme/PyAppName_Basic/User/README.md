# YouTube Video Analyser

A local-first Windows desktop app built with HTML, CSS, JavaScript, Python, Eel and SQLite.

## Phase 1 features
- Local sign-up/sign-in and account-specific job history/output directories.
- Password reset using a one-time recovery code (no email service required).
- Batch input for up to 10 YouTube URLs; 2 background workers.
- Transcript extraction from available YouTube captions; optional Faster-Whisper fallback.
- Optional video and MP3 output, with bundled FFmpeg discovery.
- Optional Chrome, Edge or Firefox cookie session (explicit opt-in) for YouTube requests.
- User-selectable local output folder.
- Upload completed artifacts to a GitHub repository through a fine-grained PAT.
- Modular templates, HTML components, per-component CSS and Python services.

## Update an existing Windows environment

Run these commands in the same virtual environment that starts the app:

    python -m pip install --upgrade pip
    python -m pip install --upgrade yt-dlp
    python -m pip install -r requirements.txt

The requirements now include imageio-ffmpeg, which provides a bundled FFmpeg executable for MP3 conversion and video/audio merging. If your organization blocks binary package installation, install FFmpeg separately and set YTA_FFMPEG_LOCATION to its executable or containing folder.

Then restart the desktop app:

    python main.py

Optional speech-recognition fallback:

    python -m pip install faster-whisper

The first Whisper use downloads a model. Default is small; set YTA_WHISPER_MODEL=base for a smaller model.

## YouTube HTTP 429 rate limits

HTTP 429 means YouTube has temporarily rate-limited the requesting connection. The app now reports this as a job warning instead of dumping a long traceback and continues with the other selected outputs. Do not repeatedly retry a rate-limited request.

If YouTube presents a CAPTCHA or account prompt, open YouTube manually in Chrome, Edge or Firefox and complete the prompt. Then select that same browser in the app's optional browser-session selector. This explicitly allows yt-dlp to use the selected local browser session. Close the browser first if its cookie database is reported as locked. Browser cookies are not copied into app storage. This may help when YouTube requests a verified session, but does not guarantee that a rate limit has cleared. See the [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#http-error-429-too-many-requests-or-402-payment-required).

## GitHub uploads

Create a fine-grained PAT limited to the target repository with **Contents: Read and write** permission. Enter it in the app. “Remember token” stores it in the operating system keyring when supported; it is not stored in SQLite. The GitHub Contents API upload is limited to 20 MiB per individual artifact; use Git LFS or object storage for larger media. Do not upload confidential or copyrighted material without rights.

## Account and data

Accounts are local to this installation and do not sync between computers. Save the one-time recovery code shown after registration. The app stores only its salted hash. SQLite is stored in data/app.sqlite3 and files default to data/exports/<user-id>/. The data folder is git-ignored.

## Important limitations

This is a Phase 1 desktop foundation, not a verified capacity claim of 10,000 remote users/hour. A local desktop process serves one interactive user; real multi-user scale needs a separate hosted API, identity service, queue and shared database. Jobs are local and in-flight work stops if the app closes. No production load test, installer, code signing, email verification, or cloud sync is included.

Only process/download videos you own or are authorized to use. Follow YouTube's terms, copyright law and applicable policies. Captions may be unavailable and downloads may be blocked for some videos.
