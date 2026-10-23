import os
import json
import urllib.request
import urllib.parse
from django.core.management.base import BaseCommand
from django.conf import settings
from decouple import config

class Command(BaseCommand):
    help = 'Fetches Telegram updates from bot to detect room/chat ID and sends a test message.'

    def handle(self, *args, **options):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or config('TELEGRAM_BOT_TOKEN', default='')
        if not bot_token:
            self.stdout.write(self.style.ERROR("❌ TELEGRAM_BOT_TOKEN is not configured!"))
            return

        self.stdout.write(self.style.NOTICE(f"🤖 Checking Telegram updates for bot token: {bot_token[:15]}..."))
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SengranBot/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            if not data.get('ok'):
                self.stdout.write(self.style.ERROR(f"❌ Telegram API Error: {data}"))
                return

            results = data.get('result', [])
            if not results:
                self.stdout.write(self.style.WARNING("⚠️ ยังไม่พบข้อความในคิว (result is empty)"))
                self.stdout.write("👉 วิธีหาเลขห้อง:")
                self.stdout.write("1. ดึงบอท @proptech2026_th_bot เข้ากลุ่ม Telegram ของคุณ")
                self.stdout.write("2. พิมพ์ข้อความอะไรก็ได้ในกลุ่ม 1 ข้อความ (เช่น 'test' หรือ '/start')")
                self.stdout.write("3. รันคำสั่งนี้อีกครั้ง เพื่อดึง Chat ID และยิงข้อความทดสอบเข้ากลุ่มทันที!")
                return

            # Find latest message with chat info
            latest_chat = None
            for item in reversed(results):
                msg = item.get('message') or item.get('my_chat_member') or item.get('channel_post')
                if msg and 'chat' in msg:
                    latest_chat = msg['chat']
                    break

            if not latest_chat:
                self.stdout.write(self.style.WARNING("⚠️ พบ update แต่ไม่มี chat object"))
                return

            chat_id = str(latest_chat.get('id'))
            chat_type = latest_chat.get('type')
            chat_title = latest_chat.get('title') or latest_chat.get('username') or latest_chat.get('first_name') or 'Direct'

            self.stdout.write(self.style.SUCCESS(f"🎯 พบคุยล่าสุด!"))
            self.stdout.write(f"   - Chat ID: {chat_id}")
            self.stdout.write(f"   - Type: {chat_type}")
            self.stdout.write(f"   - Title: {chat_title}")

            # Update .env file
            env_path = os.path.join(settings.BASE_DIR, '.env')
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                new_lines = []
                replaced = False
                for line in lines:
                    if line.startswith('TELEGRAM_CHAT_ID='):
                        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                        replaced = True
                    else:
                        new_lines.append(line)
                if not replaced:
                    new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                self.stdout.write(self.style.SUCCESS(f"✅ บันทึก TELEGRAM_CHAT_ID={chat_id} ลงใน .env เรียบร้อยแล้ว!"))

            # Test shoot message into group
            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            test_text = (
                f"🚀 *ทดสอบยิงข้อความบอท เซ้งร้าน.com*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"✅ เชื่อมต่อระบบแจ้งเตือนสำเร็จ!\n"
                f"📌 Chat ID: `{chat_id}`\n"
                f"🏷️ ห้อง: *{chat_title}*\n"
                f"⏰ เวลา: {urllib.request.urlopen('http://worldtimeapi.org/api/timezone/Asia/Bangkok').status if False else 'เรียลไทม์'}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"ระบบพร้อมส่งการแจ้งเตือนสลิป VIP, ลีดลูกค้าใหม่ และข้อความติดต่อแล้วครับ"
            )
            payload = json.dumps({
                'chat_id': chat_id,
                'text': test_text,
                'parse_mode': 'Markdown'
            }).encode('utf-8')
            send_req = urllib.request.Request(send_url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(send_req, timeout=10) as s_resp:
                s_data = json.loads(s_resp.read().decode('utf-8'))
                if s_data.get('ok'):
                    self.stdout.write(self.style.SUCCESS("🎉 ยิงข้อความทดสอบเข้ากลุ่ม Telegram สำเร็จแล้ว!"))
                else:
                    self.stdout.write(self.style.ERROR(f"❌ ส่งข้อความไม่สำเร็จ: {s_data}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Exception: {e}"))
