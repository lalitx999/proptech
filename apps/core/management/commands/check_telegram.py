import requests
from django.core.management.base import BaseCommand

from apps.core.services.telegram import TelegramAlertService


class Command(BaseCommand):
    """
    ตรวจว่าแจ้งเตือน Telegram ใช้งานได้ไหม (ไม่แก้ .env และไม่ยิงข้อความ เว้นแต่ใส่ --send-test)

        docker compose exec web python manage.py check_telegram
        docker compose exec web python manage.py check_telegram --send-test
    """
    help = 'Checks the Telegram bot token, chat ID and bot permissions used for alerts.'

    def add_arguments(self, parser):
        parser.add_argument('--send-test', action='store_true',
                            help='ส่งข้อความทดสอบ 1 ข้อความผ่าน TelegramAlertService.send_alert')

    def handle(self, *args, **options):
        token, chat_id = TelegramAlertService.get_credentials()
        if not token:
            self.stdout.write(self.style.ERROR('❌ ไม่มี TELEGRAM_BOT_TOKEN ใน environment ของเซิร์ฟเวอร์'))
        if not chat_id:
            self.stdout.write(self.style.ERROR('❌ ไม่มี TELEGRAM_CHAT_ID ใน environment ของเซิร์ฟเวอร์'))
        if not token or not chat_id:
            self.stdout.write('👉 ใส่ค่าใน .env แล้วรัน docker compose up -d web (restart อย่างเดียวไม่อ่าน .env ใหม่)')
            return

        base = f'https://api.telegram.org/bot{token}'
        try:
            me = requests.get(f'{base}/getMe', timeout=10).json()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f'❌ เซิร์ฟเวอร์ต่อ api.telegram.org ไม่ได้: {e}'))
            return
        if not me.get('ok'):
            self.stdout.write(self.style.ERROR(f"❌ Bot token ใช้ไม่ได้: {me.get('description')}"))
            return
        bot = me['result']
        self.stdout.write(self.style.SUCCESS(f"✅ Bot: @{bot['username']}"))

        chat = requests.get(f'{base}/getChat', params={'chat_id': chat_id}, timeout=10).json()
        if not chat.get('ok'):
            self.stdout.write(self.style.ERROR(f"❌ Chat ID {chat_id} ใช้ไม่ได้: {chat.get('description')}"))
            migrated = (chat.get('parameters') or {}).get('migrate_to_chat_id')
            if migrated:
                self.stdout.write(f'👉 กลุ่มถูกอัปเกรดเป็น supergroup แล้ว เปลี่ยน TELEGRAM_CHAT_ID={migrated}')
            return
        info = chat['result']
        self.stdout.write(self.style.SUCCESS(f"✅ Chat: {info.get('title') or info.get('username')} ({info.get('type')})"))

        member = requests.get(f'{base}/getChatMember',
                              params={'chat_id': chat_id, 'user_id': bot['id']}, timeout=10).json()
        status = (member.get('result') or {}).get('status')
        if status in ('left', 'kicked', None):
            self.stdout.write(self.style.ERROR(f'❌ บอทไม่ได้อยู่ในกลุ่มนี้แล้ว (status={status})'))
            return
        self.stdout.write(self.style.SUCCESS(f'✅ บอทอยู่ในกลุ่ม (status={status})'))

        if options['send_test']:
            ok = TelegramAlertService.send_alert('ทดสอบระบบแจ้งเตือนจากคำสั่ง check_telegram',
                                                 event_title='🧪 ทดสอบแจ้งเตือน')
            if ok:
                self.stdout.write(self.style.SUCCESS('✅ ส่งข้อความทดสอบสำเร็จ'))
            else:
                self.stdout.write(self.style.ERROR('❌ ส่งข้อความทดสอบไม่สำเร็จ ดู log ของ web container'))
