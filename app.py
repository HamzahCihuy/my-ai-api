import os
import time
import json
import subprocess
import sys
import yt_dlp
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# =========================
# 1. KONFIGURASI API 
# =========================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ PERINGATAN: API Key belum disetting di Railway Variables!")
    genai.configure(api_key="")
else:
    print("✅ API Key berhasil dimuat.")
    genai.configure(api_key=GOOGLE_API_KEY)

# =========================
# 2. FUNGSI DOWNLOADER (OPTIMASI RAILWAY)
# =========================
def download_video(url):
    print(f"📥 Sedang mengunduh: {url}")
    
    # Settingan Hemat RAM & Anti-Blokir
    ydl_opts = {
        'format': 'best[height<=480]/best[height<=360]/worst', # Max 480p
        'outtmpl': 'temp_video.mp4',
        'quiet': True,
        'no_warnings': True,
        'overwrites': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'user_agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36',
    }
    
    try:
        if os.path.exists('temp_video.mp4'):
            os.remove('temp_video.mp4')
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return "temp_video.mp4"
    except Exception as e:
        print(f"Error Download: {e}")
        return None

# =========================
# 3. FUNGSI AI VALIDATOR
# =========================
def validate_content(file_path, misi_id, nama_peserta):
    # Gunakan model flash agar cepat
    model = genai.GenerativeModel("models/gemini-1.5-flash") 
    
    print("🤖 Mengunggah ke AI...")
    video_file = genai.upload_file(path=file_path)

    # Tunggu processing
    while video_file.state.name == "PROCESSING":
        time.sleep(1)
        video_file = genai.get_file(video_file.name)

    # Logic Prompt
    prompt_spesifik = ""
    try:
        misi_id = int(misi_id)
    except:
        misi_id = -1

    if misi_id == 0: 
        prompt_spesifik = "Video harus menampilkan buah kelapa muda, es kelapa, atau orang minum air kelapa."
    elif misi_id == 1: 
        prompt_spesifik = "Video harus menampilkan alat pancing, danau/kolam pemancingan, atau aktivitas memancing."
    elif misi_id == 2: 
        prompt_spesifik = "Video harus menampilkan hidangan ikan bakar atau proses membakar ikan."
    elif misi_id == 3: 
        prompt_spesifik = "Video harus menampilkan orang menaiki rakit/perahu bambu di atas air."
    elif misi_id == 4: 
        prompt_spesifik = "Video harus menampilkan tenda camping atau suasana berkemah."
    else:
        prompt_spesifik = "Video harus menampilkan suasana wisata alam outdoor."

    final_prompt = f"""
    Kamu adalah Validator Lomba Wisata 'Bukit Jar'un'.
    Nama Peserta: {nama_peserta}
    
    Tugas: Cek apakah video ini valid untuk misi: "{prompt_spesifik}"
    
    Aturan:
    1. Jika video menampilkan apa yang diminta di misi -> status: VALID.
    2. Jika video gelap, tidak jelas, atau tidak nyambung -> status: INVALID.
    
    Jawab HANYA dengan format JSON ini (tanpa markdown ```json):
    {{
        "status": "VALID" atau "INVALID",
        "alasan": "Berikan alasan singkat dan santai dalam 1 kalimat bahasa Indonesia untuk {nama_peserta}."
    }}
    """

    response = model.generate_content([video_file, final_prompt])
    
    # Hapus file di Cloud Google
    try: genai.delete_file(video_file.name)
    except: pass
    
    return response.text

# =========================
# 4. ENDPOINT UTAMA
# =========================
@app.route('/', methods=['GET'])
def health_check():
    return "Server AI Validator is Running!", 200

@app.route('/cek-video', methods=['POST'])
def api_handler():
    data = request.json
    link = data.get('url')
    misi_id = data.get('misi_id') 
    nama = data.get('nama', 'Peserta')

    if not link:
        return jsonify({"status": "INVALID", "alasan": "Link video kosong."})

    # 1. Download
    path = download_video(link)
    if not path:
        return jsonify({"status": "INVALID", "alasan": "Gagal download video. Pastikan link TikTok/IG publik dan benar."})

    # 2. Analisis AI
    try:
        hasil_teks = validate_content(path, misi_id, nama)
        
        # Bersihkan text JSON
        clean_text = hasil_teks.replace("```json", "").replace("```", "").strip()
        hasil_json = json.loads(clean_text)
        
    except Exception as e:
        hasil_json = {"status": "INVALID", "alasan": f"AI Error: {str(e)}"}

    # 3. Cleanup File Lokal
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"⚠️ Gagal hapus file: {e}")

    return jsonify(hasil_json)

# =========================
# 5. START SERVER
# =========================
if __name__ == '__main__':
    # Auto update yt-dlp saat start
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    except:
        pass

    port = int(os.environ.get("PORT", 5000))
    print(f"🔥 Server AI Validator Siap di Port {port}!")
    app.run(host='0.0.0.0', port=port)
