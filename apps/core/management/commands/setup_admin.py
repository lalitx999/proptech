from django.core.management.base import BaseCommand
from apps.accounts.models import User, UserRole


class Command(BaseCommand):
    help = 'Create or update superuser administrator account'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, default='ple1930@gmail.com', help='Admin email address')
        parser.add_argument('--password', type=str, default='661201123_SD', help='Admin password')
        parser.add_argument('--username', type=str, default=None, help='Admin username (defaults to email)')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        password = options['password']
        username = (options['username'] or email).strip()

        # Check existing user by email or username
        user = User.objects.filter(email=email).first() or User.objects.filter(username=username).first()
        created = False
        if not user:
            user = User(username=username, email=email)
            created = True
        else:
            user.email = email
            user.username = username

        user.first_name = 'ผู้ดูแลระบบ'
        user.last_name = 'Admin'
        user.set_password(password)
        user.role = UserRole.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.email_verified = True
        user.is_active = True
        user.save()

        action = "สร้างบัญชีใหม่" if created else "อัปเดตข้อมูลบัญชีเดิม"
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {action} สำเร็จ!\n"
                f"   Email: {user.email}\n"
                f"   Username: {user.username}\n"
                f"   Role: {user.role} (ADMIN)\n"
                f"   is_staff: {user.is_staff}, is_superuser: {user.is_superuser}\n"
                f"   email_verified: {user.email_verified}\n"
            )
        )
