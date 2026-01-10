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
# 1. KONFIGURASI API (UPDATE UTAMA)
# =========================
# Mengambil kunci dari "Brankas" Railway (Environment Variables)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ PERINGATAN: API Key belum disetting di Railway Variables!")
    # Fallback kosong agar tidak error saat start, tapi nanti akan error saat dipakai
    genai.configure(api_key="")
else:
    print("✅ API Key berhasil dimuat dari Railway.")
    genai.configure(api_key=GOOGLE_API_KEY)
if GOOGLE_API_KEY:
    # Tampilkan 5 huruf awal dan 5 huruf akhir key di Log Railway
    # Ini aman karena tidak menampilkan seluruh key
    print(f"🔑 Key Aktif: {GOOGLE_API_KEY[:5]}...{GOOGLE_API_KEY[-5:]}")
else:
    print("❌ Key KOSONG/TIDAK TERBACA")

# ==========================================
# FITUR: AUTO UPDATE YT-DLP
# ==========================================
def update_library():
    """Fungsi untuk memaksa update yt-dlp via pip"""
    print("🔄 Memulai Update yt-dlp...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
        print("✅ yt-dlp berhasil diupdate ke versi terbaru!")
        return True
    except Exception as e:
        print(f"❌ Gagal update: {e}")
        return False

@app.route('/update-system', methods=['GET'])
def trigger_update():
    """Endpoint rahasia untuk memicu update tanpa restart server"""
    sukses = update_library()
    if sukses:
        return jsonify({"status": "success", "pesan": "Library yt-dlp berhasil diperbarui."})
    else:
        return jsonify({"status": "error", "pesan": "Gagal melakukan update."}), 500


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
        # Hapus file lama jika ada
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
def validate_content(file_path, misi_id):
    model = genai.GenerativeModel("models/gemini-2.5-flash") # atau 1.5-flash
    
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
    Kamu adalah Validator Lomba.
    Tugas: Cek apakah video ini memenuhi syarat misi: "{prompt_spesifik}"
    
    Jawab HANYA dengan format JSON ini (tanpa markdown):
    {{
        "status": "VALID" atau "INVALID",
        "alasan": "Alasan singkat 1 kalimat"
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

    if not link:
        return jsonify({"status": "error", "alasan": "Link kosong"})

    # 1. Download
    path = download_video(link)
    if not path:
        return jsonify({"status": "error", "alasan": "Gagal download video (Link private/salah)"})

    # 2. Analisis AI
    try:
        hasil_teks = validate_content(path, misi_id)
        
        # Bersihkan text JSON
        clean_text = hasil_teks.replace("```json", "").replace("```", "").strip()
        hasil_json = json.loads(clean_text)
        
    except Exception as e:
        hasil_json = {"status": "error", "alasan": f"AI Error: {str(e)}"}

    # 3. Cleanup File Lokal
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"🗑️ File {path} berhasil dihapus.")
    except Exception as e:
        print(f"⚠️ Gagal hapus file: {e}")

    return jsonify(hasil_json)


# =========================
# 5. START SERVER
# =========================
if __name__ == '__main__':
    # Ambil PORT dari Railway, default 5000
    port = int(os.environ.get("PORT", 5000))
    print(f"🔥 Server AI Validator Siap di Port {port}!")
    
    # Host 0.0.0.0 Wajib untuk Railway
    app.run(host='0.0.0.0', port=port)
