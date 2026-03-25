# Logic V2 Call Realtime

Tai lieu nay dung de chot huong trien khai `v2` cho chuc nang goi khan cap realtime. Tai lieu nay duoc viet tren nen `v1` da co:

- tai khoan user
- dang nhap ben vung theo thiet bi
- PIN 4 so
- nhom gia dinh
- admin/member

Phan `v2` chi tap trung vao:

- goi khan cap bang giong noi
- audio call realtime
- incoming call native tren mobile
- fallback sang nguoi than tiep theo neu khong nghe may

Quyet dinh hien tai da chot:

- provider uu tien: `ZEGOCLOUD`
- backend dieu phoi: `Flask`
- client call: `Flutter native`

Khong lam trong v2 MVP:

- video call
- group call
- web call tren PWA
- call tren desktop browser

## 1. Muc tieu v2

Nguoi gia chi can noi mot cau tu nhien, vi du:

- "Goi con trai"
- "Goi con gai"
- "Goi chau"
- "Goi nguoi nha giup toi"

He thong se:

1. Nhan giong noi tren Flutter
2. Chuyen thanh text
3. Gui text len Flask
4. Flask dung AI hoac rule de hieu y dinh can goi
5. Flask map den dung nguoi than dua tren du lieu gia dinh
6. Tao `call_session`
7. Goi nguoi nhan dau tien
8. Neu sau 20-30 giay khong bat may thi fallback sang nguoi tiep theo
9. Khi nguoi nhan bat may thi vao audio call realtime
10. Luu log cuoc goi

## 2. Huong ky thuat da chot

Huong kha thi nhat cho v2:

- mobile app Flutter native
- Flask giu vai tro backend business logic
- AI chi dung de hieu y dinh va map quan he khi can
- phan media call dung SDK/RTC provider hoac nen tang call invitation co san
- incoming call phai la native incoming call, khong lam bang web page

Ket luan:

- khong nen lam chuc nang call nay tren Flask web/PWA hien tai
- nen co app Flutter rieng cho mobile
- uu tien Android truoc
- chi lam audio 1-1 o ban dau

## 3. Tai sao khong nen lam call tren web/PWA

Nhung van de lon cua realtime call:

- app dang chay nen
- may dang khoa man hinh
- incoming call can do chuong that
- thong bao can mo duoc man hinh nghe tu choi
- iOS va Android co rule rieng cho incoming call
- WebRTC can signaling + STUN/TURN

Neu lam tren web/PWA:

- incoming call khong on dinh bang app native
- background behavior yeu hon
- kho dat trai nghiem nhu cuoc goi that

Vay nen:

- `Flutter native` la huong dung

## 4. Scope MVP cua v2

Ban MVP nen nho va chac:

- chi audio call
- chi 1 nguoi goi -> 1 nguoi nhan tai moi thoi diem
- co fallback sang nguoi tiep theo
- co timeout ro rang
- co log trang thai cuoc goi

V2 MVP khong nen om them:

- video
- conference
- live subtitle
- ghi am
- AI noi chuyen trong luc call

## 5. Luong nghiep vu chinh

### 5.1 Luong goi khan cap tu giong noi

1. Nguoi gia mo app Flutter
2. Bam nut noi hoac app dang lang nghe theo che do da cho phep
3. Noi: `Goi con trai`
4. Flutter speech-to-text doi thanh text
5. Flutter goi API Flask, gui:
   - text
   - user_id hien tai
   - device info
6. Flask phan tich y dinh:
   - day la lenh goi
   - doi tuong can goi la `con trai`
7. Flask tra ve doi tuong muc tieu
8. Flask tao `call_session`
9. Flask lay danh sach nguoi co the nhan theo thu tu uu tien
10. Flask day cuoc goi den nguoi nhan dau tien
11. Nguoi nhan thay incoming call native
12. Neu bam `Nghe` thi vao call
13. Neu khong nghe trong 20-30 giay thi Flask fallback
14. Neu khong ai nghe thi session ket thuc voi trang thai `failed` hoac `missed`

### 5.2 Luong khi nguoi nhan nghe may

1. Nguoi nhan bam `Nghe`
2. App nguoi nhan gui len backend la `accept`
3. Backend danh dau `call_session = accepted`
4. Backend khong goi nhung target khac nua
5. Hai ben vao kenh audio realtime
6. Ket thuc cuoc goi thi backend luu `ended`

### 5.3 Luong fallback

1. Session duoc tao
2. He thong ring nguoi A
3. Sau 25 giay A khong nghe
4. Danh dau target A la `timeout`
5. Chuyen sang nguoi B
6. Ring nguoi B
7. Neu B nghe thi dung
8. Neu B cung khong nghe thi tiep tuc nguoi C neu co
9. Neu het nguoi thi session `failed`

## 6. Nguyen tac map quan he

AI khong nen tu do doan nguoi duoc goi.

AI chi nen lam:

- nhan ra day la lenh `call`
- trich xuat nhan quan he:
  - con trai
  - con gai
  - chau
  - vo
  - chong
  - em
  - anh
  - chi

Con viec map cuoi cung phai dua vao data co cau truc trong he thong.

Rule:

- AI chi xac dinh `intent` va `relationship_key`
- Flask map `relationship_key` -> user_id theo du lieu da luu
- Neu co nhieu nguoi trung quan he thi backend can co `priority`
- Neu cau noi mo ho, app hoi lai ngan:
  - `Bac muon goi con trai hay con gai a?`

## 7. Du lieu moi can them cho v2

Toi thieu can co cac bang sau:

### device_push_tokens

Luu token de gui notification/invitation:

- id
- user_id
- device_id
- platform
- push_token
- is_active
- created_at
- updated_at

### family_relationships

Luu quan he giua user goi va user nhan trong nhom gia dinh:

- id
- family_group_id
- owner_user_id
- relative_user_id
- relationship_key
- priority_order
- is_active
- created_at
- updated_at

Vi du:

- owner_user_id = nguoi gia
- relative_user_id = con trai
- relationship_key = `son`
- priority_order = 1

Co the co nhieu dong:

- `son`
- `daughter`
- `grandchild`
- `wife`
- `husband`

### call_sessions

Bang session cuoc goi:

- id
- room_id
- initiated_by_user_id
- caller_user_id
- trigger_source
- transcript_text
- detected_intent
- relationship_key
- status
- accepted_by_user_id
- started_at
- accepted_at
- ended_at
- end_reason
- created_at
- updated_at

Gia tri goi y:

- trigger_source: `voice`, `manual_button`
- status:
  - `created`
  - `ringing`
  - `accepted`
  - `declined`
  - `timeout`
  - `missed`
  - `ended`
  - `failed`

### call_session_targets

Luu tung nguoi duoc goi trong 1 session:

- id
- call_session_id
- target_user_id
- priority_order
- status
- rung_at
- responded_at
- response_reason
- created_at
- updated_at

Gia tri:

- status:
  - `pending`
  - `ringing`
  - `accepted`
  - `declined`
  - `timeout`
  - `skipped`
  - `missed`

### call_events

Bang log chi tiet:

- id
- call_session_id
- event_type
- actor_user_id
- payload_json
- created_at

Su dung de debug va theo doi timeline.

## 8. Quan he giua v1 va v2

V1 da co `family group`, nhung chua du de goi.

V2 can bo sung:

- ai la nguoi gia / ai la nguoi cham soc
- trong mot family, quan he giua 2 user la gi
- thu tu uu tien khi goi

Khong nen suy luan quan he chi bang role admin/member.

Can co man hinh setup:

- Chon user A la `nguoi can duoc ho tro`
- Chon user B la `con trai`
- Chon user C la `con gai`
- Chon user D la `chau`
- Chon thu tu uu tien khi fallback

## 9. Dinh nghia relationship_key

Nen chot 1 bo key on dinh:

- `son`
- `daughter`
- `grandchild`
- `wife`
- `husband`
- `brother`
- `sister`
- `caregiver`
- `family_member`

Phia AI se map tu cum tu tu nhien sang key nay.

Vi du:

- "con trai" -> `son`
- "con gai" -> `daughter`
- "chau" -> `grandchild`

## 10. State machine cho call_session

### Session level

- `created`
  - vua tao session
- `ringing`
  - dang ring it nhat 1 target
- `accepted`
  - da co nguoi nhan nghe
- `declined`
  - tat ca target tu choi
- `timeout`
  - target hien tai timeout va khong con target tiep theo
- `missed`
  - khong ai nghe
- `ended`
  - cuoc goi da noi va da ket thuc
- `failed`
  - loi he thong hoac khong tim duoc target hop le

### Target level

- `pending`
- `ringing`
- `accepted`
- `declined`
- `timeout`
- `skipped`

## 11. Rule fallback can chot

Gia tri khuyen nghi:

- moi target duoc ring trong `25 giay`
- fallback toi da `3 nguoi`
- neu da co nguoi `accepted` thi dung ngay
- khong ring song song o MVP de de quan ly

Tai sao khong ring song song:

- de roi vao tinh huong 2 nguoi cung bat may
- kho giai thich cho nguoi gia
- luong support phuc tap hon

Vay nen:

- ring theo thu tu, tung nguoi mot

## 12. Luong AI detect intent

AI can rat nhe, khong nen bien thanh chatbot phuc tap o luong khan cap.

Input:

- transcript text
- possible relationship labels trong family cua user

Output chuan hoa:

```json
{
  "type": "call",
  "relationship_key": "son",
  "confidence": 0.95,
  "needs_confirmation": false
}
```

Neu mo ho:

```json
{
  "type": "call",
  "relationship_key": null,
  "confidence": 0.42,
  "needs_confirmation": true,
  "question": "Bac muon goi con trai hay con gai a?"
}
```

Rule:

- Neu confidence cao thi goi ngay
- Neu confidence thap thi hoi lai
- Neu khong tim thay target hop le thi thong bao ro

## 13. Incoming call native

Phan nay la bat buoc neu muon trai nghiem dung.

Nguoi nhan phai thay:

- ten nguoi goi
- label nhu `Cuoc goi khan cap`
- nut `Nghe`
- nut `Tu choi`

Nguoi nhan bam vao la vao call ngay.

Day la ly do nen dung:

- Flutter native
- incoming call UI native
- provider/SDK co ho tro call invitation

## 14. Vai tro cua Flask trong v2

Flask khong truyen media.

Flask chi nen lam:

- xac thuc request
- xac dinh session cuoc goi
- tim target
- tao log
- quan ly fallback
- cap nhat state cuoc goi
- giao tiep voi push/provider API
- cung cap signaling neu tu build WebRTC

Khong nen de Flask:

- xu ly media stream
- giu audio stream

## 15. Provider strategy

Co 2 huong:

### Huong A: Managed provider

Vi du:

- ZEGOCLOUD
- Agora

Uu diem:

- nhanh ra MVP
- co incoming call invitation
- giam cong signaling/TURN
- giam rui ro

Nhuoc diem:

- ton phi
- phu thuoc vendor

### Huong B: Tu build bang WebRTC

Stack:

- Flutter + flutter_webrtc
- Flask Socket.IO signaling
- coturn
- FCM/APNs

Uu diem:

- tu chu
- linh hoat

Nhuoc diem:

- kho hon nhieu
- test background call met hon
- rui ro production cao hon

Ket luan cho v2:

- Uu tien `Huong A`

## 16. API de xuat cho v2

### Voice intent

- `POST /api/calls/voice-intent`

Input:

- transcript_text
- device_id

Output:

- action = `calling`
- call_session_id
- room_id
- target_preview

hoac:

- action = `confirm`
- question

### Tao session call thu cong

- `POST /api/calls`

Input:

- relationship_key

### Trang thai session

- `GET /api/calls/{call_session_id}`

### Accept

- `POST /api/calls/{call_session_id}/accept`

### Decline

- `POST /api/calls/{call_session_id}/decline`

### End call

- `POST /api/calls/{call_session_id}/end`

### Webhook/provider callback

- `POST /api/calls/provider/webhook`

### Danh sach log call

- `GET /api/calls/history`

## 17. Payload mau cho call session

```json
{
  "call_session_id": 101,
  "room_id": "e65a1f2d-0d7b-4ee2-a4bb-1e1c19f11a20",
  "status": "ringing",
  "caller": {
    "id": 12,
    "full_name": "Ba Nguyen"
  },
  "current_target": {
    "id": 18,
    "full_name": "Nguyen Van B",
    "relationship_key": "son",
    "priority_order": 1
  },
  "timeout_seconds": 25
}
```

## 18. Rule UX cho nguoi gia

Phai cuc ky don gian:

- nut noi to
- chu lon
- phan hoi bang voice
- xac nhan ngan gon khi mo ho
- khong bat user thao tac nhieu buoc

Vi du:

- Nguoi gia noi: `Goi con`
- App tra loi bang am thanh:
  - `Bac muon goi con trai hay con gai a?`

Neu AI da chac:

- `Dang goi con trai cho bac`

## 19. Rule UX cho nguoi nhan

Nguoi nhan can thay:

- ai dang goi
- day la cuoc goi khan cap
- co the nghe ngay
- neu bo lo thi vao lich su thay `cuoc goi nho`

## 20. Rule loi va fail-safe

Can xu ly ro rang:

- khong tim thay relationship_key
- family chua setup quan he
- nguoi duoc goi khong co device token
- provider loi
- call timeout
- khong ai nghe

Thong bao cho nguoi gia phai de hieu:

- `Toi chua tim thay nguoi can goi`
- `Gia dinh chua cai dat nguoi nhan cuoc goi nay`
- `Khong co ai nghe may luc nay`

## 21. Thu tu trien khai de xuat

Nen lam theo thu tu nay:

1. Bo sung DB cho call + relationship + push token
2. Lam man hinh setup quan he va uu tien trong family
3. Flutter gui transcript voice len Flask
4. Flask detect intent va tao call_session
5. Noi provider incoming call
6. Lam accept/decline/end
7. Lam fallback 25 giay
8. Lam call history
9. Toi uu UX va retry

## 22. Cac quyet dinh da chot cho v2

- V2 tap trung vao call realtime
- Chi audio call trong MVP
- Chi 1-1 call trong MVP
- Trigger chinh la giong noi
- AI chi dung de detect intent va relationship
- Mapping nguoi nhan phai dua vao data co cau truc
- Flask la bo nao dieu phoi
- Incoming call phai native
- Co fallback 20-30 giay sang nguoi tiep theo
- Neu khong ai nghe thi ket thuc session va thong bao ro
- Uu tien Flutter native + managed call provider

## 23. Viec can chot tiep truoc khi code

Truoc khi code that, can chot them 5 dieu:

1. Chon provider nao:
   - ZEGOCLOUD
   - Agora
   - hay tu build WebRTC

2. V2 co lam Android truoc khong

3. Quan he nao duoc ho tro trong MVP:
   - son
   - daughter
   - grandchild
   - caregiver
   - family_member

4. Fallback toi da may nguoi

5. Timeout cu the la 20, 25 hay 30 giay

## 24. De xuat chot cho MVP

MVP minh de xuat:

- Android first
- audio only
- 1-1 only
- timeout 25 giay
- fallback toi da 3 nguoi
- relationship MVP:
  - `son`
  - `daughter`
  - `grandchild`
  - `caregiver`
  - `family_member`
- provider: uu tien 1 nen tang managed de ra nhanh
