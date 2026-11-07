"""Bethlehem University Student Assistant: a RAG web app.

Run:  python app.py   then open http://127.0.0.1:5000
"""
import json
import re
import sys
import threading
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import config
from db import connect, init_db
from ingest import SUPPORTED, TEXT_TYPES, index_file, sync_data_folder
from llm import LLMError, answer, plan_queries
from search import INDEX, hybrid_retrieve
from textnorm import is_arabic

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
)
_index_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- helpers
def err(message: str, code: int = 400):
    return jsonify({"error": message}), code


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return err("Please log in.", 401)
        if request.method != "GET" and request.headers.get("X-Requested-With") != "fetch":
            return err("Bad request.", 400)  # simple CSRF protection for JSON endpoints
        return fn(*args, **kwargs)
    return wrapper


def allowed_doc_ids(conn, user_id: int) -> set:
    rows = conn.execute(
        "SELECT id FROM documents WHERE status = 'ready' AND (visibility = 'shared' OR owner_id = ?)", (user_id,)
    ).fetchall()
    return {r["id"] for r in rows}


def doc_json(row, user_id) -> dict:
    return {
        "id": row["id"], "filename": row["filename"], "pages": row["pages"], "chunks": row["chunks"],
        "status": row["status"], "source": row["source"], "visibility": row["visibility"], "kind": row["kind"],
        "mine": row["owner_id"] == user_id, "created_at": row["created_at"],
    }


def resync() -> dict:
    with _index_lock:
        with connect() as conn:
            summary = sync_data_folder(conn)
        INDEX.rebuild()
    return summary


# ---------------------------------------------------------------- pages
@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------- auth
@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or len(name) > 100:
        return err("Please enter your name.")
    if not EMAIL_RE.match(email):
        return err("Please enter a valid email address.")
    if len(password) < 8:
        return err("Password must be at least 8 characters.")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return err("An account with this email already exists.", 409)
        cur = conn.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                           (name, email, generate_password_hash(password)))
        user_id = cur.lastrowid
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    return jsonify({"user": {"id": user_id, "name": name, "email": email}})


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], data.get("password") or ""):
        return err("Wrong email or password.", 401)
    session.clear()
    session.permanent = True
    session["user_id"] = row["id"]
    return jsonify({"user": {"id": row["id"], "name": row["name"], "email": row["email"]}})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"user": None})
    with connect() as conn:
        row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not row:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": dict(row)})


# ---------------------------------------------------------------- documents
@app.get("/api/documents")
@login_required
def list_documents():
    uid = session["user_id"]
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE visibility = 'shared' OR owner_id = ? ORDER BY source, filename", (uid,)
        ).fetchall()
    return jsonify({"documents": [doc_json(r, uid) for r in rows]})


@app.post("/api/documents")
@login_required
def upload_document():
    uid = session["user_id"]
    f = request.files.get("file")
    if not f or not f.filename:
        return err("Choose a file to upload.")
    original = Path(f.filename.replace("\\", "/")).name[:200]
    ext = Path(original).suffix.lower()
    if ext not in SUPPORTED:
        return err("Unsupported file type. Allowed: " + ", ".join(sorted(SUPPORTED)))
    head = f.stream.read(8)
    f.stream.seek(0)
    if ext == ".pdf" and not head.startswith(b"%PDF-"):
        return err("This file is not a valid PDF.")
    if ext in (".docx", ".pptx", ".xlsx") and not head.startswith(b"PK"):
        return err("This file is not a valid Office document.")
    visibility = "shared" if request.form.get("share") == "true" else "private"
    user_dir = config.UPLOAD_DIR / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{uuid.uuid4().hex}{ext}"  # original name (incl. Arabic) is kept in the DB
    f.save(path)
    try:
        with _index_lock:
            with connect() as conn:
                row = index_file(conn, path, filename=original, owner_id=uid, visibility=visibility, source="upload")
                conn.commit()
            INDEX.rebuild()
    except Exception as exc:
        path.unlink(missing_ok=True)
        return err(f"Could not read this file: {exc}")
    doc = doc_json(row, uid)
    if row["status"] == "no_text":
        doc["warning"] = ("No text could be extracted. If this is a scanned PDF, "
                          "run it through OCR first so its text can be searched.")
    return jsonify({"document": doc})


@app.delete("/api/documents/<int:doc_id>")
@login_required
def delete_document(doc_id):
    uid = session["user_id"]
    with _index_lock:
        with connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row or row["owner_id"] != uid:
                return err("You can only delete files you uploaded.", 403)
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        Path(row["stored_path"]).unlink(missing_ok=True)
        INDEX.rebuild()
    return jsonify({"ok": True})


@app.get("/api/documents/<int:doc_id>/file")
@login_required
def get_document_file(doc_id):
    uid = session["user_id"]
    with connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row or not (row["visibility"] == "shared" or row["owner_id"] == uid):
        return err("Not found.", 404)
    ext = Path(row["stored_path"]).suffix.lower()
    name = Path(row["filename"]).name
    if ext == ".pdf":
        resp = send_file(row["stored_path"], mimetype="application/pdf", download_name=name, as_attachment=False)
    elif ext in TEXT_TYPES:
        # always served as plain text (never as HTML) so uploaded files cannot run scripts in the site
        resp = send_file(row["stored_path"], mimetype="text/plain", download_name=name, as_attachment=False)
    else:
        resp = send_file(row["stored_path"], download_name=name, as_attachment=True)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.post("/api/rescan")
@login_required
def rescan():
    return jsonify(resync())


# ---------------------------------------------------------------- chat
@app.get("/api/history")
@login_required
def history():
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content, refs_json FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 60",
            (session["user_id"],),
        ).fetchall()
    msgs = [{"role": r["role"], "content": r["content"], "refs": json.loads(r["refs_json"] or "[]")}
            for r in reversed(rows)]
    return jsonify({"messages": msgs})


@app.post("/api/history/clear")
@login_required
def clear_history():
    with connect() as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (session["user_id"],))
    return jsonify({"ok": True})


@app.post("/api/ask")
@login_required
def ask():
    uid = session["user_id"]
    question = ((request.get_json(silent=True) or {}).get("question") or "").strip()
    if not question:
        return err("Please type a question.")
    if len(question) > 2000:
        return err("Question is too long (max 2000 characters).")

    with connect() as conn:
        hist = [dict(r) for r in conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 6", (uid,)
        ).fetchall()][::-1]
        allowed = allowed_doc_ids(conn, uid)

    try:
        plan = plan_queries(question, hist)
        language = plan["language"] or ("ar" if is_arabic(question) else "en")
        standalone = plan["standalone_question"]
        queries = [question, standalone] + plan["queries"]
        chunk_ids = hybrid_retrieve(queries, allowed, config.TOP_K) if allowed else []

        chunks = []
        if chunk_ids:
            with connect() as conn:
                marks = ",".join("?" * len(chunk_ids))
                rows = {r["chunk_id"]: dict(r) for r in conn.execute(
                    f"SELECT c.id AS chunk_id, c.document_id, c.page, c.section, c.location, c.text, d.filename,"
                    f" d.pages, d.kind, d.visibility FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id IN ({marks})",
                    chunk_ids,
                ).fetchall()}
            chunks = [rows[c] for c in chunk_ids if c in rows]
        result = answer(standalone, language, chunks)
    except LLMError as exc:
        return err(str(exc), 502)

    with connect() as conn:
        conn.execute("INSERT INTO messages (user_id, role, content) VALUES (?,?,?)", (uid, "user", question))
        conn.execute("INSERT INTO messages (user_id, role, content, refs_json) VALUES (?,?,?,?)",
                     (uid, "assistant", result["text"], json.dumps(result["refs"], ensure_ascii=False)))
    return jsonify({
        "answer": result["text"], "refs": result["refs"], "idk": result["idk"],
        "language": language, "searched_chunks": len(chunks),
    })


@app.errorhandler(413)
def too_large(_e):
    return err(f"File too large (max {config.MAX_UPLOAD_MB} MB).", 413)


def startup():
    for stream in (sys.stdout, sys.stderr):  # never crash on Arabic file names in a Windows console
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    init_db()
    s = resync()
    with connect() as conn:
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"[index] data folder: {config.DATA_DIR}")
    print(f"[index] added {len(s['added'])}, updated {len(s['updated'])}, removed {len(s['removed'])}, "
          f"failed {len(s['failed'])}; total {n_docs} documents / {n_chunks} chunks")
    for f in s["failed"]:
        print("  [failed]", f)
    print(f"[ai] provider: {config.PROVIDER} | answer model: {config.ANSWER_MODEL} | query model: {config.QUERY_MODEL}")
    if not config.API_KEY:
        print("[warning] No API key found. Put it in the .env file (API_KEY=...)")


startup()

if __name__ == "__main__":
    print(f"Open http://{'127.0.0.1' if config.HOST == '0.0.0.0' else config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, threaded=True)
