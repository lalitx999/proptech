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

    class Meta:
        model = Property
        fields = [
            'type', 'title', 'desc', 'address', 'province',
            'district', 'postal', 'google_maps_url', 'lat', 'lng', 'floors'
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

    def clean_desc(self):
        desc = self.cleaned_data.get('desc', '').strip()
        if desc:
            allowed_tags = ['p', 'br', 'span', 'b', 'strong', 'i', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h3', 'h4', 'font', 'div']
            allowed_attrs = {
                'a': ['href', 'title', 'target', 'rel', 'class'],
                'span': ['style', 'class'],
                'font': ['color'],
                '*': ['style', 'class']
            }
            try:
                import bleach
                try:
                    from bleach.css_sanitizer import CSSSanitizer
                    css_sanitizer = CSSSanitizer(allowed_css_properties=['color', 'background-color', 'font-weight', 'text-decoration'])
                    desc = bleach.clean(desc, tags=allowed_tags, attributes=allowed_attrs, css_sanitizer=css_sanitizer, strip=True)
                except Exception:
                    desc = bleach.clean(desc, tags=allowed_tags, attributes=allowed_attrs, strip=True)
            except Exception:
                pass
        return desc

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
