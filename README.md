# LiveStoryBook: AI Audio animated ebook from scanned book

Turn a scanned kindergarten picture book into a live **animated audio e-book**:
clean the printed text off each page, generate a short looping animation with
**Wan** image-to-video, narrate with **Qwen TTS**, and re-type the words in place
in the reader, synced to the voice.

## Repository layout

| Folder | What it is |
|---|---|
| `ebook_app/` | **The web app** (Flask server + pipeline + reader UI). This is the main deliverable — see `ebook_app/README.md`. |
| `AI_Audio_Picture_Book_Studio.pptx` | Pitch deck (opens cleanly in Google Slides). |
| `Three Little Pigs (Ladybird) - rescaled.pdf` | Sample source book used in the demo. |
| `test_book.pdf` | Minimal 3-page test book. |
| `ebook/` | Early single-page proof-of-concept (one animated page + its narration). |
| `pipeline/` | Standalone `generate_page.py` — the original per-page generation script. |
| `pdf-craft-main/` | Vendored reference for the PDF text-detection approach (OOMOL pdf-craft). |

## Quick start (the app)

```
cd ebook_app
pip install -r requirements.txt
set DASHSCOPE_API_KEY=sk-...     # Alibaba Cloud Model Studio / DashScope key
python app.py                    # open http://127.0.0.1:8140
```

Or with Docker: `docker compose up --build -d` (see `ebook_app/README.md`).

## What's NOT committed

Generated book media (`ebook_app/data/` — hundreds of MB of mp4/mp3/png), runtime
logs, caches, and `.env` are excluded via `.gitignore`. Put your API key in `.env`
or pass it through the UI; never commit it.
