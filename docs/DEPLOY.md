# คู่มือการ Deploy และดูแลระบบ — เซ้งร้านด่วน.com

เอกสารนี้สรุปขั้นตอนการนำระบบขึ้น Production ด้วย Docker Compose และ Cloudflare Tunnel บน Linux Home Server / VPS

---

## 1. การเตรียมตัวครั้งแรก (First-Time Setup)

### 1.1 สร้างไฟล์คอนฟิก `.env.prod`
```bash
cp .env.prod.example .env.prod
nano .env.prod
```
กรอกข้อมูลสำคัญ:
- `SECRET_KEY`: สร้างด้วย `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`
- `SITE_URL`: เช่น `https://sengranduan.com`
- `ALLOWED_HOSTS` & `CSRF_TRUSTED_ORIGINS`: ใส่โดเมนจริงของคุณ
- `DB_PASSWORD`: ตั้งรหัสผ่านฐานข้อมูลที่แข็งแรง
- `CLOUDFLARE_TUNNEL_TOKEN`: รับ Token จาก Cloudflare Zero Trust (Tunnels > Add a Tunnel)
- `EASYSLIP_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EMAIL_HOST_PASSWORD`

### 1.2 เชื่อมต่อ Cloudflare Tunnel กับ Nginx
ใน Cloudflare Zero Trust Dashboard ให้ตั้งค่า Public Hostname ดังนี้:
- **Subdomain / Domain**: `sengranduan.com` และ `www.sengranduan.com`
- **Service Type**: `HTTP`
- **URL**: `nginx:80` (หรือ `localhost:80`)

---

## 2. การสั่งรันระบบ (Build & Start)

```bash
# 1. Build Docker images และ Start services ทั้งหมด
docker compose --env-file .env.prod up -d --build

# 2. ตรวจสอบการทำงานของแต่ละ Container
docker compose ps

# 3. ดู Logs แบบ Real-time
docker compose logs -f web nginx

# 4. ทดสอบ Healthcheck
curl -s http://127.0.0.1:8000/healthz
# ได้รับ: {"status": "ok", "db": "ok"}
```

เมื่อ container `web` เริ่มทำงาน สคริปต์ `entrypoint.sh` จะรันสิ่งต่อไปนี้ให้อัตโนมัติ:
1. `python manage.py migrate --noinput`
2. `python manage.py createcachetable`
3. `python manage.py collectstatic --noinput`
4. `python manage.py check --deploy`

---

## 3. การสร้างบัญชีแอดมิน (Superuser)

```bash
docker compose exec web python manage.py createsuperuser
```

---

## 4. การตั้งค่า Cron Jobs สำหรับ Backup และทำความสะอาด Session

เปิด crontab บนเครื่องเซิร์ฟเวอร์:
```bash
crontab -e
```
ใส่บรรทัดคำสั่งต่อไปนี้:
```cron
# สำรองข้อมูลฐานข้อมูลและไฟล์ Media ทุกวันเวลา 03:00 น.
0 3 * * * /home/user/proptech/scripts/backup.sh >> /var/log/proptech_backup.log 2>&1

# เคลียร์ Django Session ที่หมดอายุทุกวันเวลา 03:30 น.
30 3 * * * cd /home/user/proptech && docker compose exec -T web python manage.py clearsessions >> /var/log/proptech_clearsessions.log 2>&1
```

---

## 5. การทดสอบ Restore ฐานข้อมูล

เพื่อความมั่นใจว่าไฟล์ Backup สามารถนำกลับมาใช้ได้จริงเสมอ:
```bash
./scripts/restore.sh ./backups/2026-10-23/db_proptech_db_xxx.dump
```

---

## 6. แผนการ Rollback เมื่อเกิดปัญหา (Rollback Strategy)

หากการอัปเดตโค้ดใหม่มีปัญหา:
1. **Rollback ฐานข้อมูล**:
   ```bash
   # สำรองข้อมูลปัจจุบันก่อน
   ./scripts/backup.sh
   # Restore กลับไปยังจุดก่อน Deploy
   docker exec -i proptech_postgres pg_restore -U proptech_user -d proptech_db --clean --if-exists < ./backups/PRE_DEPLOY.dump
   ```
2. **Rollback Docker Container**:
   ```bash
   # Rebuild กลับไปยัง Git Commit ที่เสถียร
   git checkout <stable_commit_hash>
   docker compose --env-file .env.prod up -d --build
   ```
