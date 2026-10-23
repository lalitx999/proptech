import os
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Deal, DealStage, ContractDocument, DocumentType

ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx']
MAX_DOC_SIZE = 10 * 1024 * 1024  # 10 MB

class DealStageUpdateForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = ['stage', 'agreed_price', 'deposit_amount', 'notes']
        widgets = {
            'stage': forms.Select(attrs={'class': 'w-full rounded-md border-neutral-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500'}),
            'agreed_price': forms.NumberInput(attrs={'class': 'w-full rounded-md border-neutral-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500', 'placeholder': 'ราคาตกลงสุดท้าย (บาท)'}),
            'deposit_amount': forms.NumberInput(attrs={'class': 'w-full rounded-md border-neutral-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500', 'placeholder': 'ยอดเงินมัดจำ (บาท)'}),
            'notes': forms.Textarea(attrs={'class': 'w-full rounded-md border-neutral-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500', 'rows': 3, 'placeholder': 'บันทึกการเจรจาหรือความคืบหน้า'}),
        }

class ContractDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ContractDocument
        fields = ['type', 'file']
        widgets = {
            'type': forms.Select(attrs={'class': 'w-full rounded-md border-neutral-300 shadow-sm text-sm focus:border-brand-500 focus:ring-brand-500'}),
            'file': forms.FileInput(attrs={'class': 'w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100'}),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise ValidationError(_('กรุณาเลือกไฟล์เอกสาร'))

        if uploaded_file.size > MAX_DOC_SIZE:
            raise ValidationError(_('ขนาดไฟล์ต้องไม่เกิน 10 MB'))

        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                _('ไฟล์ประเภท %(ext)s ไม่ได้รับอนุญาต กรุณาอัปโหลดเฉพาะ %(allowed)s'),
                params={'ext': ext, 'allowed': ', '.join(ALLOWED_EXTENSIONS)}
            )

        # Basic magic header inspection for dangerous executable signatures
        head = uploaded_file.read(8)
        uploaded_file.seek(0)
        # Windows PE header 'MZ', Linux ELF '\x7fELF'
        if head.startswith(b'MZ') or head.startswith(b'\x7fELF'):
            raise ValidationError(_('ตรวจพบไฟล์ที่อาจเป็นอันตราย'))

        return uploaded_file
