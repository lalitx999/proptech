from django import forms
from apps.listings.models import Listing, ListingApproval

class ListingForm(forms.ModelForm):
    """
    WHY SECURE:
    - Restricts user input to declared schema.
    - Validates business rules on financial numbers (cannot be negative).
    """
    security_deposit = forms.DecimalField(required=False, initial=0.00)
    lease_remaining_months = forms.IntegerField(required=False, initial=12)
    lease_transfer_fee = forms.DecimalField(required=False, initial=0.00)
    lease_transfer_fee_payer = forms.CharField(required=False, initial='free')

    class Meta:
        model = Listing
        fields = [
            'type', 'price', 'monthly_rent', 'security_deposit',
            'lease_remaining_months', 'lease_transfer_fee',
            'lease_transfer_fee_payer', 'avg_revenue_3m',
            'avg_profit_3m', 'includes_equipment', 'includes_staff'
        ]

    def clean_security_deposit(self):
        val = self.cleaned_data.get('security_deposit')
        return val if val is not None else 0.00

    def clean_lease_remaining_months(self):
        val = self.cleaned_data.get('lease_remaining_months')
        return val if val is not None else 12

    def clean_lease_transfer_fee(self):
        val = self.cleaned_data.get('lease_transfer_fee')
        return val if val is not None else 0.00

    def clean_lease_transfer_fee_payer(self):
        val = self.cleaned_data.get('lease_transfer_fee_payer', '').strip()
        return val if val else 'free'

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError("ราคาเซ้งต้องมากกว่า 0 บาท")
        return price

    def clean_monthly_rent(self):
        rent = self.cleaned_data.get('monthly_rent')
        if rent is not None and rent < 0:
            raise forms.ValidationError("ค่าเช่าต่อเดือนไม่สามารถติดลบได้")
        return rent

class ListingApprovalForm(forms.ModelForm):
    """Staff/Admin listing moderation form."""
    class Meta:
        model = ListingApproval
        fields = ['action', 'note']

    def clean_note(self):
        note = self.cleaned_data.get('note', '').strip()
        if not note:
            raise forms.ValidationError("กรุณาระบุบันทึกหรือเหตุผลประกอบการพิจารณา")
        return note
