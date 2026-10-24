from django import forms
from apps.properties.models import Property, PropertyImage
from apps.properties.utils import extract_google_maps_coordinates, get_default_coordinates_for_location
from apps.core.utils.files import validate_and_sanitize_image

class PropertyForm(forms.ModelForm):
    """
    WHY SECURE:
    - Explicit field whitelist.
    - Owner is not accepted from user POST data; injected securely in view.
    """
    floors = forms.IntegerField(required=False, initial=1, min_value=1, label="จำนวนชั้น")
    postal = forms.CharField(required=False, initial='10000', label="รหัสไปรษณีย์")
    area_sqm = forms.DecimalField(required=False, initial=0.0, label="พื้นที่ (ตร.ม.)")

    class Meta:
        model = Property
        fields = [
            'type', 'title', 'desc', 'address', 'province',
            'district', 'postal', 'google_maps_url', 'lat', 'lng', 'area_sqm', 'floors'
        ]

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if len(title) < 3:
            raise forms.ValidationError("ชื่อสถานที่หรือหัวข้อต้องมีความยาวอย่างน้อย 3 ตัวอักษร")
        return title

    def clean_floors(self):
        floors = self.cleaned_data.get('floors')
        if not floors:
            return 1
        return floors

    def clean_postal(self):
        postal = self.cleaned_data.get('postal', '').strip()
        if not postal:
            return '10000'
        return postal

    def clean_area_sqm(self):
        area = self.cleaned_data.get('area_sqm')
        if not area:
            if self.instance and self.instance.pk and self.instance.area_sqm:
                return self.instance.area_sqm
            return 0.0
        if area < 0:
            raise forms.ValidationError("พื้นที่ใช้สอยต้องมากกว่าหรือเท่ากับ 0 ตารางเมตร")
        return area

    def clean(self):
        cleaned_data = super().clean()
        maps_url = cleaned_data.get('google_maps_url')
        lat = cleaned_data.get('lat')
        lng = cleaned_data.get('lng')

        if maps_url and (not lat or not lng):
            ext_lat, ext_lng = extract_google_maps_coordinates(maps_url)
            if ext_lat and ext_lng:
                cleaned_data['lat'] = ext_lat
                cleaned_data['lng'] = ext_lng

        if not cleaned_data.get('lat') or not cleaned_data.get('lng'):
            fallback_lat, fallback_lng = get_default_coordinates_for_location(
                cleaned_data.get('province', ''),
                cleaned_data.get('district', '')
            )
            cleaned_data['lat'] = fallback_lat
            cleaned_data['lng'] = fallback_lng

        return cleaned_data

class PropertyImageForm(forms.ModelForm):
    """
    WHY SECURE:
    Runs validate_and_sanitize_image on every uploaded image:
    1. Size limit (<= 10MB)
    2. Extension whitelist (jpg, png, webp)
    3. Magic bytes inspection
    4. Pillow re-encoding to strip EXIF GPS coordinates
    """
    class Meta:
        model = PropertyImage
        fields = ['image', 'is_cover', 'order', 'is_360_panorama']

    def clean_image(self):
        uploaded_image = self.cleaned_data.get('image')
        if uploaded_image:
            return validate_and_sanitize_image(uploaded_image)
        return uploaded_image
