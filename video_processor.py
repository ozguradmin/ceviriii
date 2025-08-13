import os
import json
import subprocess
import google.generativeai as genai
import math

# Opsiyonel: font ailesi adını dosyadan okuyabilmek için fontTools
try:
    from fontTools.ttLib import TTFont  # type: ignore
    _HAS_FONTTOOLS = True
except Exception:
    _HAS_FONTTOOLS = False

# Debug: fontTools mevcut mu?
try:
    print(f"fontTools durumu: {_HAS_FONTTOOLS}")
except Exception:
    pass

# API anahtarları listesi (ENV üzerinden override edilebilir)
ENV_KEYS = os.environ.get('GEMINI_API_KEYS') or os.environ.get('GOOGLE_API_KEYS') or ''
if ENV_KEYS.strip():
    API_KEYS = [k.strip() for k in ENV_KEYS.replace('\n', ',').split(',') if k.strip()]
else:
    API_KEYS = [
        "AIzaSyAE3oQi4Zwb7YBiJ2zX5K3HcogcJxwpH9g",
        "AIzaSyBkGFGkPtUIJV07dolTA61iDCVCX8Satl4",
        "AIzaSyCcu5GLciG4rdT8FftRnk7NKS06qaehn8Q",
        "AIzaSyDIstqqMAlS1EGHZCBWvy98ueqejrHN8C4",
        "AIzaSyB8pRKjomrBkKELh-cDtuD8sqzFflwUdoA",
        "AIzaSyAYN0kchg5scMw0Xn0BxM-t51XhqAaN3Jc",
        "AIzaSyA22fyewqngWsO82oY8zQQe_FtcbQeZ2TI",
        "AIzaSyBmYob9OQoE0IyMzdzpzExKip6nwWwf6mk",
        "AIzaSyB1dK2TDgEc6bSyMe_KpE5kZWf8tSubCX4"
    ]
aktif_api_key_index = 0

def run_ffmpeg_command(command):
    """FFmpeg komutunu çalıştırır ve hataları kontrol eder."""
    try:
        env = os.environ.copy()
        # Windows'ta libass'ın fontconfig sağlayıcısını kullanması için zorla
        env['LIBASS_FONT_PROVIDER'] = 'fontconfig'
        # Daha detaylı log isterseniz: command = ['ffmpeg', '-loglevel', 'info', ...]
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', env=env)
        print("FFmpeg komutu başarıyla çalıştı:", " ".join(command))
    except subprocess.CalledProcessError as e:
        print("FFmpeg Hatası:")
        print("Komut:", " ".join(e.cmd))
        print("Çıktı:", e.stdout)
        print("Hata Çıktısı:", e.stderr)
        raise Exception(f"FFmpeg hatası: {e.stderr}")

def videoyu_9_16_boyutuna_getir(video_yolu, output_folder, width: int = 1080, height: int = 1920, crf: int = 20, fps: int | None = None):
    """Videoyu verilen genişlik x yükseklik boyutuna getirir, en boy oranını korur ve siyah bant ekler."""
    dosya_adi = os.path.basename(video_yolu)
    cikti_yolu = os.path.join(output_folder, f"{os.path.splitext(dosya_adi)[0]}_9x16.mp4")
    
    command = [
        'ffmpeg',
        '-i', video_yolu,
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black'
    ]
    if fps:
        # ÇIKTI FPS'i ayarla (output option). '-vf' sonrasında, codec ayarlarından önce konumlandır.
        command += ['-r', str(int(fps))]
    command += [
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', str(int(crf)),
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-c:a', 'copy',
        '-y',
        cikti_yolu
    ]
    run_ffmpeg_command(command)
    return cikti_yolu

def sesi_ayikla(video_yolu, output_folder):
    """Videodan sesi ayıklar ve mp3 olarak kaydeder."""
    dosya_adi = os.path.basename(video_yolu)
    ses_cikti_yolu = os.path.join(output_folder, f"{os.path.splitext(dosya_adi)[0]}.mp3")
    
    # -vn: video yok (sadece ses)
    # -q:a 0: en iyi mp3 kalitesi
    command = [
        'ffmpeg',
        '-i', video_yolu,
        '-vn',
        '-q:a', '0',
        '-map', 'a',
        '-y',
        ses_cikti_yolu
    ]
    run_ffmpeg_command(command)
    return ses_cikti_yolu

def saniye_to_ass_time(saniye):
    """Saniyeyi ASS formatındaki Saat:Dakika:Saniye.Salise formatına çevirir."""
    saat = int(saniye // 3600)
    saniye %= 3600
    dakika = int(saniye // 60)
    saniye %= 60
    saniye_tam = int(saniye)
    salise = int((saniye - saniye_tam) * 100)
    return f"{saat:01}:{dakika:02}:{saniye_tam:02}.{salise:02}"

def relax_timings(subs: list, start_pad_sec: float = 0.0, end_pad_sec: float = 0.5) -> list:
    """Altyazı aralıklarını (start_pad_sec, end_pad_sec) kadar genişletir; çakışmayı komşularla sınırlar.
    Kurallar:
      - start = max(0, start - start_pad_sec)
      - end   = end + end_pad_sec
      - Bir sonraki satırla çakışırsa, end = min(end, next.start)
      - Bir öncekiyle çakışırsa, start = max(start, prev.end)
    """
    if not subs:
        return subs
    # Önce zamanlanan sıraya koy
    items = sorted([dict(s) for s in subs], key=lambda s: (float(s.get('start', 0)), float(s.get('end', 0))))
    n = len(items)
    for i in range(n):
        s = items[i]
        s['start'] = max(0.0, float(s['start']) - float(start_pad_sec))
        s['end'] = float(s['end']) + float(end_pad_sec)
    # Komşularla çakışmayı azalt
    for i in range(n):
        if i > 0:
            prev = items[i-1]
            if items[i]['start'] < prev['end']:
                items[i]['start'] = prev['end']
        if i < n-1:
            nxt = items[i+1]
            if items[i]['end'] > float(nxt['start']):
                items[i]['end'] = float(nxt['start'])
        # start <= end güvenliği
        if items[i]['end'] < items[i]['start']:
            items[i]['end'] = items[i]['start']
    return items

def _guess_family_from_filename(file_path: str) -> str:
    """Font dosya adından aile ismini tahmin eder (fontTools yoksa)."""
    base = os.path.splitext(os.path.basename(file_path))[0]
    # Yaygın ağırlık/stil eklerini temizle
    tokens = base.replace('_', '-').split('-')
    if len(tokens) > 1:
        family = tokens[0]
    else:
        family = base
    # Bazı son ekleri kaldır
    endings = [
        'Regular', 'Bold', 'Italic', 'Oblique', 'Medium', 'SemiBold', 'ExtraBold',
        'Light', 'Thin', 'Black', 'Book', 'Roman', 'ExtraLight', 'DemiBold'
    ]
    for end in endings:
        if family.endswith(end):
            family = family[: -len(end)]
    return family.strip() or base


def _read_font_family_name(font_path: str) -> str:
    """Font dosyasının gerçek family adını döndürür; mümkün değilse dosya adına göre tahmin eder.

    Not: Çalışan süreçte fontTools sonradan yüklenmiş olabilir. Bu yüzden her çağrıda
    dinamik import denemesi yapıyoruz ki yeniden başlatmaya gerek kalmadan doğru
    aile ismi okunabilsin.
    """
    global _HAS_FONTTOOLS
    TTFontLocal = None

    # Dinamik import denemesi
    if not _HAS_FONTTOOLS:
        try:
            from importlib import import_module
            TTFontLocal = import_module('fontTools.ttLib').TTFont  # type: ignore
            _HAS_FONTTOOLS = True
        except Exception:
            TTFontLocal = None
    else:
        try:
            TTFontLocal = TTFont  # type: ignore
        except Exception:
            TTFontLocal = None

    if font_path and TTFontLocal:
        try:
            font = TTFontLocal(font_path)
            # nameID 1: Family Name; nameID 4: Full Name
            family_name = None
            full_name = None
            for rec in font['name'].names:
                try:
                    text = rec.toUnicode()
                except Exception:
                    try:
                        text = rec.string.decode(rec.getEncoding(), errors='ignore')
                    except Exception:
                        text = None
                if not text:
                    continue
                if rec.nameID == 1 and not family_name:
                    family_name = text
                if rec.nameID == 4 and not full_name:
                    full_name = text
                if family_name and full_name:
                    break
            font.close()
            # Önce family (1), yoksa full (4)
            if family_name:
                return family_name
            if full_name:
                return full_name
        except Exception:
            pass
    # fontTools yoksa veya okunamadıysa dosya adına göre tahmin et
    return _guess_family_from_filename(font_path) if font_path else 'Arial'


def _detect_font_style_flags(font_path: str) -> dict:
    """Seçili font dosyasından bold/italic destek durumunu tahmin eder.
    Dönüş: { 'supports_bold': bool, 'is_italic_face': bool }
    """
    info = { 'supports_bold': False, 'is_italic_face': False }
    if not font_path:
        return info
    lower_name = os.path.basename(font_path).lower()
    if 'italic' in lower_name or 'ital' in lower_name:
        info['is_italic_face'] = True

    # Dinamik fontTools ile daha sağlam tespit
    try:
        from importlib import import_module
        TTFontLocal = import_module('fontTools.ttLib').TTFont  # type: ignore
        font = TTFontLocal(font_path)
        try:
            # OS/2 tablosu ağırlık ve italic bayrağı içerir
            if 'OS/2' in font:
                os2 = font['OS/2']
                weight = getattr(os2, 'usWeightClass', 400)
                info['supports_bold'] = bool(weight and weight >= 700)
                # ItalicAngle bazı fontlarda post tablosunda olur
                if 'post' in font:
                    italic_angle = getattr(font['post'], 'italicAngle', 0)
                    if italic_angle and float(italic_angle) != 0.0:
                        info['is_italic_face'] = True
        finally:
            font.close()
    except Exception:
        # Dosya adına göre kaba tahmin
        if any(t in lower_name for t in ['bold', 'black', 'heavy']):
            info['supports_bold'] = True
    return info


def generate_ass_file(altyazilar_data, output_path, color_map=None, font_path=None, has_background=False, has_animation=False, is_bold=False, bg_opacity=0.5, margin_v=450, font_size: int = 60, outline_px: int = 3, shadow_px: int = 2, alignment: int = 2, margin_l: int = 80, margin_r: int = 80):
    """Verilen altyazı verisinden bir .ass altyazı dosyası oluşturur."""
    konusmaci_stilleri = {}
    renk_listesi = ['&H00FFFF', '&HFFFFFF', '&H00FF00', '&HFF00FF', '&HFFFF00']

    stiller = "[V4+ Styles]\n"
    stiller += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    
    olaylar = "\n[Events]\n"
    olaylar += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    
    # Varsayılan fontu ve font klasörünü kontrol et
    fontname = "Arial"  # Varsayılan
    default_font_path = None
    fonts_dir = 'fonts'
    if os.path.exists(fonts_dir):
        font_files = [
            os.path.join(fonts_dir, f)
            for f in os.listdir(fonts_dir)
            if f.lower().endswith(('.ttf', '.otf'))
        ]
        if font_files:
            # En son eklenen/değiştirilen fontu seç
            default_font_path = max(font_files, key=lambda p: os.path.getmtime(p))
    
    active_font_path = font_path if font_path else default_font_path
    italic_flag = 0
    supports_bold = True
    if active_font_path:
        fontname = _read_font_family_name(active_font_path)
        style_info = _detect_font_style_flags(active_font_path)
        italic_flag = 1 if style_info.get('is_italic_face') else 0
        supports_bold = bool(style_info.get('supports_bold', True))
        try:
            print(f"ASS içinde kullanılacak aile adı: {fontname}")
            print(f"Font yüzü italik mi: {bool(italic_flag)}, bold destekli mi: {supports_bold}")
        except Exception:
            pass

    bg_opacity_hex = format(math.floor(255 * (1 - bg_opacity)), '02X')

    for altyazi in altyazilar_data:
        konusmaci = altyazi.get("speaker", "Konuşmacı 1").replace(" ", "")
        if konusmaci not in konusmaci_stilleri:
            renk = color_map.get(altyazi.get("speaker", "Konuşmacı 1"), renk_listesi[len(konusmaci_stilleri) % len(renk_listesi)]) if color_map else renk_listesi[len(konusmaci_stilleri) % len(renk_listesi)]
            konusmaci_stilleri[konusmaci] = renk
            
            border_style = 1 if not has_background else 3
            outline = max(0, int(outline_px))
            # Seçilen font bold desteklemiyorsa bold'u zorlamayalım (fallback tetikleyebilir)
            bold_flag = -1 if (is_bold and supports_bold) else 0
            back_color = f"&H{bg_opacity_hex}000000"

            # SecondaryColour ve OutlineColour'u daha mantıklı yapalım: Secondary beyaz, Outline siyah
            secondary = '&H00FFFFFF'
            outline_colour = '&H00000000'
            shadow = max(0, int(shadow_px))

            stiller += f"Style: {konusmaci},{fontname},{int(font_size)},{renk},{secondary},{outline_colour},{back_color},{bold_flag},{italic_flag},0,0,100,100,0,0,{border_style},{outline},{shadow},{int(alignment)},{int(margin_l)},{int(margin_r)},{int(margin_v)},1\n"
        
        start_sec = max(0.0, float(altyazi['start']) - (0.08 if has_animation else 0.0))
        end_sec = float(altyazi['end'])
        start_time = saniye_to_ass_time(start_sec)
        end_time = saniye_to_ass_time(end_sec)
        text = altyazi['text'].replace('\n', '\\N')
        
        effect = ""
        if has_animation:
            # Daha hızlı pop-up (120ms)
            text = f"{{\\fad(120,120)}}{text}"

        olaylar += f"Dialogue: 0,{start_time},{end_time},{konusmaci},,0,0,0,{effect},{text}\n"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("[Script Info]\nTitle: Generated Subtitles\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\nPlayResX: 1080\nPlayResY: 1920\n\n")
        f.write(stiller)
        f.write(olaylar)
    
    return output_path

def altyazilari_videoya_ekle(video_yolu, altyazilar_data, output_folder, color_map=None, font_path=None, has_background=False, has_animation=False, is_bold=False, bg_opacity=0.5, margin_v=450, font_size: int = 60, outline_px: int = 3, shadow_px: int = 2, alignment: int = 2, crf: int = 20, fps: int | None = None, margin_l: int = 80, margin_r: int = 80):
    """Altyazı dosyası oluşturur ve FFmpeg'in subtitles filtresi ile videoya basar."""
    dosya_adi = os.path.basename(video_yolu)
    altyazili_video_yolu = os.path.join(output_folder, f"{os.path.splitext(dosya_adi)[0]}_altyazili.mp4")
    altyazi_dosya_yolu = os.path.join(output_folder, f"{os.path.splitext(dosya_adi)[0]}.ass")

    # Adım 1: Kullanılacak fontu belirle (yüklenen > varsayılan)
    active_font_path = None
    default_font_path = None
    fonts_dir = 'fonts'
    if os.path.exists(fonts_dir):
        font_files = [
            os.path.join(fonts_dir, f)
            for f in os.listdir(fonts_dir)
            if f.lower().endswith(('.ttf', '.otf'))
        ]
        if font_files:
            # En son eklenen/değiştirilen fontu seç
            default_font_path = max(font_files, key=lambda p: os.path.getmtime(p))
    active_font_path = font_path if font_path else default_font_path

    # Adım 2: Fontu .ass dosyasının yanına kopyala ki FFmpeg bulsun
    temp_font_path_in_output = None
    if active_font_path and os.path.exists(active_font_path):
        import shutil
        temp_font_path_in_output = os.path.join(output_folder, os.path.basename(active_font_path))
        shutil.copy(active_font_path, temp_font_path_in_output)
        try:
            print(f"Kullanılan font dosyası: {active_font_path}")
            print(f"ASS içinde kullanılacak aile adı: {_read_font_family_name(active_font_path)}")
        except Exception:
            pass

    # Adım 3: .ass altyazı dosyasını oluştur
    generate_ass_file(altyazilar_data, altyazi_dosya_yolu, color_map, active_font_path, has_background, has_animation, is_bold, bg_opacity, margin_v, font_size=font_size, outline_px=outline_px, shadow_px=shadow_px, alignment=alignment, margin_l=margin_l, margin_r=margin_r)

    # Adım 4: Altyazıyı videoya bas (fontsdir ile kopyaladığımız klasörü ve fallback olarak fonts/ klasörünü göster)
    altyazi_dosya_yolu_ffmpeg = altyazi_dosya_yolu.replace('\\', '/')
    output_folder_rel = output_folder.replace('\\', '/')
    fonts_dir_rel = 'fonts'
    # Bazı ffmpeg derlemeleri birden fazla dizini '|' ile ayırarak kabul eder
    vf_fontsdir = f"{output_folder_rel}|{fonts_dir_rel}"
    # Shell kullanılmadığı için tırnak gerekmez; relatif yollar boşluk içermiyor
    vf_filter = f"subtitles=filename={altyazi_dosya_yolu_ffmpeg}:fontsdir={vf_fontsdir}"

    command = [
        'ffmpeg',
        '-i', video_yolu,
        '-vf', vf_filter
    ]
    if fps:
        command += ['-r', str(int(fps))]
    command += [
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', str(int(crf)),
        '-threads', '2',
        '-movflags', '+faststart',
        '-c:a', 'copy',
        '-y',
        altyazili_video_yolu
    ]
    run_ffmpeg_command(command)
    
    # Adım 5: Geçici dosyaları temizle
    os.remove(altyazi_dosya_yolu)
    if temp_font_path_in_output and os.path.exists(temp_font_path_in_output):
        os.remove(temp_font_path_in_output)

    return altyazili_video_yolu


def _split_long_sentences(entries: list, max_chars_per_entry: int = 90) -> list:
    """Uzun metinleri nokta/soru/ünlem ve uygun bağlaçlara göre 2-3 parçaya böler.
    Çok uzun cümlede yaklaşık 80-100 karakteri geçmeyecek şekilde parçalara ayırır.
    Zamanı orantısal paylaştırır.
    """
    out = []
    for e in entries:
        text = (e.get('text') or '').strip()
        if not text:
            continue
        length = len(text)
        start = float(e.get('start', 0))
        end = float(e.get('end', start))
        dur = max(0.0, end - start)
        if length <= max_chars_per_entry or dur <= 0.4:
            out.append(e)
            continue
        # Cümle sınırlarına göre bölmeyi dene
        import re
        parts = re.split(r'(?<=[\.!?])\s+', text)
        parts = [p for p in parts if p]
        if len(parts) == 1:
            # Noktalama yoksa kabaca karakter sayısına göre 2-3 parçaya böl
            chunk = max_chars_per_entry
            parts = [text[i:i+chunk] for i in range(0, length, chunk)]
        total_chars = sum(len(p) for p in parts)
        t = start
        for p in parts:
            frac = (len(p) / total_chars) if total_chars else 1.0/len(parts)
            seg = max(0.3, dur * frac)
            seg_end = min(end, t + seg)
            out.append({
                'speaker': e.get('speaker', 'Konuşmacı 1'),
                'start': t,
                'end': seg_end,
                'text': p.strip()
            })
            t = seg_end
    return out

def gemini_altyazi_olustur(ses_dosya_yolu):
    """Gemini API'sini kullanarak sesten altyazı verisi oluşturur."""
    global aktif_api_key_index
    while aktif_api_key_index < len(API_KEYS):
        api_key = API_KEYS[aktif_api_key_index]
        try:
            genai.configure(api_key=api_key)

            # Güvenlik ayarlarını daha esnek hale getir
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            model = genai.GenerativeModel(
                'gemini-2.5-flash', # Model ismi kullanıcının isteğine göre güncellendi.
                safety_settings=safety_settings
            )
            
            print("Ses dosyası Gemini'ye yükleniyor...")
            audio_file = genai.upload_file(path=ses_dosya_yolu)
            
            prompt = """
            SENARYO: Sen, bir video için altyazı oluşturan profesyonel bir çevirmensin. Görevin, bir ses dosyasındaki konuşmaları analiz edip, bunları konuşmacılarına göre ayırarak akıcı ve doğal bir Türkçe ile altyazıya dönüştürmektir.

            ADIMLAR:
            1.  **KONUŞMACI ANALİZİ:** Ses dosyasındaki farklı konuşmacıları dikkatlice ayırt et. Her bir konuşmacı için tutarlı bir etiket kullan (örn. "Konuşmacı 1", "Konuşmacı 2"). Aynı kişi konuştuğunda etiketi DEĞİŞTİRME.
            2.  **METNE DÖKME:** Konuşmaların tamamını hatasız bir şekilde metne dök.
            3.  **TÜRKÇE'YE ÇEVİRİ (ZORUNLU):** Metne döktüğün TÜM CÜMLELERİ, anlam bütünlüğünü koruyarak, akıcı ve doğal bir Türkçe'ye çevir. Argo veya küfürlü ifadeleri, anlamı en yakın şekilde, sansürlemeden veya yumuşatarak çevir. Asla İngilizce veya başka bir dilde metin bırakma.
            4.  **JSON FORMATLAMA:** Sonucu, ZORUNLU olarak aşağıdaki JSON formatında, tüm metinler Türkçe olacak şekilde ver. Zaman damgaları saniye cinsinden ve hassas olmalıdır. Konuşma olmayan kısımları dahil etme. Eğer hiç konuşma yoksa, boş bir JSON dizisi `[]` döndür.

            ÖRNEK JSON ÇIKTISI:
            [
              {
                "speaker": "Konuşmacı 1",
                "start": 0.5,
                "end": 2.8,
                "text": "Bu uygulamanın harika çalıştığını düşünüyorum."
              },
              {
                "speaker": "Konuşmacı 2",
                "start": 3.1,
                "end": 5.2,
                "text": "Evet, kesinlikle katılıyorum."
              }
            ]
            """
            
            print("Gemini'den yanıt bekleniyor...")
            response = model.generate_content([prompt, audio_file])
            
            # Debug için yanıtı ve olası engelleme sebebini yazdır
            print("--- Gemini Ham Yanıtı ---")
            print(response)
            print("-------------------------")

            if not response.parts:
                feedback = response.prompt_feedback
                raise ValueError(f"Gemini'den boş yanıt alındı. Engellenme sebebi: {feedback.block_reason.name if feedback.block_reason else 'Bilinmiyor'}")

            json_response_text = response.text.strip().lstrip("```json").rstrip("```")
            
            if not json_response_text:
                 # Eğer hiç konuşma yoksa model boş bir dizi döndürmeli, bu bir hata değil.
                if "[]" in response.text:
                    return []
                raise ValueError("Gemini'den gelen yanıt metni boş. Ham yanıt: " + str(response))

            print("Ayıklanmış JSON Metni:", json_response_text)
            data = json.loads(json_response_text)
            # Uzun cümleleri 2-3 parçaya böl
            data = _split_long_sentences(data, max_chars_per_entry=90)
            return data

        except Exception as e:
            print(f"API anahtarı (index {aktif_api_key_index}) ile hata: {e}")
            aktif_api_key_index += 1
            if aktif_api_key_index >= len(API_KEYS):
                 raise Exception(f"Tüm API anahtarları denendi ve başarısız oldu. Son hata: {e}")
    raise Exception("Tüm API anahtarları denendi ve başarısız oldu.")
