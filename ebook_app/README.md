# AI Audio Picture Book Studio

Turn a scanned picture-book PDF into an animated audio e-book.

For each page you choose to animate, the app:
1. detects the printed story text + page numbers (Qwen3-VL grounding),
2. erases that text from the page (OpenCV inpaint) so the artwork is clean,
3. narrates the text (Qwen TTS / `qwen3-tts-flash`),
4. generates a ~3s animation whose motion follows the text (Wan image-to-video `wan2.5-i2v`),
5. rebuilds the text in the e-book reader as **word-by-word typing in place**, synced to the voice,
   with crisp static page numbers re-drawn on top.

Pages you leave OFF (cover / author / last) are shown as-is.

## Run — Docker (recommended)
```
docker compose up --build -d        # builds image + starts container
# open http://localhost:8140   (hard-refresh Ctrl+F5 after any rebuild)
```
- The container can't read `D:\RTH\alibaba.md`, so the API key comes from either:
  - the **UI field** (pasted once, remembered in the mounted `data/config.json`), or
  - an env var: set `DASHSCOPE_API_KEY=...` before `docker compose up`.
- Generated books + the saved key persist in the mounted `./data` volume across rebuilds.
- Rebuild after code changes: `docker compose up --build -d` (then Ctrl+F5 — the browser caches the old UI).

## Run — local (no Docker)
```
pip install -r requirements.txt
set DASHSCOPE_API_KEY=sk-...   (or keep the key in D:\RTH\alibaba.md)
python app.py                  # http://127.0.0.1:8140
```

## Using it
- **Upload** button (top right): paste your Qwen/DashScope API key (prefilled with the local key in
  `D:\RTH\alibaba.md`; empty for new users), choose a PDF, preview the pages, click any page to toggle
  animation, then **Generate**. Watch progress, then **Read the e-book**.
- **Storage** button (top right): your finished books; click **Read**.
- Finished books are stored under `data/books/<id>/` (manifest.json + assets).

## Notes
- The API key is used server-side for the DashScope calls. This is a local development server
  (`127.0.0.1` only) — do not expose it publicly without adding auth.
- Video generation takes ~1-3 minutes per animated page; pages process sequentially in a background job.
- Credits shown in the footer: QwenWork · Wan2.7 · Qwen TTS.
