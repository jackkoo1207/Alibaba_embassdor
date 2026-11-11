"""
AI audio e-book page generator  (DashScope international endpoint)
------------------------------------------------------------------
For one picture-book content page (illustration + its printed text) it produces:
  1. text detection   -> qwen3-vl-plus grounding  (line boxes, normalized 0-1000)
  2. text removal      -> OpenCV inpaint over the text boxes  => CLEAN illustration
  3. narration audio   -> Qwen3-TTS (qwen3-tts-flash)          [CosyVoice NOT on this key]
  4. ~3s animation     -> Wan image-to-video (wan2.5-i2v-preview) FROM THE CLEAN image
  5. a manifest entry with `layout.lines` for in-place, word-by-word typing synced to audio

Why this design (pdf-craft inspired): pdf-craft detects book text via OCR and, when writing
translated text back onto a page, MASKS OUT the source glyphs and preserves the graphics.
We do the same: erase the printed text so the video has no baked-in text, then re-type the
narration word-by-word exactly where it was, timed to the voice.

Usage:
  set DASHSCOPE_API_KEY, or keep the key in D:\RTH\alibaba.md (first line).
  python generate_page.py --image page2.png --id page2 --voice Cherry
  # --text is auto-read from the page via OCR if not supplied
"""
import os, sys, json, time, base64, argparse, subprocess, urllib.request

BASE = "https://dashscope-intl.aliyuncs.com/api/v1"
COMPAT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

def get_key():
    k = os.environ.get("DASHSCOPE_API_KEY")
    if k:
        return k.strip()
    with open(r"D:\RTH\alibaba.md", encoding="utf-8") as f:
        return f.readline().strip()

def resize_frame(src, out_jpg, max_side=1280):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1])
    w, h = bg.size; s = max_side / max(w, h)
    bg = bg.resize((int(w*s), int(h*s)), Image.LANCZOS)
    bg.save(out_jpg, quality=92)
    return bg.size

def detect_text(key, frame_jpg):
    """Return {text, lines:[{text, box:[x1,y1,x2,y2] normalized 0-1000}]}"""
    data_url = "data:image/jpeg;base64," + base64.b64encode(open(frame_jpg, "rb").read()).decode()
    prompt = ("Find the printed STORY TEXT of this picture-book page (the narrative sentence). "
              "IGNORE page numbers and any word inside the artwork. Return ONLY JSON: "
              '{"text":"<full sentence>","lines":[{"text":"<line>","box":[x1,y1,x2,y2]}]} '
              "with boxes in 0-1000 normalized coords, lines top-to-bottom.")
    body = json.dumps({"model": "qwen3-vl-plus", "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}}, {"type": "text", "text": prompt}]}]}).encode()
    req = urllib.request.Request(COMPAT + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    txt = r["choices"][0]["message"]["content"]
    s = txt.find("{"); e = txt.rfind("}") + 1
    return json.loads(txt[s:e])

def remove_text(frame_jpg, clean_jpg, boxes):
    """Erase by masking ONLY the dark ink pixels within each box (keeps page texture),
    then OpenCV inpaint. `boxes` is a list of [x1,y1,x2,y2] (normalized 0-1000)."""
    import cv2, numpy as np
    img = cv2.imread(frame_jpg); H, W = img.shape[:2]
    mask = np.zeros((H, W), np.uint8)
    for x1, y1, x2, y2 in boxes:
        X1, Y1 = max(0, int(x1/1000*W-14)), max(0, int(y1/1000*H-14))
        X2, Y2 = min(W, int(x2/1000*W+14)), min(H, int(y2/1000*H+14))
        sub = img[Y1:Y2, X1:X2]; g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        thr = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 8)
        thr = cv2.dilate(thr, np.ones((3, 3), np.uint8), iterations=2)
        mask[Y1:Y2, X1:X2] = np.maximum(mask[Y1:Y2, X1:X2], thr)
    cv2.imwrite(clean_jpg, cv2.inpaint(img, mask, 6, cv2.INPAINT_NS), [cv2.IMWRITE_JPEG_QUALITY, 92])

def detect_page_numbers(key, frame_jpg):
    """Return list of {text, box} for the small page numbers in the bottom corners."""
    data_url = "data:image/jpeg;base64," + base64.b64encode(open(frame_jpg, "rb").read()).decode()
    prompt = ("Find the small printed PAGE NUMBERS in the bottom corners of this opened two-page book "
              "spread (bottom-left and bottom-right). Ignore story text. Return ONLY JSON: "
              '{"numbers":[{"text":"<number>","box":[x1,y1,x2,y2]}]} with boxes in 0-1000 normalized coords.')
    body = json.dumps({"model": "qwen3-vl-plus", "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}}, {"type": "text", "text": prompt}]}]}).encode()
    req = urllib.request.Request(COMPAT + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    txt = r["choices"][0]["message"]["content"]; s = txt.find("{"); e = txt.rfind("}") + 1
    try:
        return json.loads(txt[s:e]).get("numbers", [])
    except Exception:
        return []

def make_narration(key, text, out_mp3, voice="Cherry"):
    body = json.dumps({"model": "qwen3-tts-flash",
                       "input": {"text": text, "voice": voice, "language_type": "English"}}).encode()
    req = urllib.request.Request(BASE + "/services/aigc/multimodal-generation/generation", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    url = d["output"]["audio"]["url"].replace("http://", "https://")
    open(out_mp3, "wb").write(urllib.request.urlopen(url, timeout=60).read())

def make_video(key, clean_jpg, prompt, out_mp4, duration=3):
    import dashscope
    from dashscope.aigc.video_synthesis import VideoSynthesis
    dashscope.base_http_api_url = BASE; dashscope.api_key = key
    r = VideoSynthesis.async_call(model="wan2.5-i2v-preview", img_url=clean_jpg,
                                  prompt=prompt, resolution="480P", duration=duration)
    if r.status_code != 200:
        raise RuntimeError(f"submit failed {getattr(r,'code',None)} {getattr(r,'message',None)}")
    tid = r.output["task_id"]
    while True:
        time.sleep(15)
        f = VideoSynthesis.fetch(tid); st = f.output.get("task_status")
        if st == "SUCCEEDED":
            raw = out_mp4 + ".raw.mp4"
            urllib.request.urlretrieve(f.output["video_url"].replace("http://", "https://"), raw)
            subprocess.run(["ffmpeg", "-y", "-t", str(duration), "-i", raw, "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "20", "-an", out_mp4], capture_output=True)
            os.remove(raw); return
        if st == "FAILED":
            raise RuntimeError(f"video failed {f.output.get('code')} {f.output.get('message')}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True); ap.add_argument("--id", required=True)
    ap.add_argument("--text", default=None); ap.add_argument("--voice", default="Cherry")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "ebook", "assets"))
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); key = get_key()
    frame = os.path.join(a.out, f"{a.id}_frame.jpg")        # poster (clean, no text)
    rawj = os.path.join(a.out, f"{a.id}_frame_raw.jpg")      # original with text (for detection)
    mp3 = os.path.join(a.out, f"{a.id}_narration.mp3")
    mp4 = os.path.join(a.out, f"{a.id}.mp4")
    print("resize", resize_frame(a.image, rawj))
    det = detect_text(key, rawj); print("detected", det["text"])
    nums = detect_page_numbers(key, rawj); print("page numbers", [n["text"] for n in nums])
    text = a.text or det["text"]
    boxes = [ln["box"] for ln in det["lines"]] + [n["box"] for n in nums]
    remove_text(rawj, frame, boxes)                        # erase story text AND page numbers
    print("narrating..."); make_narration(key, text, mp3, a.voice)
    prompt = a.prompt or (f"Lively children's picture-book animation of this scene: {text}. "
                          "Natural motion following the action, warm and vivid, static camera.")
    print("animating (a few minutes)..."); make_video(key, frame, prompt, mp4)
    entry = {"type": "content", "id": a.id, "text": text,
             "video": f"assets/{a.id}.mp4", "poster": f"assets/{a.id}_frame.jpg",
             "audio": f"assets/{a.id}_narration.mp3",
             "layout": {"lines": det["lines"], "pageNumbers": nums}}
    print("MANIFEST_ENTRY=" + json.dumps(entry, ensure_ascii=False))

if __name__ == "__main__":
    main()
