"""E-book generation pipeline (DashScope international endpoint).
Pure functions; the caller passes the API key so different users can use their own."""
import os, json, time, base64, subprocess, urllib.request

BASE = "https://dashscope-intl.aliyuncs.com/api/v1"
COMPAT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def render_pdf_pages(pdf_path, out_dir, max_dim=1400, thumb_dir=None, thumb_w=260):
    """Render each PDF page to a PNG at a controlled resolution. Returns list of
    {index, full, thumb}. (Scanned pages can be enormous, so we cap the render size.)"""
    import pymupdf
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None  # scanned books legitimately exceed the default bomb limit
    os.makedirs(out_dir, exist_ok=True)
    if thumb_dir: os.makedirs(thumb_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        rect = page.rect
        scale = max_dim / max(rect.width, rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        full = os.path.join(out_dir, f"page{i+1:03d}.png")
        pix.save(full)
        thumb = full
        if thumb_dir:
            im = Image.open(full); w, h = im.size; s = thumb_w / w
            t = os.path.join(thumb_dir, f"page{i+1:03d}.png")
            im.resize((thumb_w, int(h*s)), Image.LANCZOS).save(t)
            thumb = t
        pages.append({"index": i, "full": full, "thumb": thumb})
    return pages


def _vl(key, frame_jpg, prompt):
    data_url = "data:image/jpeg;base64," + base64.b64encode(open(frame_jpg, "rb").read()).decode()
    body = json.dumps({"model": "qwen3-vl-plus", "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}}, {"type": "text", "text": prompt}]}]}).encode()
    req = urllib.request.Request(COMPAT + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=90).read())
            return r["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 2: raise
            time.sleep(3)


def detect_text(key, frame_jpg):
    prompt = ("Find the printed STORY TEXT of this picture-book page (the narrative sentence). "
              "IGNORE page numbers and any word inside the artwork. Return ONLY JSON: "
              '{"text":"<full sentence>","lines":[{"text":"<line>","box":[x1,y1,x2,y2]}]} '
              "with boxes in 0-1000 normalized coords, lines top-to-bottom.")
    txt = _vl(key, frame_jpg, prompt); s = txt.find("{"); e = txt.rfind("}") + 1
    return json.loads(txt[s:e])


def detect_page_numbers(key, frame_jpg):
    prompt = ("Find the small printed PAGE NUMBERS in the bottom corners of this opened two-page book "
              "spread (bottom-left and bottom-right). Ignore story text. Return ONLY JSON: "
              '{"numbers":[{"text":"<number>","box":[x1,y1,x2,y2]}]} with boxes in 0-1000 normalized coords.')
    txt = _vl(key, frame_jpg, prompt); s = txt.find("{"); e = txt.rfind("}") + 1
    try: return json.loads(txt[s:e]).get("numbers", [])
    except Exception: return []


def remove_text(frame_jpg, clean_jpg, boxes, max_side=1280):
    """Downscale, mask only the dark ink strokes inside each box, inpaint -> text-free image."""
    import cv2, numpy as np
    from PIL import Image
    im = Image.open(frame_jpg).convert("RGB"); w, h = im.size; s = max_side / max(w, h)
    if s < 1: im = im.resize((int(w*s), int(h*s)), Image.LANCZOS)
    im.save(frame_jpg.replace(".png", "_res.jpg"), quality=92)
    img = cv2.imread(im and frame_jpg.replace(".png", "_res.jpg")); H, W = img.shape[:2]
    mask = np.zeros((H, W), np.uint8)
    for x1, y1, x2, y2 in boxes:
        X1, Y1 = max(0, int(x1/1000*W-14)), max(0, int(y1/1000*H-14))
        X2, Y2 = min(W, int(x2/1000*W+14)), min(H, int(y2/1000*H+14))
        sub = img[Y1:Y2, X1:X2]; g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        thr = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 8)
        thr = cv2.dilate(thr, np.ones((3, 3), np.uint8), iterations=2)
        mask[Y1:Y2, X1:X2] = np.maximum(mask[Y1:Y2, X1:X2], thr)
    out = cv2.inpaint(img, mask, 6, cv2.INPAINT_NS)
    cv2.imwrite(clean_jpg, out, [cv2.IMWRITE_JPEG_QUALITY, 92])


def make_narration(key, text, out_mp3, voice="Cherry"):
    body = json.dumps({"model": "qwen3-tts-flash",
                       "input": {"text": text, "voice": voice, "language_type": "English"}}).encode()
    req = urllib.request.Request(BASE + "/services/aigc/multimodal-generation/generation", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    url = d["output"]["audio"]["url"].replace("http://", "https://")
    open(out_mp3, "wb").write(urllib.request.urlopen(url, timeout=60).read())


def make_video(key, clean_jpg, prompt, out_mp4, duration=3, poll_cb=None,
               model="wan2.5-i2v-preview", ratio=None):
    import dashscope
    from dashscope.aigc.video_synthesis import VideoSynthesis
    dashscope.base_http_api_url = BASE; dashscope.api_key = key
    # Some models (wan2.7-i2v, happyhorse-*) use input.media=[{type:"first_frame",url}];
    # wan2.5 / wan3.0 use img_url. wan2.7-i2v preserves the input image aspect automatically.
    if model.startswith("wan2.7") or model.startswith("happyhorse"):
        r = VideoSynthesis.async_call(model=model,
                                      media=[{"type": "first_frame", "url": clean_jpg}],
                                      prompt=prompt, duration=duration)
    else:
        kw = {"img_url": clean_jpg, "prompt": prompt, "resolution": "480P", "duration": duration}
        if ratio: kw["ratio"] = ratio
        r = VideoSynthesis.async_call(model=model, **kw)
    if r.status_code != 200:
        raise RuntimeError(f"video submit failed: {getattr(r,'code',None)} {getattr(r,'message',None)}")
    tid = r.output["task_id"]
    while True:
        time.sleep(12)
        if poll_cb: poll_cb(tid)
        f = VideoSynthesis.fetch(tid); st = f.output.get("task_status")
        if st == "SUCCEEDED":
            raw = out_mp4 + ".raw.mp4"
            urllib.request.urlretrieve(f.output["video_url"].replace("http://", "https://"), raw)
            subprocess.run(["ffmpeg", "-y", "-t", str(duration), "-i", raw, "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "20", "-an", out_mp4], capture_output=True)
            os.remove(raw); return
        if st == "FAILED":
            raise RuntimeError(f"video failed: {f.output.get('code')} {f.output.get('message')}")


# Option B: enumerate ONLY what is actually drawn, then build a grounded motion prompt.
# (Never uses the story text; the VLM only reports visible subjects, so it can't seed a hallucination.)
def _chat(key, model, prompt):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(COMPAT + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            return r["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == 2: raise
            time.sleep(3)


def summarize_book(key, title, story_text, model="qwen-plus"):
    """~100-word summary that names the book and captures the plot, for animation context."""
    prompt = ("Summarize this children's picture book in about 100 words, and state the book's title. "
              "The summary is for an animator, so capture the plot and mood. "
              "Title: " + str(title) + "\nText from the pages:\n" + (story_text or "(no text captured)") +
              "\nReturn a single ~100-word paragraph that names the book and describes the story.")
    return _chat(key, model, prompt)


def motion_prompt_from_story(key, frame_jpg, summary):
    """qwen-VL writes a lively 5s motion prompt for THIS page that fits the story, animating the
    visible characters AND the environment physics, without ever introducing new characters."""
    instruction = (
        "You are an animation director for a children's picture book. "
        "Write ONE image-to-video motion prompt that animates THIS page's illustration for a "
        "5-second clip in a way that fits the story below. "
        "1) Characters: describe SMOOTH, rhythmic motion for the characters/creatures that are ACTUALLY "
        "DRAWN and fully visible in the image — e.g. dancing in place, gentle bouncing, small arm waves, "
        "slight head turns — choosing actions that suit the scene. Put the lively action on the main, "
        "fully-visible characters. "
        "2) Environment physics: gentle motion of the environment that is present — soft flames flickering, "
        "steam or smoke drifting upward, small ripples or bubbles, curtains/leaves swaying lightly. "
        "HARD RULES: Only animate characters, creatures and objects that are ALREADY visible in the image. "
        "NEVER introduce any new character, animal, person, or body part that is not drawn (even if the "
        "story mentions them). For SMALL or PARTIALLY-visible figures (e.g. legs or hands sticking out of a "
        "pot), keep them ESSENTIALLY STILL \u2014 at most a barely-"
        "perceptible motion; do NOT make them kick, flap, wave or move a lot, because that makes them "
        "melt and distort. Keep the motion SLOW, smooth and temporally stable: every character and "
        "object must KEEP ITS EXACT ORIGINAL SHAPE and anatomy for the whole clip \u2014 do not melt, "
        "morph, merge, dissolve, or reshape anything. Keep the camera static (locked-off shot, no "
        "pan/zoom/drift). Maintain visual consistency with the initial frame. Return ONLY the motion "
        "prompt text, 40-80 words.")
    txt = _vl(key, frame_jpg, instruction + "\n\nBOOK SUMMARY:\n" + (summary or "(none)"))
    return txt.strip().strip('"').strip()


def visible_elements(key, frame_jpg):
    prompt = ("You are deciding what should ANIMATE in a picture-book page. List ONLY: "
              "(a) the MAIN characters or creatures that are the focus of the scene, and which body "
              "parts are visible (e.g. 'three pigs, full bodies', 'two legs sticking out of a pot'); "
              "and (b) the clearly DYNAMIC elements only — fire/flames, boiling water or steam, moving "
              "liquid, or wind-blown curtains. Do NOT list static objects, furniture, decorations, "
              "portraits, photos, props, or background details. Return ONLY JSON: "
              '{"subjects":["..."],"environment":["..."]}. Never mention anything not visible in the image.')
    txt = _vl(key, frame_jpg, prompt); s = txt.find("{"); e = txt.rfind("}") + 1
    try:
        d = json.loads(txt[s:e]); return d.get("subjects", []), d.get("environment", [])
    except Exception:
        return [], []


def build_motion_prompt(subjects, env):
    subj = ", ".join(subjects) if subjects else "the characters already visible in the image"
    envi = ", ".join(env) if env else "fire, water, steam, fabric"
    return ("static locked-off shot, zero camera drift or panning. "
            "Only these elements already visible in the image may move: " + subj + ". "
            "They perform small, lively in-place movements \u2014 gentle bobbing, swaying, and limb "
            "gestures \u2014 without changing position or the scene. Environmental motion: " + envi +
            " moves softly with natural physics. Do not introduce any character, animal, person, or "
            "body part not listed above. Maintain visual consistency with the initial frame.")


def process_animated_page(key, page_png, assets_dir, page_id, voice="Cherry", summary=None):
    """Run the full pipeline for one animated page. Returns a manifest entry."""
    os.makedirs(assets_dir, exist_ok=True)
    frame = os.path.join(assets_dir, f"{page_id}_frame.jpg")   # clean poster / video source
    det = detect_text(key, page_png)
    nums = detect_page_numbers(key, page_png)
    text = det.get("text", "")
    boxes = [ln["box"] for ln in det.get("lines", [])] + [n["box"] for n in nums]
    remove_text(page_png, frame, boxes)
    mp3 = os.path.join(assets_dir, f"{page_id}_narration.mp3")
    if text: make_narration(key, text, mp3, voice)
    mp4 = os.path.join(assets_dir, f"{page_id}.mp4")
    if summary:
        prompt = motion_prompt_from_story(key, frame, summary)
    else:
        subjects, env = visible_elements(key, frame)
        prompt = build_motion_prompt(subjects, env)
    make_video(key, frame, prompt, mp4, duration=5, model="wan2.7-i2v")
    return {"type": "content", "id": page_id, "text": text,
            "video": f"assets/{page_id}.mp4", "poster": f"assets/{page_id}_frame.jpg",
            "audio": (f"assets/{page_id}_narration.mp3" if text else None),
            "layout": {"lines": det.get("lines", []), "pageNumbers": nums}}
