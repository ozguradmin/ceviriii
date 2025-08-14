from flask import Flask, render_template, request, jsonify, url_for, send_from_directory
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import video_processor
import threading
import uuid
import json
from urllib.request import urlopen
import socket

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Yüklenen dosyaların ve çıktıların kaydedileceği klasör
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'static/outputs'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Klasörlerin var olduğundan emin ol
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

FONT_FOLDER = 'fonts'
os.makedirs(FONT_FOLDER, exist_ok=True)
app.config['FONT_FOLDER'] = FONT_FOLDER

# Varsayılan birkaç açık kaynak fontu otomatik indir (yoksa)
def ensure_default_fonts():
    default_fonts = {
        'Roboto-Bold.ttf': 'https://raw.githubusercontent.com/google/fonts/main/apache/roboto/Roboto-Bold.ttf',
        'Montserrat-Bold.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Bold.ttf',
        'Anton-Regular.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf',
        'Poppins-Bold.ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf'
    }
    for fname, url in default_fonts.items():
        dest = os.path.join(FONT_FOLDER, fname)
        if not os.path.exists(dest):
            try:
                with urlopen(url) as resp, open(dest, 'wb') as out:
                    out.write(resp.read())
            except Exception:
                # Ağ yoksa sessiz geç
                pass

ensure_default_fonts()

# Arka plan görevlerinin durumunu saklamak için global bir sözlük
tasks = {}

def process_video_task(video_path, task_id, style_options, font_path=None): # font_path eklendi
    """Bu fonksiyon arka planda çalışacak ve video işleme adımlarını yürütecek."""
    # app.app_context() artık gerekli değil çünkü url_for kullanmıyoruz.
    try:
        tasks[task_id] = {'status': 'processing', 'progress': 25, 'message': 'Video 9:16 boyutuna getiriliyor...'}
        resized_video_path = video_processor.videoyu_9_16_boyutuna_getir(
            video_path,
            app.config['OUTPUT_FOLDER'],
            width=style_options.get('width', 1080),
            height=style_options.get('height', 1920),
            crf=style_options.get('crf', 20),
            fps=style_options.get('fps', None)
        )
        
        tasks[task_id] = {'status': 'processing', 'progress': 50, 'message': 'Sesi ayrıştırılıyor...'}
        audio_path = video_processor.sesi_ayikla(resized_video_path, app.config['OUTPUT_FOLDER'])
        
        tasks[task_id] = {'status': 'processing', 'progress': 75, 'message': 'Gemini AI ile altyazılar oluşturuluyor...'}
        subtitles_data = video_processor.gemini_altyazi_olustur(audio_path)

        # Zaman esnetme istenirse (ilk işlemde) uygula
        if style_options.get('timing_relax'):
            subtitles_data = video_processor.relax_timings(subtitles_data, start_pad_sec=0.0, end_pad_sec=0.5)

        tasks[task_id] = {'status': 'processing', 'progress': 90, 'message': 'Altyazılar videoya ekleniyor...'}
        final_video_path = video_processor.altyazilari_videoya_ekle(
            resized_video_path, subtitles_data, app.config['OUTPUT_FOLDER'], 
            font_path=font_path, # font_path'i aktar
            is_bold=style_options['is_bold'],
            has_background=style_options['has_background'],
            bg_opacity=style_options['bg_opacity'],
            has_animation=style_options['has_animation'],
            margin_v=style_options['margin_v'],
            font_size=style_options.get('font_size', 60),
            outline_px=style_options.get('outline_px', 3),
            shadow_px=style_options.get('shadow_px', 2),
            alignment=style_options.get('alignment', 2),
            crf=style_options.get('crf', 20),
            fps=style_options.get('fps', None),
            margin_l=style_options.get('margin_l', 80),
            margin_r=style_options.get('margin_r', 80)
        )
        
        # Web için göreceli yolu oluştur
        final_video_web_path = os.path.join('static', 'outputs', os.path.basename(final_video_path)).replace("\\", "/")

        tasks[task_id] = {
            'status': 'complete', 
            'progress': 100, 
            'message': 'İşlem tamamlandı!',
            'video_path': final_video_web_path, # URL yerine path gönderiyoruz
            'subtitles': subtitles_data
        }

    except Exception as e:
        tasks[task_id] = {'status': 'error', 'message': str(e)}
        try:
            print('Process task error:', e)
        except Exception:
            pass


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_video():
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'Video dosyası bulunamadı.'})
    file = request.files['video']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Video dosyası seçilmedi.'})

    if file:
        filename = secure_filename(file.filename)
        uploaded_video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(uploaded_video_path)

        # Stilleri ve fontu formdan al
        style_options = {
            'has_background': request.form.get('has_background') == 'true',
            'has_animation': request.form.get('has_animation') == 'true',
            'is_bold': request.form.get('is_bold') == 'true',
            'timing_relax': request.form.get('timing_relax') == 'true',
            'bg_opacity': float(request.form.get('bg_opacity', 0.5)),
            'margin_v': int(request.form.get('margin_v', 450)),
            'font_size': int(request.form.get('font_size', 60)),
            'outline_px': int(request.form.get('outline_px', 3)),
            'shadow_px': int(request.form.get('shadow_px', 2)),
            'alignment': int(request.form.get('alignment', 2)),
            'crf': int(request.form.get('crf', 20)),
            'fps': (int(request.form.get('fps')) if request.form.get('fps') and request.form.get('fps').isdigit() else None),
            'margin_l': int(request.form.get('margin_l', 80)),
            'margin_r': int(request.form.get('margin_r', 80))
        }
        res = request.form.get('resolution', '1080x1920')
        try:
            w, h = res.lower().split('x')
            style_options['width'] = int(w)
            style_options['height'] = int(h)
        except Exception:
            style_options['width'] = 1080
            style_options['height'] = 1920
        
        font_path = None
        selected_font = request.form.get('selected_font', '').strip()
        if 'font_file' in request.files:
            font_file = request.files['font_file']
            if font_file.filename != '':
                font_filename = secure_filename(font_file.filename)
                font_path = os.path.join(app.config['FONT_FOLDER'], font_filename)
                font_file.save(font_path)
        if not font_path and selected_font:
            candidate_path = os.path.join(app.config['FONT_FOLDER'], secure_filename(selected_font))
            if os.path.exists(candidate_path):
                font_path = candidate_path

        task_id = str(uuid.uuid4())
        tasks[task_id] = {'status': 'pending', 'progress': 0, 'message': 'Görev başlatılıyor...'}
        
        # Görevi stil seçenekleriyle birlikte arka plan thread'inde başlat
        thread = threading.Thread(target=process_video_task, args=(uploaded_video_path, task_id, style_options, font_path))
        thread.start()

        return jsonify({'success': True, 'task_id': task_id})

@app.route('/status/<task_id>')
def task_status(task_id):
    """Bir görevin durumunu döndürür."""
    task = tasks.get(task_id, None)
    if not task:
        return jsonify({'status': 'error', 'message': 'Görev bulunamadı.'})
    return jsonify(task)

@app.route('/reprocess', methods=['POST'])
def reprocess_video():
    # FormData'dan verileri al
    video_path = request.form.get('video_path')
    subtitles = json.loads(request.form.get('subtitles'))
    color_map = json.loads(request.form.get('color_map'))
    has_background = request.form.get('has_background') == 'true'
    has_animation = request.form.get('has_animation') == 'true'
    is_bold = request.form.get('is_bold') == 'true'
    timing_relax = request.form.get('timing_relax') == 'true'
    bg_opacity = float(request.form.get('bg_opacity', 0.5))
    margin_v = int(request.form.get('margin_v', 450)) # Yeni dikey konumu al
    font_size = int(request.form.get('font_size', 60))
    outline_px = int(request.form.get('outline_px', 3))
    shadow_px = int(request.form.get('shadow_px', 2))
    alignment = int(request.form.get('alignment', 2))
    crf = int(request.form.get('crf', 20))
    fps = (int(request.form.get('fps')) if request.form.get('fps') and request.form.get('fps').isdigit() else None)
    
    font_path = None
    selected_font = request.form.get('selected_font', '').strip()
    if 'font_file' in request.files:
        font_file = request.files['font_file']
        if font_file.filename != '':
            font_filename = secure_filename(font_file.filename)
            font_path = os.path.join(app.config['FONT_FOLDER'], font_filename)
            font_file.save(font_path)
    if not font_path and selected_font:
        candidate_path = os.path.join(app.config['FONT_FOLDER'], secure_filename(selected_font))
        if os.path.exists(candidate_path):
            font_path = candidate_path

    # Gelen yol 'static/' ile başlıyorsa, onu sistem yoluna çevir
    if video_path.startswith('static/'):
        system_video_path = os.path.join(os.getcwd(), video_path)
    else:
        system_video_path = video_path # Güvenlik için normalde daha iyi kontrol gerekir

    # Orijinal _9x16.mp4 dosyasını bulmalıyız, _altyazili.mp4'ü değil.
    base_video_path = system_video_path.replace('_altyazili.mp4', '.mp4')

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'pending', 'message': 'Değişiklikler uygulanıyor...'}
    
    # Yeniden işleme görevini arka planda başlat
    thread = threading.Thread(target=reprocess_video_task, args=(
        base_video_path, subtitles, color_map, font_path, has_background, has_animation, is_bold, timing_relax, bg_opacity, margin_v, font_size, outline_px, shadow_px, alignment, crf, fps, task_id
    ))
    thread.start()

    return jsonify({'success': True, 'task_id': task_id})

@app.route('/api/fonts', methods=['GET'])
def list_fonts():
    """Sunucudaki fonts/ klasöründe bulunan fontları listeler."""
    fonts_dir = app.config['FONT_FOLDER']
    items = []
    try:
        for f in os.listdir(fonts_dir):
            if f.lower().endswith(('.ttf', '.otf')):
                full_path = os.path.join(fonts_dir, f)
                try:
                    family = video_processor._read_font_family_name(full_path)  # type: ignore
                except Exception:
                    family = os.path.splitext(f)[0]
                items.append({'file': f, 'family': family})
        items.sort(key=lambda it: os.path.getmtime(os.path.join(fonts_dir, it['file'])), reverse=True)
    except Exception:
        pass
    return jsonify({'fonts': items})

@app.route('/download/<path:filename>')
def download_output(filename: str):
    """İşlenmiş videoyu tarayıcıya indirtecek uç nokta."""
    directory = app.config['OUTPUT_FOLDER']
    return send_from_directory(directory, filename, as_attachment=True)

def reprocess_video_task(video_path, subtitles, color_map, font_path, has_background, has_animation, is_bold, timing_relax, bg_opacity, margin_v, font_size, outline_px, shadow_px, alignment, crf, fps, task_id):
    """Sadece altyazıları yeniden basan arka plan görevi."""
    try:
        tasks[task_id] = {'status': 'processing', 'progress': 50, 'message': 'Yeni altyazılar videoya ekleniyor...'}
        
        # Orijinal video yolundan (_9x16.mp4) yola çıkarak dosya adlarını oluştur
        base_video_path = video_path.replace(os.getcwd() + os.sep, '') # Mutlak yolu göreceli yap
        
        # Zaman esnetme istenirse uygula
        if timing_relax:
            subtitles = video_processor.relax_timings(subtitles, start_pad_sec=0.0, end_pad_sec=0.5)

        final_video_path = video_processor.altyazilari_videoya_ekle(
            base_video_path, subtitles, app.config['OUTPUT_FOLDER'], 
            color_map, font_path, has_background, has_animation, is_bold, bg_opacity, margin_v,
            font_size=font_size, outline_px=outline_px, shadow_px=shadow_px, alignment=alignment,
            crf=crf, fps=fps
        )
        
        final_video_web_path = os.path.join('static', 'outputs', os.path.basename(final_video_path)).replace("\\", "/")

        tasks[task_id] = {
            'status': 'complete',
            'progress': 100,
            'message': 'Değişiklikler başarıyla uygulandı!',
            'video_path': final_video_web_path,
            'subtitles': subtitles
        }
    except Exception as e:
        tasks[task_id] = {'status': 'error', 'message': str(e)}
        try:
            print('Reprocess task error:', e)
        except Exception:
            pass


@app.route('/api/host', methods=['GET'])
def host_info():
    """Sunucunun yerel IP bilgisini döndürür (mobil erişim için)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = '127.0.0.1'
    return jsonify({'ip': ip, 'port': 5001})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
