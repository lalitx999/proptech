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
- `SITE_URL`: เช่น `https://www.xn--72ch2atb1d4a4f1fudfc.com`
- `ALLOWED_HOSTS` & `CSRF_TRUSTED_ORIGINS`: ใส่โดเมนจริงของคุณ
- `DB_PASSWORD`: ตั้งรหัสผ่านฐานข้อมูลที่แข็งแรง
- `CLOUDFLARE_TUNNEL_TOKEN`: รับ Token จาก Cloudflare Zero Trust (Tunnels > Add a Tunnel)
- `EASYSLIP_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EMAIL_HOST_PASSWORD`

### 1.2 เชื่อมต่อ Cloudflare Tunnel กับ Nginx
ใน Cloudflare Zero Trust Dashboard ให้ตั้งค่า Public Hostname ดังนี้:
- **Subdomain / Domain**: `xn--72ch2atb1d4a4f1fudfc.com` และ `www.xn--72ch2atb1d4a4f1fudfc.com`
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

---

## 7. SEO / AEO Checklist หลัง Deploy

### 7.1 ตัวแปรสภาพแวดล้อมที่ต้องตั้งใน `.env.prod`
| ตัวแปร | ตัวอย่าง | ความสำคัญ |
|---|---|---|
| `SITE_URL` | `https://www.xn--72ch2atb1d4a4f1fudfc.com` | ต้นทางของ canonical / hreflang / sitemap / JSON-LD **ห้ามใส่ `/` ปิดท้าย** |
| `SITE_NAME` | `เซ้งร้านด่วน.com` | ชื่อองค์กรใน structured data |
| `GOOGLE_SITE_VERIFICATION` | `abc123...` | ค่า `content` จาก Search Console (ถ้าไม่ใส่ เมต้าแท็กจะไม่ถูก render) |
| `BING_SITE_VERIFICATION` | `abc123...` | ค่า `content` จาก Bing Webmaster Tools |

### 7.2 ตรวจสอบหลังเปิดเว็บ (ภายใน 15 นาทีแรก)
```bash
# 1) robots.txt ต้องมี Allow: /accounts/vip/ อยู่เหนือ Disallow: /accounts/
curl -s https://www.xn--72ch2atb1d4a4f1fudfc.com/robots.txt | head -40

# 2) sitemap.xml ต้องเป็น XML ที่ parse ผ่าน และมี <lastmod> แบบ ISO-8601
curl -s https://www.xn--72ch2atb1d4a4f1fudfc.com/sitemap.xml | head -30

# 3) หน้าส่วนตัวต้องมี X-Robots-Tag แบบ noindex
curl -sI https://www.xn--72ch2atb1d4a4f1fudfc.com/accounts/login/ | grep -i x-robots-tag

# 4) หน้า VIP ต้อง "ไม่มี" X-Robots-Tag (เป็นหน้า commercial ที่ต้อง index)
curl -sI https://www.xn--72ch2atb1d4a4f1fudfc.com/accounts/vip/ | grep -i x-robots-tag

# 5) canonical ของหน้า listing ต้องไม่มี query string
curl -s https://www.xn--72ch2atb1d4a4f1fudfc.com/listings/ | grep -o '<link rel="canonical"[^>]*>'
```

จากนั้นใน Google Search Console:
1. `Sitemaps` → ส่ง `https://www.xn--72ch2atb1d4a4f1fudfc.com/sitemap.xml` (ส่งซ้ำหลัง deploy ทุกครั้ง)
2. `URL Inspection` → ตรวจ `/accounts/vip/` ว่า "URL is on Google" ไม่ใช่ "Blocked by robots.txt"
3. `Rich results test` (https://search.google.com/test/rich-results) → ทดสอบหน้า listing 1 รายการ และ `/accounts/vip/`
4. ตรวจว่า `priceValidUntil` / `availability` เปลี่ยนตามสถานะประกาศจริง (ปิดการขาย → `SoldOut`)

### 7.3 แผนที่ Canonical / Redirect ที่ระบบบังคับใช้อยู่
| URL | พฤติกรรม | เหตุผล |
|---|---|---|
| `/listings/` | index + canonical ตัวเอง | หน้าหลักที่ต้องการจัดอันดับ |
| `/listings/?q=...&province=...` | `noindex, follow` + canonical → `/listings/` | กัน faceted navigation สร้างหน้าซ้ำนับพัน |
| `/listings/?page=2` | index + canonical ตัวเอง | รองรับ pagination ตามมาตรฐาน Google |
| `/packages/`, `/pricing/` | 301 → `/accounts/vip/` | รวม duplicate 3 URL เหลือ 1 canonical |
| `/accounts/vip/` | index (allowlist ใน middleware + robots.txt) | หน้า commercial หลัก |
| `/accounts/*`, `/properties/*`, `/contracts/*`, `/leads/*` | `X-Robots-Tag: noindex, nofollow` | หน้าส่วนตัว/หลังบ้าน |
| 4xx/5xx (HTML) | `X-Robots-Tag: noindex, nofollow` | ไม่ให้หน้า error เข้า index |

### 7.4 รูปภาพ OG (og-cover.png)
`static/images/og-cover.png` (1200×630) ถูกอ้างใน `base.html`, `sitemap.xml` และ JSON-LD ถ้าเปลี่ยนโลโก้/สีแบรนด์ให้รันใหม่:
```bash
../venv/bin/python scripts/make_og_cover.py
```

### 7.5 ชุดทดสอบ SEO
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev ../venv/bin/python -m pytest tests/test_seo_canonical_robots.py tests/test_seo_legacy_redirects.py -q
```

### 7.6 Core Web Vitals (LCP / CLS / caching)

| จุดที่ปรับ | ทำอะไร | ผลที่วัดได้ |
|---|---|---|
| Hero banner (`/` และ `/listings/`) | เปลี่ยน `<img>` เป็น `<picture>` + WebP `srcset` (800/1200/1600w) พร้อม JPEG fallback และ `fetchpriority="high"` เฉพาะหน้าแรก | LCP image ลดจาก **536 KB → ~93 KB** บนมือถือ |
| ภาพ hero | ใส่ `width`/`height` (1600×1200) + `object-cover` | กล่องภาพถูกจองพื้นที่ก่อนโหลดเสร็จ → CLS = 0 |
| Third-party origins | `preconnect` ไปที่ `cdn.tailwindcss.com` และ `unpkg.com` (เดิมมีแค่ Google Fonts) | ประหยัด DNS+TCP+TLS ~150–400 ms ต่อ origin |
| Lucide icons | ปักเวอร์ชัน `lucide@1.64.0` แทน `@latest` | ตัด 302 หนึ่งรอบ + cache ได้แบบ immutable |
| nginx `/static/` | `Cache-Control: public, max-age=31536000, immutable` (ยกเว้น `sw.js` และ `manifest.json` = `no-cache`) | ผู้ใช้กลับมาซ้ำไม่ต้อง revalidate |
| nginx `/media/propertyimage/` | 30 วัน | รูปประกาศโหลดซ้ำจาก cache |

เมื่อเปลี่ยนภาพ hero ต้นฉบับ ให้รันสคริปต์นี้ (สร้างไฟล์ WebP/JPEG ที่ template อ้างถึง):
```bash
../venv/bin/python scripts/optimize_hero_images.py
```
ตรวจผลจริงหลัง deploy:
```bash
# ไฟล์ WebP ต้องถูกเสิร์ฟด้วย content-type ที่ถูกต้อง + cache 1 ปี
curl -sI https://www.xn--72ch2atb1d4a4f1fudfc.com/static/images/hero_banner-800.webp | grep -iE 'content-type|cache-control'
# sw.js ต้องไม่ถูก cache ยาว
curl -sI https://www.xn--72ch2atb1d4a4f1fudfc.com/static/sw.js | grep -i cache-control
```
จากนั้นวัดด้วย PageSpeed Insights (mobile) เป้าหมาย: LCP < 2.5 s, CLS < 0.1, INP < 200 ms

> **ข้อจำกัดที่ยังเหลือ:** Tailwind ถูกโหลดผ่าน `cdn.tailwindcss.com` ซึ่ง compile CSS ที่ runtime (JS ~120 KB + FOUC) หากต้องการ LCP/INP ระดับสูงสุด ต้องย้ายไป build CSS ล่วงหน้า (Tailwind CLI → `static/css/app.css`) แล้วตัด `<script src="cdn.tailwindcss.com">` ออก ซึ่งเป็นการเปลี่ยน build pipeline จึงแยกเป็นงานถัดไป

### 7.7 AEO — ให้ AI อ้างอิงเว็บได้ (llms.txt / llms-full.txt)

| ไฟล์ / หน้า | เนื้อหาที่ต้องมี |
|---|---|
| `/llms.txt` | canonical origin, `## การอ้างอิงหน้านี้`, ตาราง `## ข้อเท็จจริงหลัก`, `## คำตอบสั้นสำหรับคำถามที่พบบ่อย`, `## ขอบเขตและข้อจำกัด` |
| `/llms-full.txt` | ตาราง `## 0. ข้อมูลอ้างอิงอย่างเป็นทางการ & วิธีอ้างอิง`, glossary, ขั้นตอน due diligence, ตารางราคา, FAQ, `## 9. ขอบเขต ข้อจำกัด…` |
| หน้าแรก `#key-facts` | บล็อก `<dl>` ข้อเท็จจริง (ชื่อ, ประเภท, พื้นที่, จำนวนประกาศ, ค่าบริการ, ช่องทางติดต่อ) + บรรทัด “วิธีอ้างอิง” |
| JSON-LD | `Organization` (+`alternateName`, `knowsAbout`, `slogan`, `#logo`), `WebSite`+`SearchAction`, `WebPage`+`speakable` (`#key-facts`, `#faq-section`), `FAQPage`, `BreadcrumbList`, `ItemList`, `Product`/`Offer` |

ตรวจว่าไฟล์ AI ถูกเสิร์ฟเป็น plain text และไม่มีโดเมนอื่นเจือปน:
```bash
curl -s https://www.xn--72ch2atb1d4a4f1fudfc.com/llms.txt | head -40
curl -s https://www.xn--72ch2atb1d4a4f1fudfc.com/llms.txt | grep -c 'sengranduan.com'   # ต้องได้ 0
```

> **สำคัญ:** โดเมน `sengranduan.com` เป็นของบุคคลอื่น — ห้ามให้ค่านี้ปรากฏใน canonical, sitemap, JSON-LD, robots.txt, llms*.txt หรืออีเมลบนเว็บเด็ดขาด เพราะจะทำให้ search engine และ AI อ้างอิงข้อมูลไปยังเว็บของเจ้าของโดเมนนั้นแทน


