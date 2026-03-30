import os
import time
import base64
import requests
import threading
from flask import Flask, request, jsonify, render_template
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Configuración de carpetas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, 'static', 'images')
VIDEO_DIR = os.path.join(BASE_DIR, 'static', 'videos')
for d in [IMAGE_DIR, VIDEO_DIR]: os.makedirs(d, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()
AD_DOMAINS = ["google-analytics", "doubleclick", "popads", "adskeeper", "googlesyndication"]

def apply_adblock(route):
    if any(ad in route.request.url for ad in AD_DOMAINS): return route.abort()
    return route.continue_()

class AutomationTask:
    def __init__(self, job_id, prompt, mode, aspect_val):
        self.job_id = job_id
        self.prompt = prompt
        self.mode = mode
        self.aspect_val = aspect_val

    def run(self):
        # Iniciar Playwright dentro del hilo para evitar errores de Loop cerrado
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.route("**/*", apply_adblock)

            if self.mode == "image":
                page.goto("https://freegen.app/", wait_until="networkidle")
                page.fill("textarea", self.prompt)
                page.click("button:has-text('Generate')")
                # Esperar a que la imagen aparezca
                page.wait_for_selector("img[src*='data:image'], img[src*='http']", timeout=60000)
                img_data = page.evaluate("""() => {
                    const target = Array.from(document.querySelectorAll('img'))
                        .find(i => i.naturalWidth > 300 && !i.src.includes('logo'));
                    return target ? target.src : null;
                }""")
                if img_data:
                    filename = f"img_{self.job_id}.png"
                    content = base64.b64decode(img_data.split(",")[1]) if "data:" in img_data else requests.get(img_data).content
                    with open(os.path.join(IMAGE_DIR, filename), "wb") as f: f.write(content)
                    with jobs_lock: jobs[self.job_id].update({"state": "done", "url": f"/static/images/{filename}"})

            elif self.mode == "video":
                page.goto("https://veoaifree.com/grok-ai-video-generator/", wait_until="networkidle")
                page.locator(".fn__svg.replaced-svg.svg-setting").first.click()
                page.get_by_label("Aspect Ratio", exact=True).select_option(self.aspect_val)
                page.fill("textarea", self.prompt)
                page.click("button:has-text('Generate')")
                
                video_el = page.wait_for_selector("video, video source, a[href$='.mp4']", timeout=180000)
                video_src = video_el.get_attribute("src") or video_el.get_attribute("href")
                if video_src:
                    filename = f"vid_{self.job_id}.mp4"
                    with open(os.path.join(VIDEO_DIR, filename), "wb") as f: f.write(requests.get(video_src).content)
                    with jobs_lock: jobs[self.job_id].update({"state": "done", "url": f"/static/videos/{filename}"})
            browser.close()
        except Exception as e:
            with jobs_lock: jobs[self.job_id].update({"state": "error", "error": str(e)})
        finally:
            pw.stop()

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    job_id = str(int(time.time() * 1000))
    with jobs_lock: jobs[job_id] = {"state": "processing", "type": data['mode']}
    task = AutomationTask(job_id, data['prompt'], data['mode'], data.get('aspect','VIDEO_ASPECT_RATIO_LANDSCAPE'))
    threading.Thread(target=task.run, daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/status")
def get_status():
    history = []
    for folder, t in [(IMAGE_DIR, "image"), (VIDEO_DIR, "video")]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                path = os.path.join(folder, f)
                history.append({
                    "url": f"/static/{t}s/{f}", 
                    "filename": f, 
                    "type": t, 
                    "t": os.path.getctime(path)
                })
    history.sort(key=lambda x: x['t'], reverse=True)
    return jsonify({"history": history, "active_jobs": jobs})

@app.route("/delete", methods=["POST"])
def delete_file():
    data = request.json
    folder = IMAGE_DIR if data['type'] == 'image' else VIDEO_DIR
    try:
        file_path = os.path.join(folder, data['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "message": "File not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/")
def index(): return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)