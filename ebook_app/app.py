import os, io, json, time, threading, uuid, traceback
from flask import Flask, request, jsonify, send_from_directory, send_file
import pipeline as P

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(APP_DIR, "data")
BOOKS = os.path.join(DATA, "books")
UPLOADS = os.path.join(DATA, "uploads")
for d in (DATA, BOOKS, UPLOADS): os.makedirs(d, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
LOCK = threading.RLock()  # reentrant: run_job holds it while save_meta() re-acquires it

KEY_FILE = os.environ.get("KEY_FILE", r"D:\RTH\alibaba.md")
CONFIG = os.path.join(DATA, "config.json")

def default_key():
    # env var (Docker) > remembered key file > local key file path (empty for new users)
    k = os.environ.get("DASHSCOPE_API_KEY")
    if k: return k.strip()
    if os.path.exists(CONFIG):
        try:
            k = json.load(open(CONFIG)).get("api_key")
            if k: return k
        except Exception: pass
    try:
        with open(KEY_FILE, encoding="utf-8") as f: return f.readline().strip()
    except Exception: return ""

def save_key(k):
    if k:
        json.dump({"api_key": k}, open(CONFIG, "w"))

def book_dir(bid): return os.path.join(BOOKS, bid)
def meta_path(bid): return os.path.join(book_dir(bid), "meta.json")
def load_meta(bid):
    p = meta_path(bid)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
def save_meta(m):
    with LOCK: json.dump(m, open(meta_path(m["id"]), "w", encoding="utf-8"))

# ---------------- routes ----------------
@app.get("/")
def index(): return send_file(os.path.join(APP_DIR, "templates", "index.html"))

@app.get("/api/config")
def api_config():
    return jsonify({"defaultKey": default_key(), "hasKey": bool(default_key())})

@app.post("/api/upload")
def api_upload():
    f = request.files.get("pdf")
    if not f: return jsonify({"error": "no file"}), 400
    api_key = (request.form.get("api_key") or "").strip() or default_key()
    if not api_key: return jsonify({"error": "missing API key"}), 400
    save_key(api_key)
    bid = uuid.uuid4().hex[:10]
    bdir = book_dir(bid); os.makedirs(os.path.join(bdir, "pages"), exist_ok=True)
    os.makedirs(os.path.join(bdir, "thumbs"), exist_ok=True)
    os.makedirs(os.path.join(bdir, "assets"), exist_ok=True)
    pdf_path = os.path.join(UPLOADS, f"{bid}.pdf")
    f.save(pdf_path)
    try:
        pages = P.render_pdf_pages(pdf_path, os.path.join(bdir, "pages"),
                                   thumb_dir=os.path.join(bdir, "thumbs"))
    except Exception as e:
        return jsonify({"error": f"PDF render failed: {e}"}), 500
    meta = {"id": bid, "title": os.path.splitext(f.filename)[0], "created": int(time.time()),
            "status": "ready", "total": len(pages), "done": 0, "animate": [], "error": None,
            "pages": [{"index": p["index"], "thumb": f"books/{bid}/thumbs/page{p['index']+1:03d}.png"}
                      for p in pages]}
    save_meta(meta)
    return jsonify({"book_id": bid, "title": meta["title"],
                    "pages": [{"index": p["index"], "thumb": p["thumb"]} for p in meta["pages"]]})

@app.post("/api/generate")
def api_generate():
    d = request.get_json(force=True)
    bid = d.get("book_id"); animate = d.get("animate", [])
    api_key = (d.get("api_key") or "").strip() or default_key()
    voice = d.get("voice", "Cherry")
    if not api_key: return jsonify({"error": "missing API key"}), 400
    m = load_meta(bid)
    if not m: return jsonify({"error": "unknown book"}), 404
    m["animate"] = animate; m["api_key"] = api_key; m["voice"] = voice
    m["status"] = "processing"; m["done"] = 0; m["error"] = None
    save_meta(m)
    threading.Thread(target=run_job, args=(bid, api_key, voice, animate), daemon=True).start()
    return jsonify({"ok": True, "book_id": bid})

def run_job(bid, api_key, voice, animate):
    def log(msg):
        try: open(os.path.join(book_dir(bid), "job.log"), "a", encoding="utf-8").write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except Exception: pass
    log(f"START animate={animate}")
    m = load_meta(bid); assets = os.path.join(book_dir(bid), "assets")
    pages_dir = os.path.join(book_dir(bid), "pages")
    manifest_pages = []
    try:
        # Pass 1: OCR all pages to build a ~100-word book summary (story context for the animation prompts)
        log("summarizing book")
        texts = []
        for p in m["pages"]:
            try:
                d = P.detect_text(api_key, os.path.join(pages_dir, f"page{p['index']+1:03d}.png"))
                if d.get("text"): texts.append(d["text"])
            except Exception as e:
                log(f"summary OCR skip {p['index']}: {e}")
        summary = P.summarize_book(api_key, m["title"], " ".join(texts))
        log("summary: " + ((summary[:80] + "...") if summary else "(none)"))

        # Pass 2: generate each page
        for p in m["pages"]:
            i = p["index"]; pid = f"page{i+1}"; page_png = os.path.join(pages_dir, f"page{i+1:03d}.png")
            log(f"page {i} start ({'animate' if i in animate else 'static'})")
            if i in animate:
                entry = P.process_animated_page(api_key, page_png, assets, pid, voice, summary=summary)
            else:
                entry = {"type": "image", "id": pid, "image": f"pages/page{i+1:03d}.png"}
            manifest_pages.append(entry)
            with LOCK:
                m["done"] += 1; m["progress"] = m["done"] / m["total"]; save_meta(m)
            log(f"page {i} done")
        json.dump({"title": m["title"], "pages": manifest_pages},
                  open(os.path.join(book_dir(bid), "manifest.json"), "w", encoding="utf-8"))
        with LOCK: m["status"] = "done"; save_meta(m)
    except Exception as e:
        log(f"ERROR {e}"); traceback.print_exc()
        with LOCK: m["status"] = "error"; m["error"] = str(e); save_meta(m)

@app.get("/api/status/<bid>")
def api_status(bid):
    m = load_meta(bid)
    if not m: return jsonify({"error": "unknown"}), 404
    return jsonify({k: m.get(k) for k in ("id", "title", "status", "total", "done", "progress", "error")})

@app.get("/api/books")
def api_books():
    out = []
    if os.path.isdir(BOOKS):
        for bid in os.listdir(BOOKS):
            m = load_meta(bid)
            if m: out.append({k: m.get(k) for k in ("id", "title", "status", "total", "done", "created")})
    out.sort(key=lambda x: x.get("created", 0), reverse=True)
    return jsonify(out)

@app.delete("/api/books/<bid>")
def api_delete_book(bid):
    """Soft-delete: move the book folder to data/trash (recoverable), not permanent removal."""
    import shutil
    d = book_dir(bid)
    if not os.path.isdir(d): return jsonify({"error": "unknown book"}), 404
    m = load_meta(bid)
    if m and m.get("status") == "processing":
        return jsonify({"error": "book is generating; wait until done"}), 409
    trash = os.path.join(DATA, "trash"); os.makedirs(trash, exist_ok=True)
    dest = os.path.join(trash, f"{int(time.time())}_{bid}")
    shutil.move(d, dest)
    return jsonify({"ok": True, "moved_to": os.path.relpath(dest, DATA)})

@app.get("/api/book/<bid>")
def api_book(bid):
    p = os.path.join(book_dir(bid), "manifest.json")
    if not os.path.exists(p): return jsonify({"error": "not ready"}), 404
    return send_file(p)

@app.get("/books/<bid>/<path:sub>")
def serve_book(bid, sub):
    return send_from_directory(book_dir(bid), sub)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8140"))
    app.run(host="0.0.0.0", port=port, threaded=True)
