"""
Admin dashboard, tab 2 (shops): pagination.

WHY:
1. The table used to stop at the newest 50 shops with no way to reach the rest.
2. Row actions must return to the same page and filters, without becoming an open redirect.
3. Query count must not grow with the number of rows (N+1).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import UserRole
from apps.listings.models import Listing, ListingStatus
from apps.properties.models import Property, PropertyImage, PropertyType

User = get_user_model()


class AdminShopPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="pager_admin",
            email="pager_admin@test.com",
            password="DevPass1234!",
            role=UserRole.ADMIN,
            is_staff=True,
            is_superuser=True,
            email_verified=True,
        )
        cls.make_shops(65, start=0)

    @classmethod
    def make_shops(cls, count, start, status=ListingStatus.PUBLISHED, prop_type=PropertyType.CAFE_BEVERAGE):
        props = Property.objects.bulk_create([
            Property(owner=cls.admin, type=prop_type, title=f"ร้านทดสอบ {i:03d}", district="เมือง", province="ชลบุรี")
            for i in range(start, start + count)
        ])
        PropertyImage.objects.bulk_create([
            PropertyImage(property=p, image=f"propertyimage/{p.pk}.jpg", is_cover=True) for p in props
        ])
        return Listing.objects.bulk_create([
            Listing(property=p, price=Decimal("100000"), ref_code=f"T{start + i:03d}", status=status)
            for i, p in enumerate(props)
        ])

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("accounts:admin_dashboard")

    def get_shops(self, **params):
        return self.client.get(self.url, {"tab": "shops", **params})

    def test_every_shop_is_reachable_across_pages(self):
        seen = []
        for page in (1, 2, 3):
            seen += [shop.ref_code for shop in self.get_shops(shop_page=page).context["shops_page"]]
        self.assertEqual(len(seen), 65)
        self.assertEqual(len(set(seen)), 65)

    def test_header_and_summary_show_the_real_total(self):
        body = self.get_shops().content.decode()
        self.assertIn("รายการร้านค้าเซ้งทั้งหมด (65 รายการ)", body)
        self.assertRegex(body, r"1–30</strong>\s*จาก <strong[^>]*>65</strong>")

    def test_page_links_keep_filters(self):
        response = self.get_shops(shop_q="ร้านทดสอบ", shop_status=ListingStatus.PUBLISHED)
        self.assertEqual(response.context["shops_page"].paginator.count, 65)
        query = response.context["shop_filter_query"]
        self.assertIn("shop_status=published", query)
        self.assertIn("tab=shops", query)
        self.assertNotIn("shop_page", query)
        self.assertContains(response, "shop_page=2")
        self.assertContains(response, "shop_status=published&amp;shop_page=2")

    def test_filter_narrows_the_total(self):
        response = self.get_shops(shop_q="T00")
        self.assertEqual(response.context["shops_page"].paginator.count, 10)
        self.assertNotContains(response, "shop_page=2")

    def test_bad_page_values_do_not_crash(self):
        self.assertEqual(self.get_shops(shop_page="abc").context["shops_page"].number, 1)
        self.assertEqual(self.get_shops(shop_page="999").context["shops_page"].number, 3)
        self.assertEqual(self.get_shops(shop_page="-1").context["shops_page"].number, 3)

    def shop_action(self, **data):
        listing = Listing.objects.get(ref_code="T000")
        return self.client.post(
            reverse("accounts:admin_shop_action", args=[listing.pk]),
            {"action": "toggle_verified", **data},
        )

    def test_action_returns_to_same_page_and_filters(self):
        back = "/admin-dashboard/?tab=shops&shop_q=T0&shop_page=2"
        self.assertRedirects(self.shop_action(next=back), back, fetch_redirect_response=False)

    def test_action_rejects_external_next(self):
        for evil in ("https://evil.example/phish", "//evil.example/phish", "javascript:alert(1)"):
            with self.subTest(next=evil):
                response = self.shop_action(next=evil)
                self.assertRedirects(response, "/admin-dashboard/?tab=shops", fetch_redirect_response=False)

    def test_table_forms_carry_the_current_page(self):
        response = self.get_shops(shop_page=2)
        self.assertContains(response, 'name="next" value="/accounts/dashboard/?tab=shops&amp;shop_page=2"')

    def test_overview_lists_pending_shops_older_than_the_table_page(self):
        pending = self.make_shops(1, start=900, status=ListingStatus.PENDING)[0]
        Listing.objects.filter(pk=pending.pk).update(created_at="2020-01-01T00:00:00Z")

        response = self.client.get(self.url, {"tab": "overview"})

        self.assertEqual([s.pk for s in response.context["pending_shops_list"]], [pending.pk])
        self.assertContains(response, "ร้านทดสอบ 900")

    def test_overview_shows_empty_state_when_nothing_is_pending(self):
        self.assertContains(self.client.get(self.url, {"tab": "overview"}), "ไม่มีร้านค้ารออนุมัติในขณะนี้")

    def test_query_count_does_not_grow_with_rows(self):
        with CaptureQueriesContext(connection) as few:
            self.assertEqual(len(self.get_shops(shop_q="T000").context["shops_page"]), 1)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.get_shops().context["shops_page"]), 30)
        self.assertEqual(len(many), len(few))
