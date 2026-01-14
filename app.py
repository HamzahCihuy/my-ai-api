import os
import time
import json
import subprocess
import sys
import yt_dlp
import cv2
import imagehash
from PIL import Image
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ PERINGATAN: API Key belum disetting!")
    genai.configure(api_key="")
else:
    print("✅ API Key berhasil dimuat.")
    genai.configure(api_key=GOOGLE_API_KEY)

def get_video_fingerprint(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
            success, frame = cap.read()
        cap.release()
        if success:
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            im_pil = Image.fromarray(img)
            return str(imagehash.phash(im_pil))
        return None
    except Exception as e:
        print(f"Gagal fingerprint: {e}")
        return None

def download_video(url):
    print(f"📥 Sedang mengunduh: {url}")
    ydl_opts = {
        'format': 'best[height<=480]/best[height<=720]/best',
        'outtmpl': 'temp_video_%(id)s.mp4',
        'quiet': True, 'no_warnings': True, 'overwrites': True,
        'nocheckcertificate': True, 'geo_bypass': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        print(f"Error Download: {e}")
        return None

def validate_content(file_path, instruksi_input, nama_peserta):
    model = genai.GenerativeModel("gemini-2.5-flash")

    print("🤖 Mengunggah ke AI...")
    video_file = genai.upload_file(path=file_path)

    while video_file.state.name == "PROCESSING":
        time.sleep(1)
        video_file = genai.get_file(video_file.name)

    prompt_spesifik = ""

    if isinstance(instruksi_input, str) and len(instruksi_input) > 3:
        prompt_spesifik = instruksi_input
        print(f"✅ Menggunakan Prompt CMS: {prompt_spesifik}")

    else:
        try: misi_id = int(instruksi_input)
        except: misi_id = -1

        if misi_id == 0: prompt_spesifik = "Video harus menampilkan buah kelapa muda/es kelapa."
        elif misi_id == 1: prompt_spesifik = "Video harus menampilkan alat pancing/danau."
        elif misi_id == 2: prompt_spesifik = "Video harus menampilkan ikan bakar."
        elif misi_id == 3: prompt_spesifik = "Video harus menampilkan rakit bambu."
        elif misi_id == 4: prompt_spesifik = "Video harus menampilkan tenda camping."
        else: prompt_spesifik = "Video harus menampilkan wisata alam."

    final_prompt = f"""
    Kamu adalah Validator Lomba Wisata 'Bukit Jar'un'.
    Nama Peserta: {nama_peserta}
    Tugas: Cek apakah video ini valid untuk kriteria: "{prompt_spesifik}"
    """
    Aturan:
    1. Jika visual video sesuai kriteria -> status: VALID.
    2. Jika video gelap, buram, atau tidak nyambung -> status: INVALID.
    Jawab HANYA JSON:
    {{ "status": "VALID" atau "INVALID", "alasan": "Alasan singkat..." }}
    """

    response = model.generate_content([video_file, final_prompt])
    try: genai.delete_file(video_file.name)
    except: pass
    return response.text

@app.route('/', methods=['GET'])
def health_check():
    return "Server AI Ready (CMS + Multi-Link Mode)!", 200

@app.route('/cek-video', methods=['POST'])
def api_handler():
    data = request.json

    urls = data.get('urls')
    if not urls:
        single = data.get('url')
        urls = [single] if single else []

    if not urls:
        return jsonify({"status": "INVALID", "alasan": "Link video tidak ditemukan."})

    prompt_cms = data.get('prompt_ai')

    instruksi_dasar = prompt_cms if prompt_cms else data.get('misi_id', -1)

    nama = data.get('nama', 'Peserta')
    hashes = []

    print(f"🔄 Memproses {len(urls)} video untuk {nama}...")

    for i, link in enumerate(urls):
        if not link: continue

        path = download_video(link)
        if not path:
             return jsonify({"status": "INVALID", "alasan": f"Gagal download video ke-{i+1}."})

        fp = get_video_fingerprint(path)
        if fp: hashes.append(fp)

        try:
            instruksi_final = instruksi_dasar
            if len(urls) > 1 and isinstance(instruksi_dasar, str):
                instruksi_final = f"{instruksi_dasar} (Ini adalah video bukti urutan ke-{i+1})"

            hasil_teks = validate_content(path, instruksi_final, nama)
            clean_text = hasil_teks.replace("```json", "").replace("```", "").strip()
            hasil_json = json.loads(clean_text)

            try: os.remove(path)
            except: pass

            if hasil_json.get('status') == 'INVALID':
                return jsonify({
                    "status": "INVALID",
                    "alasan": f"Video #{i+1} GAGAL: {hasil_json.get('alasan')}"
                })

        except Exception as e:
            print(f"Error: {e}")
            try: os.remove(path)
            except: pass
            return jsonify({"status": "INVALID", "alasan": "Kesalahan sistem AI."})

    return jsonify({
        "status": "VALID",
        "video_hash": ",".join(hashes)
    })

if __name__ == '__main__':
    try: subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    except: pass
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
