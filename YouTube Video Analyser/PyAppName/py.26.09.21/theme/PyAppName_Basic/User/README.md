# YouTube Video Analyser

A local-first Windows desktop app built with HTML, CSS, JavaScript, Python, Eel and SQLite.

## Phase 1 features
- Local sign-up/sign-in and account-specific job history/output directories.
- Password reset using a one-time recovery code (no email service required).
- Batch input for up to 10 YouTube URLs; 2 background workers.
- Transcript extraction from available YouTube captions; optional Faster-Whisper fallback.
- Optional MP4 and MP3 output (MP3 and merge require FFmpeg).
- User-selectable local output folder.
- Upload completed artifacts to a GitHub repository through a fine-grained PAT.
- Modular templates, HTML components, per-component CSS and Python services.

## Windows install
Python 3.10+, Chrome, and FFmpeg on PATH are recommended.

    py -3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    python main.py

Optional speech-recognition fallback:

    pip install faster-whisper

The first Whisper use downloads a model. Default is small; set YTA_WHISPER_MODEL=base for a smaller model.

## GitHub uploads
Create a fine-grained PAT limited to the target repository with **Contents: Read and write** permission. Enter it in the app. “Remember token” stores it in the operating system keyring when supported; it is not stored in SQLite. The GitHub Contents API upload is limited to 20 MiB per individual artifact; use Git LFS or object storage for larger media. Do not upload confidential or copyrighted material without rights.

## Account and data
Accounts are local to this installation and do not sync between computers. Save the one-time recovery code shown after registration. The app stores only its salted hash. SQLite is stored in data/app.sqlite3 and files default to data/exports/<user-id>/. The data folder is git-ignored.

## Important limitations
This is a Phase 1 desktop foundation, not a verified capacity claim of 10,000 remote users/hour. A local desktop process serves one interactive user; real multi-user scale needs a separate hosted API, identity service, queue and shared database. Jobs are local and in-flight work stops if the app closes. No production load test, installer, code signing, email verification, or cloud sync is included.

Only process/download videos you own or are authorized to use. Follow YouTube's terms, copyright law and applicable policies. Captions may be unavailable and downloads may be blocked for some videos.
