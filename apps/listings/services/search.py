from decimal import Decimal, InvalidOperation
from django.db.models import Q
from apps.listings.models import Listing, ListingStatus, ListingType
from apps.properties.models import PropertyType

class ListingSearchService:
    """
    WHY SECURE:
    1. SQLi Defense: Uses parameterized ORM filters with Q objects; zero raw SQL string interpolation.
    2. Input Sanitization: Truncates search query to 100 chars (prevents memory attacks & ReDoS).
    3. Whitelisting: Strict validation against enum choices for types and sort parameters.
    4. N+1 Query Optimization: Employs select_related and prefetch_related across all relations.
    5. Access Isolation: Strictly isolates status='published' so draft/pending listings are never leaked.
    """
    SORT_MAP = {
        'latest': '-published_at',
        'price_asc': 'price',
        'price_desc': '-price',
        'rent_asc': 'monthly_rent',
    }

    @classmethod
    def clean_decimal(cls, val):
        if val is None or val == '':
            return None
        try:
            d = Decimal(str(val))
            return d if d >= 0 else None
        except (InvalidOperation, ValueError, TypeError):
            return None

    @classmethod
    def search(cls, params):
        # ⚠️ Public discovery must strictly filter for published status only
        queryset = Listing.objects.filter(status=ListingStatus.PUBLISHED).select_related(
            'property', 'property__owner', 'agent'
        ).prefetch_related('property__images')

        # 1. Text Query (Truncated to 100 characters)
        q_raw = params.get('q', '').strip()[:100]
        if q_raw:
            queryset = queryset.filter(
                Q(ref_code__icontains=q_raw) |
                Q(property__title__icontains=q_raw) |
                Q(property__desc__icontains=q_raw) |
                Q(property__province__icontains=q_raw) |
                Q(property__district__icontains=q_raw)
            )

        # 2. Listing Type Whitelist Check
        listing_type = params.get('type')
        if listing_type in ListingType.values:
            queryset = queryset.filter(type=listing_type)

        # 3. Property Type / Category Filter
        cat_or_type = params.get('category') or params.get('property_type')
        if cat_or_type:
            if cat_or_type in PropertyType.values:
                queryset = queryset.filter(property__type=cat_or_type)
            elif cat_or_type in ('massage_spa', 'spa'):
                queryset = queryset.filter(Q(property__type='massage_spa') | Q(property__title__icontains='นวด') | Q(property__title__icontains='สปา'))
            elif cat_or_type in ('bar_pub_karaoke', 'bar', 'pub', 'bar_pub'):
                queryset = queryset.filter(Q(property__type='bar_pub_karaoke') | Q(property__title__icontains='บาร์') | Q(property__title__icontains='ผับ') | Q(property__title__icontains='คาราโอเกะ'))
            elif cat_or_type in ('beauty_salon_nails', 'salon', 'nail'):
                queryset = queryset.filter(Q(property__type='beauty_salon_nails') | Q(property__title__icontains='เสริมสวย') | Q(property__title__icontains='ทำเล็บ') | Q(property__title__icontains='ตัดผม'))
            elif cat_or_type in ('restaurant_shabu', 'restaurant', 'shabu', 'mookata'):
                queryset = queryset.filter(Q(property__type='restaurant_shabu') | Q(property__title__icontains='อาหาร') | Q(property__title__icontains='หมูกระทะ') | Q(property__title__icontains='ชาบู') | Q(property__title__icontains='ซีฟู้ด'))
            elif cat_or_type in ('building_land_condo', 'condo', 'land', 'building'):
                queryset = queryset.filter(Q(property__type='building_land_condo') | Q(property__title__icontains='ตึก') | Q(property__title__icontains='บ้าน') | Q(property__title__icontains='คอนโด') | Q(property__title__icontains='ที่ดิน'))
            elif cat_or_type in ('cafe_beverage', 'cafe', 'coffee', 'beverage'):
                queryset = queryset.filter(Q(property__type='cafe_beverage') | Q(property__title__icontains='คาเฟ่') | Q(property__title__icontains='กาแฟ') | Q(property__title__icontains='ชานม') | Q(property__title__icontains='น้ำปั่น'))
            elif cat_or_type in ('rental_booth_space', 'booth', 'rental'):
                queryset = queryset.filter(Q(property__type='rental_booth_space') | Q(property__title__icontains='ล็อค') | Q(property__title__icontains='บูธ') | Q(property__title__icontains='พื้นที่ให้เช่า'))
            elif cat_or_type == 'other':
                queryset = queryset.filter(property__type='other')

        # 4. Location Filter (Province / District)
        province = params.get('province', '').strip()[:50]
        if province:
            queryset = queryset.filter(property__province__icontains=province)

        district = params.get('district', '').strip()[:50]
        if district:
            queryset = queryset.filter(property__district__icontains=district)

        # 5. Price Range Filters (Takeover Price)
        price_min = cls.clean_decimal(params.get('price_min'))
        if price_min is not None:
            queryset = queryset.filter(price__gte=price_min)

        price_max = cls.clean_decimal(params.get('price_max'))
        if price_max is not None:
            queryset = queryset.filter(price__lte=price_max)

        # 6. Monthly Rent Range Filters
        rent_min = cls.clean_decimal(params.get('rent_min'))
        if rent_min is not None:
            queryset = queryset.filter(monthly_rent__gte=rent_min)

        rent_max = cls.clean_decimal(params.get('rent_max'))
        if rent_max is not None:
            queryset = queryset.filter(monthly_rent__lte=rent_max)

        # 7. Sorting: VIP listings get search priority boost, then specified order
        sort_key = params.get('sort', 'latest')
        order_field = cls.SORT_MAP.get(sort_key, '-published_at')
        queryset = queryset.order_by('-property__owner__is_vip', order_field)

        return queryset
