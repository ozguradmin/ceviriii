# Deploy Kılavuzu

## Render (Önerilen - Backend)
1. Bu repo'yu GitHub'a push edin.
2. Render.com > New + > Blueprint > repo olarak bu projeyi seçin.
3. Ortaya çıkan serviste `subtitle-studio-backend` Web Service kurulacak.
4. Env Vars:
   - `GEMINI_API_KEYS` = anahtar(lar)ınızı virgülle verin.
5. Diske yazma için otomatik `/static/outputs` mount edilir.
6. Deploy sonrası URL örn: `https://subtitle-studio-backend.onrender.com`

## Netlify (Frontend)
- `static/` klasörünü publish edin.
- Netlify Site Settings > Environment > `API_BASE=https://subtitle-studio-backend.onrender.com`
- Alternatif: `templates/index.html` içindeki `window.API_BASE` değişkenini direkt set edin.

## Lokal Çalıştırma
```
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
set GEMINI_API_KEYS=anahtar1,anahtar2
python app.py
```

Tarayıcı: http://127.0.0.1:5001
