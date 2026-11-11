# AI Audio E-Book — Progress

Project: an animated audio picture-book website. Per content page: narration (TTS) + a ~3s
animation whose motion follows the page text. A "Next" button flips pages. Front / author / last
pages are static. The narration text is **typed word-by-word directly on the page, in place**,
synced to the voice (no bottom subtitle bar).

## Status (2026-11-11)
- Working site in `ebook/` (open `ebook/index.html`, or serve it: `python -m http.server` in `ebook/`).
- Sample page done = *The Three Little Pigs* — **"Splash! And that was the end of the big, bad wolf."**
  - `ebook/assets/page1_narration.mp3`  (Qwen3-TTS, voice Cherry)
  - `ebook/assets/page1.mp4`            (Wan i2v from a TEXT-FREE image, ~3.0s, lively motion)
  - `ebook/assets/page1_frame.jpg`      (clean poster — printed text removed, used as video source)
- Reusable generator: `pipeline/generate_page.py` (also copied into `ebook/`).

## In-place typing (this iteration)
- Text detection: `qwen3-vl-plus` grounding returns per-line boxes (normalized 0-1000). Verified
  aligned to the printed text (left page, upper area).
- Text removal: OpenCV `inpaint` (Telea) over the padded boxes erases the printed glyphs while keeping
  the illustration -> the video has NO baked-in text, so our typed text sits cleanly on top.
- Frontend: each line is positioned/sized from its box relative to the rendered media (container aspect
  matches the video aspect 128/97 so normalized coords map 1:1). Words reveal over the narration
  duration proportional to character length, with a blinking caret.
- Inspired by pdf-craft (github.com/oomol-lab/pdf-craft): it detects book text via OCR and, when writing
  translated text back onto a page, MASKS the source glyphs and preserves the graphics. We mirror that.

## API key
- At `D:\RTH\alibaba.md` (first line). Never hardcode the value. Scoped to the **international**
  endpoint `dashscope-intl.aliyuncs.com`; the China host returns 401.

## Page-number fix (latest)
- Bug: the story-text detection deliberately ignored page numbers, so they stayed in the source image
  and the image-to-video model garbled them (right corner "27" became "20"). Root cause = small text
  left in the frame that the video model can't keep stable, NOT a detection miss per se.
- Fix: detect the page-number boxes too, erase them from the source (mask only the dark digit ink +
  OpenCV inpaint, so page texture is preserved and no white patch appears), regenerate the video from
  the fully text-free image, and re-draw crisp "26"/"27" as static overlays in the frontend
  (`layout.pageNumbers`). `generate_page.py` now does this automatically for every page.

## Verified capabilities / decisions
- **TTS:** CosyVoice NOT available on this key ("Model not exist"; WebSocket API, SDK defaults to China
  WS host). Using **Qwen3-TTS `qwen3-tts-flash`** (returns a hosted audio URL to download).
- **Vision/OCR:** `qwen3-vl-plus` grounding works (via compatible-mode). Boxes are normalized 0-1000 ->
  rescale by width/1000, height/1000; approximate (+/-10-20px) but fine for masking/positioning.
- **Text removal:** NO inpaint model on this key (`image-erase-completion`, `wanx2.1-imageedit` = "Model
  not exist"). Used OpenCV inpaint locally instead — clean results on the white paper area.
- **Video:** `wan2.5-i2v-preview` works (single `img_url`; SDK auto-uploads local file; poll `fetch`).
  Input images must be downscaled (an 8220x6234 RGBA scan is rejected). Duration 3 supported.
- **Loop:** the "first frame == last frame" constraint was removed per user request; plain i2v for lively
  natural motion, trimmed to 3s.

## How to add a page
```
set DASHSCOPE_API_KEY=...   (or keep it in D:\RTH\alibaba.md)
python pipeline/generate_page.py --image page2.png --id page2
```
It auto-detects the text, removes it, narrates, animates, and prints a `MANIFEST_ENTRY=...` JSON.
Paste that entry into the `pages` array in `ebook/data.js` (between cover and author pages).

## Environment notes (Windows box)
- ffmpeg at `C:\Users\User\AppData\Local\Programs\ffmpeg7\bin` (on PATH). PIL, cv2 (opencv-python-headless
  5.0), numpy available.
- System proxy intercepts localhost -> verify local servers with Python `urllib`, not curl.
- After swapping media assets, hard-refresh (Ctrl+F5) — the browser caches the old video.

## Full workflow app (latest)
- Built a Flask web app in `ebook_app/` implementing the end-to-end workflow:
  Upload a scanned PDF -> preview pages + toggle which to animate (cover/author/last off) ->
  background job generates each animated page (detect text+numbers, erase, Qwen-TTS, Wan i2v, ffmpeg)
  -> store the finished book -> read it in the built-in reader (in-place typing + video + static pages).
- Right-side **Upload** and **Storage** buttons; footer tag "Powered by QwenWork · Wan2.7 · Qwen TTS".
- API key field: prefilled from `D:\RTH\alibaba.md` for the current user, empty for new users; also
  remembered in `data/config.json`. Used server-side for all DashScope calls.
- Run: `pip install -r requirements.txt` then `python app.py` (http://127.0.0.1:8140).
- Files: `app.py` (Flask + job manager), `pipeline.py` (generation functions), `templates/index.html`,
  `static/style.css`, `static/app.js`, `requirements.txt`, `README.md`. Books stored under `data/books/`.
- Verified end-to-end with a 2-page test PDF (cover skipped as static image; spread animated with
  narration + 3s video + in-place typing + crisp page numbers). Fixed a lock deadlock (LOCK is now RLock).

## Next steps
- Supply real multi-page books to batch-generate.
- Optional: exact word timing via forced alignment / TTS timestamps (currently proportional to length).
- Optional: real page-turn using the StPageFlip library already in this folder; production WSGI + auth.
