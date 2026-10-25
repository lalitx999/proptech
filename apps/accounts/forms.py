import re
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from apps.accounts.models import UserRole

User = get_user_model()

class UserRegistrationForm(forms.ModelForm):
    """
    WHY SECURE:
    1. Form-based validation with strict clean methods.
    2. Honeypot field 'website' catches spam bots silently.
    3. Self-registration is restricted to CUSTOMER and OWNER roles only.
       (Prevents privilege escalation to ADMIN/STAFF/AGENT).
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'รหัสผ่านอย่างน้อย 10 ตัวอักษร', 'autocomplete': 'new-password'}),
        label='รหัสผ่าน',
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'ยืนยันรหัสผ่านอีกครั้ง', 'autocomplete': 'new-password'}),
        label='ยืนยันรหัสผ่าน',
    )
    # Honeypot: must remain empty for real humans
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'role', 'avatar']
        widgets = {
            'role': forms.Select(choices=[
                (UserRole.OWNER, 'เจ้าของร้าน/ผู้ต้องการเซ้ง (Shop Owner)'),
                (UserRole.CUSTOMER, 'ผู้ค้นหา/ผู้ซื้อ (Customer)'),
            ])
        }

    def clean_website(self):
        # ⚠️ Honeypot check: Bots fill hidden fields
        if self.cleaned_data.get('website'):
            raise ValidationError("Spam bot detected.")
        return ''

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            from apps.core.utils.files import validate_and_sanitize_image
            try:
                return validate_and_sanitize_image(avatar)
            except Exception as e:
                raise ValidationError(str(e))
        return avatar

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError("กรุณากรอกอีเมล")
        if User.objects.filter(email=email).exists():
            raise ValidationError("อีเมลนี้ถูกลงทะเบียนใช้งานแล้ว")
        return email

    def clean_role(self):
        role = self.cleaned_data.get('role')
        # ⚠️ Privilege escalation defense: Prevent self-assigning ADMIN or STAFF
        if role not in [UserRole.CUSTOMER, UserRole.OWNER]:
            raise ValidationError("ไม่อนุญาตให้กำหนดบทบาทนี้ผ่านการลงทะเบียนสาธารณะ")
        return role

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm:
            if password != password_confirm:
                self.add_error('password_confirm', "รหัสผ่านทั้งสองช่องไม่ตรงกัน")
            else:
                # Runs all validators defined in settings.AUTH_PASSWORD_VALIDATORS
                validate_password(password)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email'] # Username mirrors clean email
        user.set_password(self.cleaned_data['password']) # Argon2 hash
        user.is_active = False # Inactive until email is verified
        user.email_verified = False
        if commit:
            user.save()
        return user

class UserLoginForm(forms.Form):
    """Clean login form with email/username and password."""
    username = forms.CharField(
        label='อีเมล หรือ ชื่อผู้ใช้',
        widget=forms.TextInput(attrs={'placeholder': 'อีเมลของคุณ', 'autocomplete': 'username'}),
    )
    password = forms.CharField(
        label='รหัสผ่าน',
        widget=forms.PasswordInput(attrs={'placeholder': 'รหัสผ่าน', 'autocomplete': 'current-password'}),
    )

class TOTPVerificationForm(forms.Form):
    """Validation for 6-digit TOTP token."""
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label='รหัสความปลอดภัย 6 หลัก (2FA TOTP)',
        widget=forms.TextInput(attrs={
            'placeholder': '123456',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True,
        })
    )

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if not re.match(r'^\d{6}$', code):
            raise ValidationError("รหัสความปลอดภัยต้องเป็นตัวเลข 6 หลักเท่านั้น")
        return code

class PasswordResetRequestForm(forms.Form):
    """Password reset request form."""
    email = forms.EmailField(
        label='อีเมลที่ลงทะเบียน',
        widget=forms.EmailInput(attrs={'placeholder': 'name@example.com', 'autocomplete': 'email'}),
    )
