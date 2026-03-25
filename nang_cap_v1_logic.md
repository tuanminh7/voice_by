# Nang Cap V1

Tai lieu nay dung de chot logic cho ban nang cap v1. Pham vi cua v1 chi gom:

- dang ky
- dang nhap
- ghi nho trang thai dang nhap
- PIN 4 so de vao app nhanh tren thiet bi da dang nhap
- quen mat khau
- tai khoan ca nhan
- nhom gia dinh va vai tro admin

Chua lam trong v1:

- goi khan cap
- WebRTC
- push notification
- xac minh email
- xac minh so dien thoai

## 1. Muc tieu v1

Ung dung sau khi nang cap v1 can dat duoc cac muc tieu sau:

- Nguoi dung co the tao tai khoan bang email, so dien thoai, ten, tuoi va mat khau.
- Nguoi dung chi can dang nhap mat khau o lan dau hoac sau khi da chu dong dang xuat.
- Sau khi dang nhap thanh cong, app ghi nho phien dang nhap lau dai.
- App cho tao PIN 4 so tren thiet bi hien tai de mo app nhanh.
- Neu nguoi dung quen mat khau nhung van con dang nhap tren may, ho van co the vao app bang PIN va doi mat khau trong cai dat.
- Neu nguoi dung da dang xuat hoac doi may, PIN cu khong con dung duoc.
- Tai khoan ca nhan co the tao nhom gia dinh hoac duoc them vao nhom gia dinh.
- Moi nhom gia dinh co it nhat 1 admin quan ly.

## 2. Kieu tai khoan

He thong co 2 kieu su dung trong giao dien, nhung thuc te chi nen co 1 bang user va 1 bang nhom:

- Tai khoan ca nhan:
  - la 1 user thong thuong
  - co the dung doc lap
  - co the ket ban voi user khac
  - co the tao nhom gia dinh
  - co the duoc moi vao nhom gia dinh

- Tai khoan gia dinh:
  - khong nen tach thanh 1 bang login rieng
  - ban chat la 1 nhom gia dinh do 1 user tao ra
  - user tao nhom mac dinh la admin dau tien
  - cac thanh vien khac duoc them vao nhom theo role

Ket luan thiet ke:

- Dang nhap luon bang tai khoan user.
- "Tai khoan gia dinh" chi la cach the hien user dang so huu hoac dang tham gia mot family group.

## 3. Du lieu bat buoc khi dang ky

Bat buoc:

- email
- so dien thoai
- ho ten
- tuoi
- mat khau

Khong bat buoc o v1:

- xac minh email
- xac minh OTP dien thoai

Rule validate toi thieu:

- email dung dinh dang co ban
- so dien thoai chi gom ky tu hop le va do dai hop ly
- email phai la duy nhat trong he thong
- so dien thoai phai la duy nhat trong he thong
- tuoi phai la so hop le
- mat khau dat do dai toi thieu

Luu y:

- He thong chi kiem tra format va tinh duy nhat.
- Neu nguoi dung tu nhap sai email hoac so dien thoai, he thong khong chiu trach nhiem xac minh ho.

## 4. Cac bang du lieu de trien khai

Toi thieu nen co cac bang sau:

### users

Luu thong tin tai khoan:

- id
- full_name
- age
- email
- phone_number
- password_hash
- is_active
- created_at
- updated_at

### family_groups

Luu thong tin nhom gia dinh:

- id
- family_name
- created_by_user_id
- created_at
- updated_at

### family_members

Bang lien ket user voi nhom gia dinh:

- id
- family_group_id
- user_id
- role
- status
- joined_at

Gia tri goi y:

- role: `admin`, `member`
- status: `active`, `invited`, `removed`

### friendships

Luu quan he ket ban giua cac user:

- id
- requester_id
- addressee_id
- status
- created_at
- updated_at

Gia tri goi y:

- status: `pending`, `accepted`, `rejected`, `blocked`

### user_devices

Luu trang thai dang nhap tren thiet bi va PIN cua thiet bi:

- id
- user_id
- device_id
- device_name
- refresh_token_hash
- pin_code_hash
- pin_enabled
- last_login_at
- last_seen_at
- is_revoked
- created_at
- updated_at

### password_reset_tokens

Luu phuc hoi mat khau:

- id
- user_id
- token_hash
- expires_at
- used_at
- created_at

## 5. Logic dang ky

Luong xu ly:

1. Nguoi dung nhap email, so dien thoai, ho ten, tuoi, mat khau.
2. Backend validate du lieu.
3. Neu email hoac so dien thoai da ton tai thi bao loi.
4. Backend hash mat khau roi tao user.
5. Backend tao phien dang nhap dau tien cho thiet bi hien tai.
6. Backend tra ve thong tin user va token.
7. App chuyen sang man hinh tao PIN 4 so.
8. Nguoi dung tao PIN thanh cong xong moi vao man hinh chinh.

Luu y UX:

- O buoc cuoi dang ky nen co man hinh nhac nguoi dung kiem tra lai email va so dien thoai.
- Co the them o nhap lai mat khau de giam go nham.

## 6. Logic dang nhap

Nguoi dung co the dang nhap bang:

- email + mat khau
- hoac so dien thoai + mat khau

Luong xu ly:

1. Nguoi dung nhap thong tin dang nhap.
2. Backend tim user theo email hoac so dien thoai.
3. Backend kiem tra password_hash.
4. Neu dung thi tao hoac cap nhat device session cho may do.
5. Backend tra ve access token + refresh token + thong tin user.
6. App luu token an toan trong may.
7. Neu may nay chua co PIN thi yeu cau tao PIN.
8. Neu da co PIN roi thi vao app.

## 7. Logic ghi nho dang nhap

Muc tieu:

- Sau khi dang nhap mot lan, nhung lan mo app sau khong can nhap mat khau lai.
- Chi khi nguoi dung tu dang xuat moi phai nhap mat khau lai.

Luong xu ly khi mo app:

1. App kiem tra co session hop le trong may khong.
2. Neu co refresh token hop le:
   - app thu lam moi access token
   - neu thanh cong thi vao man hinh nhap PIN hoac vao thang app tuy trang thai khoa PIN
3. Neu khong con phien hop le:
   - chuyen ve man hinh dang nhap

Rule:

- Khong tu dong dang xuat nguoi dung neu token het han.
- App se uu tien refresh token trong nen.
- Dang xuat chi xay ra khi:
  - user bam dang xuat
  - admin hoac he thong thu hoi thiet bi
  - refresh token bi revoke hoac khong hop le nua

## 8. Logic PIN 4 so

PIN la khoa mo nhanh tren thiet bi hien tai, khong phai mat khau tai khoan.

Rule quan trong:

- PIN chi co gia tri tren thiet bi da tao PIN.
- PIN khong dung de dang nhap tren may moi.
- PIN khong thay the chuc nang khoi phuc tai khoan.
- Sau khi dang xuat, PIN cua session do phai mat hieu luc.

Luong tao PIN:

1. Sau khi dang ky hoac dang nhap thanh cong, app yeu cau tao PIN 4 so.
2. Nguoi dung nhap PIN lan 1.
3. Nguoi dung xac nhan PIN lan 2.
4. App gui PIN da ma hoa hoac gui len backend qua kenh bao mat.
5. Backend luu `pin_code_hash` theo `user_devices`.
6. Danh dau `pin_enabled = true`.

Luong vao app bang PIN:

1. App mo len, tim thay session hop le.
2. App hien man hinh nhap PIN.
3. Nguoi dung nhap dung PIN thi vao app.
4. Neu sai PIN:
   - thong bao sai PIN
   - gioi han so lan thu sai
5. Neu sai qua nhieu lan:
   - khoa tam thoi man hinh PIN
   - cho dang nhap lai bang mat khau

Goi y bao mat:

- Khong luu PIN dang text thuong.
- Hash PIN truoc khi luu.
- Co the them dem so lan nhap sai va thoi gian khoa tam thoi.

## 9. Logic quen mat khau

Can tach 2 tinh huong:

### Truong hop A: quen mat khau nhung van con dang nhap tren may

Day la truong hop uu tien cho app nay.

Luong:

1. Nguoi dung mo app.
2. App cho vao bang PIN.
3. Trong phan cai dat tai khoan co muc "Doi mat khau".
4. Neu muon de nhe hon cho nguoi gia, co the cho phep:
   - nhap mat khau moi
   - xac nhan mat khau moi
   - khong bat buoc nhap mat khau cu
5. Backend cap nhat password_hash.

Khuyen nghi:

- Khi doi mat khau trong luc user dang con session hop le va da qua man hinh PIN, co the cho doi mat khau ma khong can mat khau cu.
- Nhung nen ghi log hoac danh dau su kien doi mat khau.

### Truong hop B: da dang xuat hoac doi may, khong con vao duoc bang PIN

Luc nay phai dung luong khoi phuc tai khoan.

V1 goi y lam ban nhe:

1. User bam "Quen mat khau".
2. Nhap email da dang ky.
3. He thong gui link dat lai mat khau qua email.
4. User bam link va dat mat khau moi.

Neu chua muon gui email that o buoc dau thi co the tam thoi:

- chi ghi logic vao note
- hoac lam admin ho tro reset thu cong trong giai doan phat trien noi bo

## 10. Logic dang xuat

Luc user bam dang xuat:

1. App hien hop thoai xac nhan.
2. Neu user xac nhan:
   - goi API dang xuat
   - backend revoke refresh token cua thiet bi hien tai
   - app xoa access token, refresh token va thong tin session local
   - app xoa trang thai mo khoa bang PIN cua session do
3. Chuyen ve man hinh dang nhap

Rule:

- Dang xuat xong thi khong duoc dung PIN cu de vao lai.
- Muon vao lai phai dang nhap bang mat khau, sau do co the tao lai PIN.

## 11. Logic ket ban

Tai khoan ca nhan co the ket ban voi user khac.

Luong de xuat:

1. Tim user qua email hoac so dien thoai.
2. Gui loi moi ket ban.
3. Nguoi nhan dong y hoac tu choi.
4. Khi dong y thi tao quan he ban be.

Muc dich cua tinh nang nay trong v1:

- lam nen cho viec moi vao nhom gia dinh
- chon thanh vien de dua vao gia dinh de sau nay phuc vu chuc nang call

## 12. Logic nhom gia dinh

### Tao nhom gia dinh

1. User dang nhap.
2. User chon tao nhom gia dinh.
3. Nhap ten nhom, vi du: "Gia dinh co Lan".
4. Backend tao `family_groups`.
5. Backend tao ban ghi `family_members` cho user do voi role `admin`.

### Them thanh vien vao nhom

1. Admin vao man hinh gia dinh.
2. Chon them thanh vien.
3. Tim user can them, uu tien trong danh sach ban be.
4. Gui loi moi vao nhom.
5. User nhan loi moi va chap nhan.
6. He thong tao hoac cap nhat `family_members` thanh `active`.

### Quyen admin

Admin co the:

- sua ten nhom gia dinh
- moi them thanh vien
- xoa thanh vien khoi nhom
- gan them admin cho thanh vien khac neu can

Member thuong co the:

- xem danh sach thanh vien
- cap nhat thong tin ca nhan cua minh
- roi nhom neu he thong cho phep

Rule quan trong:

- Moi nhom phai luon con it nhat 1 admin.
- Khong duoc xoa admin cuoi cung neu chua chuyen quyen cho nguoi khac.

## 13. Man hinh de xuat cho v1

Danh sach man hinh nen co:

- splash / khoi dong
- dang ky
- dang nhap
- tao PIN 4 so
- nhap PIN 4 so
- quen mat khau
- trang chu
- ho so ca nhan
- doi mat khau
- quan ly nhom gia dinh
- moi vao gia dinh
- danh sach ban be / loi moi ket ban
- cai dat

## 14. API de xuat cho v1

Danh sach API de sau nay code:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/pin/setup`
- `POST /auth/pin/verify`
- `POST /auth/pin/reset`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `GET /me`
- `PATCH /me`
- `POST /me/change-password`
- `POST /friends/request`
- `POST /friends/respond`
- `GET /friends`
- `GET /friends/requests`
- `POST /families`
- `GET /families/current`
- `PATCH /families/current`
- `POST /families/current/invitations`
- `POST /families/current/invitations/respond`
- `PATCH /families/current/members/{member_id}/role`
- `DELETE /families/current/members/{member_id}`

## 15. Thu tu trien khai de xuat

Nen lam theo thu tu nay:

1. Bo sung database va model.
2. Lam dang ky, dang nhap, refresh token, dang xuat.
3. Lam user_devices va PIN 4 so.
4. Lam ho so ca nhan va doi mat khau.
5. Lam quen mat khau.
6. Lam friendship.
7. Lam family_groups va family_members.
8. Sau khi v1 on dinh moi mo rong sang chuc nang call.

## 16. Cac quyet dinh da chot

Day la cac quyet dinh da duoc thong nhat trong buoi trao doi:

- Email va so dien thoai la bat buoc khi dang ky.
- Khong can xac minh email.
- Khong can xac minh so dien thoai.
- Neu nguoi dung nhap sai email hoac so dien thoai thi ho tu chiu trach nhiem.
- Sau khi dang ky hoac dang nhap thanh cong, app phai ghi nho trang thai dang nhap.
- Nguoi dung chi can nhap mat khau lai khi da chu dong dang xuat.
- App su dung PIN 4 so de mo nhanh tren thiet bi hien tai.
- Neu quen mat khau nhung van con session tren may, co the vao bang PIN roi doi mat khau.
- Chuc nang call de lam o giai doan sau, khong nam trong v1.

## 17. Ghi chu ky thuat cho code hien tai

Hien tai du an dang la Flask app don gian, chua co:

- database
- user model
- auth system
- token system
- family data model
- Flutter app rieng

Vi vay khi code v1 se la mot dot nang cap lon, can bo sung cau truc backend truoc. Khong nen chen logic auth vao session memory hien tai dang dung cho chat.
