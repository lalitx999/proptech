import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.core.utils.files import secure_upload_path

User = get_user_model()

class PropertyType(models.TextChoices):
    MASSAGE_SPA = 'massage_spa', _('นวด/สปา')
    BAR_PUB_KARAOKE = 'bar_pub_karaoke', _('ผับ/บาร์/คาราโอเกะ')
    BEAUTY_SALON_NAILS = 'beauty_salon_nails', _('ตัดผม/เสริมสวย/ทำเล็บ')
    RESTAURANT_SHABU = 'restaurant_shabu', _('หมูกระทะ/ชาบู/ร้านอาหาร')
    BUILDING_LAND_CONDO = 'building_land_condo', _('ตึก/บ้าน/คอนโด/ที่ดิน')
    CAFE_BEVERAGE = 'cafe_beverage', _('คาเฟ่/กาแฟ/ร้านน้ำปั่น')
    RENTAL_BOOTH_SPACE = 'rental_booth_space', _('ล็อค/พื้นที่ให้เช่า')
    OTHER = 'other', _('อื่นๆ')

    # Legacy types for backward compatibility
    COMMERCIAL_BUILDING = 'commercial_building', _('อาคารพาณิชย์ / ตึกแถว')
    RETAIL_SHOP = 'retail_shop', _('ร้านค้า / หน้าร้าน')
    MALL_SPACE = 'mall_space', _('พื้นที่ในห้าง / คอมมูนิตี้มอลล์')
    STANDALONE = 'standalone', _('อาคารเดี่ยว / สแตนด์อโลน')
    BOOTH_KIOSK = 'booth_kiosk', _('คีออสก์ / บูธ')

class Property(models.Model):
    """
    WHY SECURE:
    - Row-level isolation: Each property is strictly bound to an owner.
    - Uses UUID-based upload isolation for associated media.
    """
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='properties',
        db_index=True,
        help_text=_('เจ้าของทรัพย์สิน')
    )
    type = models.CharField(
        max_length=50,
        choices=PropertyType.choices,
        default=PropertyType.RETAIL_SHOP,
        db_index=True
    )
    title = models.CharField(max_length=255, help_text=_('ชื่อสถานที่หรือชื่อร้าน'))
    desc = models.TextField(help_text=_('รายละเอียดสถานที่และสภาพพื้นที่'))
    
    # Location Hierarchy
    address = models.CharField(max_length=255, help_text=_('ที่อยู่/ซอย/ถนน'))
    province = models.CharField(max_length=100, db_index=True, help_text=_('จังหวัด'))
    district = models.CharField(max_length=100, db_index=True, help_text=_('เขต/อำเภอ'))
    postal = models.CharField(max_length=10, help_text=_('รหัสไปรษณีย์'))
    
    # Google Maps URL & Coordinates for Interactive Map
    google_maps_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_('ลิงก์ Google Maps ของร้าน (เช่น https://maps.app.goo.gl/... หรือ https://goo.gl/maps/...)')
    )
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Physical Dimensions
    area_sqm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.00,
        help_text=_('พื้นที่ใช้สอย (ตารางเมตร)')
    )
    floors = models.PositiveIntegerField(default=1, help_text=_('จำนวนชั้น'))

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Property')
        verbose_name_plural = _('Properties')

    def __str__(self):
        return f"{self.title} ({self.province} - {self.district})"

    @property
    def cover_image(self):
        cover = self.images.filter(is_cover=True).first()
        return cover or self.images.first()

class PropertyImage(models.Model):
    """
    WHY SECURE:
    - Path Traversal defense: Upload path generated via secure_upload_path (UUID4).
    - Supports Three.js 360° Panorama mapping via is_360_panorama flag.
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to=secure_upload_path,
        help_text=_('รูปถ่ายร้านค้า/สถานที่ (ขนาดไม่เกิน 10MB)')
    )
    is_cover = models.BooleanField(default=False, help_text=_('รูปหน้าปกหลัก'))
    order = models.PositiveIntegerField(default=0, help_text=_('ลำดับการแสดงผล'))
    is_360_panorama = models.BooleanField(
        default=False,
        help_text=_('เป็นภาพ 360° Panorama สำหรับ Three.js Virtual Tour')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = _('Property Image')
        verbose_name_plural = _('Property Images')

    def __str__(self):
        return f"Image for {self.property.title} (Order: {self.order})"
