# Tro ly voice cho nguoi lon tuoi

Project nay duoc dung bang Flask va Gemini, bam sat theo hai file `cautruc.txt` va `logic.txt`. Ung dung ho tro chat thuong, voice input, streaming response, doc cau tra loi bang tieng Viet va dong goi PWA co the cai len may.

## Tinh nang chinh

- Backend Flask co 2 API: `/chat` va `/chat_stream`
- Luu nho hoi thoai theo session de tao cam giac tro chuyen lien mach
- Tim phan noi dung lien quan trong `chatbot.txt` truoc khi tao prompt
- Frontend co o chat, nut voice, doc lai bang Speech Synthesis
- Ho tro `manifest.json` va `service worker` de san sang cho PWA

## Cau truc thu muc

```text
ut_nguyen/
|-- app.py
|-- chatbot.txt
|-- requirements.txt
|-- render.yaml
|-- .env.example
|-- README.md
|-- bug_fix.txt
|-- templates/
|   `-- index.html
`-- static/
    |-- style.css
    |-- script.js
    |-- manifest.json
    |-- sw.js
    `-- icon.png
```

## Cach chay local

1. Tao virtual environment va kich hoat:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Cai thu vien:

```powershell
pip install -r requirements.txt
```

3. Tao file `.env` tu `.env.example` va dien `GEMINI_API_KEY`.

4. Chay app:

```powershell
python app.py
```

5. Mo trinh duyet tai `http://127.0.0.1:5000`

## Bien moi truong

- `GEMINI_API_KEY`: bat buoc de goi Gemini
- `GEMINI_MODEL`: tuy chon, mac dinh `gemini-2.5-flash`
- `FLASK_SECRET_KEY`: khoa session cho Flask
- `PORT`: cong chay app

## Ghi chu trien khai

- `render.yaml` da co san cho Render
- Can bo sung `GEMINI_API_KEY` tren nen tang deploy
- Neu muon production on dinh hon, nen thay memory in-memory bang Redis, SQLite hoac database

## File bug_fix

Trong qua trinh lam, cac loi gap va cach xu ly da duoc ghi vao `bug_fix.txt` de lan sau co the tai su dung kinh nghiem nhanh hon.
