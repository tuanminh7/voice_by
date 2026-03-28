# Tro ly voice cho nguoi lon tuoi

Project nay duoc dung bang Flask va Gemini. Hien tai app da duoc nang cap len v1 voi luong dang ky, dang nhap, ghi nho dang nhap, PIN 4 so theo thiet bi, quan ly ho so va nhom gia dinh co admin/member, dong thoi van giu chatbot va voice UI de tiep tuc mo rong.

## Tinh nang chinh

- Dang ky va dang nhap bang email hoac so dien thoai + mat khau
- Ghi nho dang nhap lau dai va mo app bang PIN 4 so tren thiet bi da dang ky
- API quan ly ho so, doi mat khau, quen mat khau va dat lai mat khau
- API nhom gia dinh: tao nhom, moi thanh vien, chap nhan loi moi, doi role admin/member, roi nhom
- Chatbot Gemini van hoat dong sau khi mo khoa bang PIN, co voice input va doc lai bang Speech Synthesis
- Ho tro `manifest.json` va `service worker` de san sang cho PWA

## Cau truc thu muc

```text
ut_nguyen/
|-- app.py
|-- mobile_app/
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

## Mobile V2

- Client Flutter cho v2 duoc dat trong thu muc `mobile_app/`
- Thu muc `mobile_app/` da la project Flutter day du voi `android/` va `ios/`
- Da co scaffold mobile cho:
  - login/register
  - PIN setup / unlock
  - lay du lieu gia dinh hien tai
  - map quan he goi khan cap bang thanh vien that trong gia dinh
  - voice intent call
  - active call polling
  - call history
- Realtime media/native incoming call van dang cho cau hinh Firebase Messaging + ZEGOCLOUD

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

Neu chay mobile:

1. Vao thu muc `mobile_app`
2. Chay:

```powershell
D:\Flutter\flutter\bin\flutter.bat pub get
D:\Flutter\flutter\bin\flutter.bat run
```

Luu y:

- SQLite `app.db` se duoc tao tu dong khi app khoi dong lan dau.
- O luong "quen mat khau", ban local hien tra ve `reset_token` truc tiep de test nhanh. Ban production can noi them email service.

## Bien moi truong

- `GEMINI_API_KEY`: bat buoc de goi Gemini
- `GEMINI_MODEL`: tuy chon, mac dinh `gemini-2.5-flash`
- `FLASK_SECRET_KEY`: khoa session cho Flask
- `PORT`: cong chay app
- `CALL_PROVIDER`: mac dinh `zegocloud`
- `CALL_RING_TIMEOUT_SECONDS`: mac dinh `25`
- `CALL_MAX_TARGETS`: mac dinh `3`

## Ghi chu trien khai

- `render.yaml` da co san cho Render
- Can bo sung `GEMINI_API_KEY` tren nen tang deploy
- Render se health-check qua duong dan `/health`
- Du lieu auth/family dang luu bang SQLite (`app.db`)
- SQLite tren Render chi phu hop de test nhanh vi filesystem cua web service khong phai lua chon ben vung cho production
- Chat history hien van la in-memory, neu muon production on dinh hon nen dua phan nay vao Redis hoac database

## Deploy Render

1. Push repo len GitHub.
2. Tao Web Service tren Render tu repo nay.
3. Render se doc `render.yaml` tu dong.
4. Dien `GEMINI_API_KEY` trong trang env vars cua service.
5. Deploy xong, mo:

```text
https://<render-service>.onrender.com/health
```

Neu thay JSON `ok` thi backend da san sang cho mobile tro vao.

## File bug_fix

Trong qua trinh lam, cac loi gap va cach xu ly da duoc ghi vao `bug_fix.txt` de lan sau co the tai su dung kinh nghiem nhanh hon.
