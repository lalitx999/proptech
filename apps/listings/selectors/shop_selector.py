from django.db.models import Q

from apps.listings.models import Listing, ListingStatus

# Columns read by the admin shop rows. Property.desc can hold large rich text, so it
# is deferred along with every other column these rows never display.
ADMIN_SHOP_ROW_FIELDS = (
    'ref_code', 'status', 'price', 'monthly_rent', 'is_admin_verified',
    'contact_phone', 'contact_line_id', 'created_at',
    'property__title', 'property__type', 'property__district', 'property__province',
    'property__owner__username', 'property__owner__phone', 'property__owner__line_id',
    'property__owner__membership_tier', 'property__owner__is_vip', 'property__owner__vip_expires_at',
)


def _admin_shop_rows():
    return (
        Listing.objects
        .select_related('property', 'property__owner')
        .prefetch_related('property__images')
        .only(*ADMIN_SHOP_ROW_FIELDS)
        # pk breaks created_at ties, so a row cannot repeat or vanish between pages
        .order_by('-created_at', '-pk')
    )


def get_admin_shops(query='', status='', category=''):
    """Shops for the admin dashboard table, newest first, narrowed by its filter form."""
    shops = _admin_shop_rows()
    if query:
        shops = shops.filter(
            Q(property__title__icontains=query) |
            Q(ref_code__icontains=query) |
            Q(property__district__icontains=query) |
            Q(property__province__icontains=query)
        )
    if status:
        shops = shops.filter(status=status)
    if category:
        shops = shops.filter(property__type=category)
    return shops


def get_pending_admin_shops(limit=10):
    """Newest shops awaiting approval, regardless of the table's page or filters."""
    return _admin_shop_rows().filter(status=ListingStatus.PENDING)[:limit]
