import os
import json
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import soundfile as sf

from app.db import get_db, init_db
from app.effects import schema_for_ui
from app.render import render

DATA_DIR = os.environ.get("DATA_DIR", "/data")
ORIGINALS_DIR = os.path.join(DATA_DIR, "originals")
RENDERED_DIR = os.path.join(DATA_DIR, "rendered")
os.makedirs(ORIGINALS_DIR, exist_ok=True)
os.makedirs(RENDERED_DIR, exist_ok=True)

# user soundfile to test the actual security of the audio file, just check extention
ALLOWED_EXTENSIONS = {".wav", ".flac", ".ogg", ".aiff", ".aif", ".mp3"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB cap

app = FastAPI(title="Audio FX Mutator")

@app.on_event("startup")
def startup():
    init_db()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# --- #effects:
@app.get("/api/effects")
def effects():
    return schema_for_ui()

# --- different sessions
@app.post("/api/sessions")
def create_session(payload: dict = Body(default={})):
    sid = uuid.uuid4().hex
    name = payload.get("name") or "Untitled Session"
    ts = now_iso()
    conn = get_db()
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sid, name, ts, ts))
    conn.commit(); conn.close()
    return {"id": sid, "name": name}

@app.get("/api/sessions")
def list_sessions():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    conn = get_db()
    s = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not s:
        conn.close(); raise HTTPException(404, "Session not found")
    tracks = conn.execute(
        "SELECT * FROM tracks WHERE session_id=? ORDER BY grid_row", (sid,)
    ).fetchall()
    conn.close()
    out = dict(s)
    out["tracks"] = [dict(t) for t in tracks]
    for t in out["tracks"]:
        t["chain"] = json.loads(t["chain_json"])  # parse recipe of effect chain for the client
    return out

# --- # upload and create tracks from audiofiles
@app.post("/api/sessions/{sid}/tracks")
async def create_track(sid: str, file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(ORIGINALS_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(data)
    try:
        info = sf.info(stored_path)
    except Exception:
        os.remove(stored_path)
        raise HTTPException(400, "File is not valid audio")

    tid = uuid.uuid4().hex
    conn = get_db()
    # grid_row = current track count, so the new tracks stack downward 
    count = conn.execute(
        "SELECT COUNT(*) c FROM tracks WHERE session_id=?", (sid,)
    ).fetchone()["c"]
    conn.execute(
        """INSERT INTO tracks
        (id, session_id, name, original_filename, rendered_filename,
         chain_json, grid_row, grid_col, duration_seconds, is_dirty, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (tid, sid, file.filename, stored_name, None, "[]",
         count, 0, info.duration, 0, now_iso()),
    )
    conn.commit(); conn.close()
    return {"id": tid, "original_name": file.filename,
            "stored_name": stored_name, "duration_seconds": info.duration,
            "chain": [], "is_dirty": False}


# --- # updates a tracks chain
@app.patch("/api/tracks/{tid}")
def update_track(tid: str, payload: dict = Body(...)):
    conn = get_db()
    t = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    if not t:
        conn.close(); raise HTTPException(404, "Track not found")
    chain = payload.get("chain")
    if chain is not None:
        conn.execute(
            "UPDATE tracks SET chain_json=?, is_dirty=1 WHERE id=?",
            (json.dumps(chain), tid))
    if "name" in payload:
        conn.execute("UPDATE tracks SET name=? WHERE id=?",
                     (payload["name"], tid))
    conn.commit(); conn.close()
    return {"ok": True}

# -- # render original file + chain into rendered cache
@app.post("/api/tracks/{tid}/render")
def render_track(tid: str):
    conn = get_db()
    t = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    if not t:
        conn.close(); raise HTTPException(404, "Track not found")
    chain = json.loads(t["chain_json"])
    original_path = os.path.join(ORIGINALS_DIR, t["original_filename"])
    rendered_name = f"{uuid.uuid4().hex}.wav"  # always write to WAV output for quality
    rendered_path = os.path.join(RENDERED_DIR, rendered_name)
    try:
        render(original_path, rendered_path, chain)
    except ValueError as e:
        conn.close(); raise HTTPException(400, str(e)) # bad chain, not crash

    # delete  previous rendered file if there was one (just a cache)
    if t["rendered_filename"]:
        old = os.path.join(RENDERED_DIR, t["rendered_filename"])
        if os.path.isfile(old):
            os.remove(old)
    conn.execute(
        "UPDATE tracks SET rendered_filename=?, is_dirty=0 WHERE id=?",
        (rendered_name, tid))
    conn.commit(); conn.close()
    return {"rendered_name": rendered_name}

# -- serve audio tracks
@app.get("/api/tracks/{tid}/audio")
def track_audio(tid: str):
    conn = get_db()
    t = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    conn.close()
    if not t:
        raise HTTPException(404, "Track not found")
    if t["rendered_filename"]:
        path = os.path.join(RENDERED_DIR, t["rendered_filename"])
    else:
        path = os.path.join(ORIGINALS_DIR, t["original_filename"])
    if not os.path.isfile(path):
        raise HTTPException(404, "Audio file missing")
    return FileResponse(path)

# -- # setup presets
@app.get("/api/presets")
def list_presets():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM presets ORDER BY created_at DESC").fetchall()
    conn.close()
    out = [dict(r) for r in rows]
    for p in out:
        p["chain"] = json.loads(p["chain_json"])
    return out

@app.post("/api/presets")
def create_preset(payload: dict = Body(...)):
    name = payload.get("name")
    chain = payload.get("chain")
    if not name or chain is None:
        raise HTTPException(400, "name and chain are required")
    # validate chain by building a board from it
    from app.render import build_board
    try:
        build_board(chain)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pid = uuid.uuid4().hex
    conn = get_db()
    conn.execute("INSERT INTO presets VALUES (?,?,?,?,?)",
                 (pid, name, "chain", json.dumps(chain), now_iso()))
    conn.commit(); conn.close()
    return {"id": pid, "name": name, "chain": chain}

# download the processed/original audio with a safe filename
@app.get("/api/tracks/{tid}/download")
def track_download(tid: str):
    conn = get_db()
    t = conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()
    conn.close()
    if not t:
        raise HTTPException(404, "Track not found")
    if t["rendered_filename"]:
        path = os.path.join(RENDERED_DIR, t["rendered_filename"])
        suffix = "_processed.wav"
    else:
        path = os.path.join(ORIGINALS_DIR, t["original_filename"])
        suffix = "_original" + os.path.splitext(t["original_filename"])[1]
    if not os.path.isfile(path):
        raise HTTPException(404, "Audio file missing")

    # give safe name
    download_name = "AudioMutateTrack_" + suffix

    return FileResponse(path, filename=download_name,
                        media_type="application/octet-stream")

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    # check the extention is valid 
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # read bytes within size bounding
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large")

    # store file under a generated UUID name, not user filename
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(ORIGINALS_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(data)

    # Let soundfile be the real validator and give us true metadata.
    # But if it cannot open the file, it is not really audio so delete
    try:
        info = sf.info(stored_path)
    except Exception:
        os.remove(stored_path)
        raise HTTPException(400, "File is not valid audio")

    return {
        "stored_name": stored_name,
        "original_name": file.filename,
        "duration_seconds": info.duration,
        "samplerate": info.samplerate,
        "channels": info.channels,
    }

# stream a stored original 
@app.get("/api/audio/{stored_name}")
def get_audio(stored_name: str):
    # use base file name to prevent path traversals lOl
    safe = os.path.basename(stored_name)
    path = os.path.join(ORIGINALS_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path)



app.mount("/", StaticFiles(directory="app/static", html=True), name="static")