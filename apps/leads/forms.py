import re
from django import forms
from django.core.exceptions import ValidationError
from apps.leads.models import Lead, LeadUrgency

class LeadInquiryForm(forms.ModelForm):
    """
    WHY SECURE:
    - Honeypot field 'website' catches spam bots.
    - Phone number regex verification.
    """
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    urgency = forms.ChoiceField(
        choices=LeadUrgency.choices,
        required=False,
        initial=LeadUrgency.IMMEDIATE
    )

    class Meta:
        model = Lead
        fields = ['full_name', 'phone', 'line_id', 'email', 'budget_max', 'urgency', 'notes']

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise ValidationError("Spam bot detected.")
        return ''

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip().replace('-', '').replace(' ', '')
        if not re.match(r'^0\d{8,9}$', phone):
            raise ValidationError("กรุณาระบุหมายเลขโทรศัพท์ที่ถูกต้อง (เช่น 0812345678)")
        return phone

    def clean_urgency(self):
        return self.cleaned_data.get('urgency') or LeadUrgency.IMMEDIATE
