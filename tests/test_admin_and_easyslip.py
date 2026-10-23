import io
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.accounts.models import UserRole, VIPPaymentTransaction
from apps.accounts.services.easyslip import EasySlipService
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingStatus, ListingType
from apps.leads.models import Lead, LeadStatus, LeadUrgency
from apps.contracts.models import Deal, DealStage
from apps.core.models import ContactMessage

User = get_user_model()

def create_dummy_image(name="test_slip.jpg"):
    file_obj = io.BytesIO()
    img = Image.new("RGB", (120, 120), color="green")
    img.save(file_obj, format="JPEG")
    file_obj.seek(0)
    return SimpleUploadedFile(name, file_obj.read(), content_type="image/jpeg")


@override_settings(EASYSLIP_API_KEY="test_api_key_12345")
class EasySlipServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner_easyslip",
            email="owner_easyslip@test.com",
            password="DevPass1234!",
            role=UserRole.OWNER,
            email_verified=True,
        )

    @patch("apps.accounts.services.easyslip.requests.post")
    def test_verify_slip_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "amountInSlip": 1000.0,
                "isAmountMatched": True,
                "isDuplicate": False,
                "rawSlip": {
                    "transRef": "KBANK20261019001",
                    "receiver": {
                        "displayName": "ดวงฤทัย ช้างน้อย",
                        "account": {
                            "name": "054-1-27630-0"
                        }
                    }
                }
            }
        }
        mock_post.return_value = mock_resp

        slip_file = create_dummy_image("slip_ok.jpg")
        result = EasySlipService.verify_slip(slip_file, expected_amount=Decimal("1000.00"))

        self.assertTrue(result["success"])
        self.assertTrue(result["is_verified"])
        self.assertEqual(result["trans_ref"], "KBANK20261019001")
        self.assertFalse(result["needs_manual_review"])

    @patch("apps.accounts.services.easyslip.requests.post")
    def test_verify_slip_mismatched_receiver_requires_manual_review(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "amountInSlip": 1000.0,
                "isAmountMatched": True,
                "isDuplicate": False,
                "rawSlip": {
                    "transRef": "KBANK_OTHER_999",
                    "receiver": {
                        "displayName": "นายสมชาย นามสมมุติ",
                        "account": {
                            "name": "999-9-99999-9"
                        }
                    }
                }
            }
        }
        mock_post.return_value = mock_resp

        slip_file = create_dummy_image("slip_wrong_receiver.jpg")
        result = EasySlipService.verify_slip(slip_file, expected_amount=Decimal("1000.00"))

        self.assertTrue(result["success"])
        self.assertFalse(result["is_verified"])
        self.assertFalse(result["is_receiver_matched"])
        self.assertTrue(result["needs_manual_review"])

    @patch("apps.accounts.services.easyslip.requests.post")
    def test_verify_slip_network_exception_fails_gracefully(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout to api.easyslip.com")

        slip_file = create_dummy_image("slip_fail.jpg")
        result = EasySlipService.verify_slip(slip_file)

        self.assertFalse(result["success"])
        self.assertTrue(result["needs_manual_review"])


class ContactMessageTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("apps.core.services.telegram.TelegramAlertService.send_contact_alert")
    def test_contact_form_submission(self, mock_telegram):
        url = reverse("core:contact")
        response = self.client.post(url, {
            "name": "คุณทดสอบ ติดต่อ",
            "phone": "0891112233",
            "email": "testcontact@gmail.com",
            "subject": "สอบถามราคาเซ้ง",
            "message": "สนใจให้ประเมินร้านอาหารแถวทองหล่อครับ",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        msg = ContactMessage.objects.filter(phone="0891112233").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.name, "คุณทดสอบ ติดต่อ")
        self.assertFalse(msg.is_resolved)
        mock_telegram.assert_called_once()


class AdminCommandCenterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin_test",
            email="admin_test@sengran.com",
            password="DevPass1234!",
            role=UserRole.ADMIN,
            is_staff=True,
            is_superuser=True,
            email_verified=True,
        )
        self.regular_user = User.objects.create_user(
            username="user_regular",
            email="reg@test.com",
            password="DevPass1234!",
            role=UserRole.CUSTOMER,
            email_verified=True,
        )
        self.agent = User.objects.create_user(
            username="agent_somchai",
            email="agent@test.com",
            password="DevPass1234!",
            role=UserRole.AGENT,
            email_verified=True,
        )
        self.property = Property.objects.create(
            owner=self.admin,
            type=PropertyType.CAFE_BEVERAGE,
            title="ร้านทดสอบใจกลางเมือง",
            desc="รายละเอียดร้านค้าทดสอบ",
            address="123 สุขุมวิท",
            province="กรุงเทพมหานคร",
            district="วัฒนา",
            postal="10110",
            area_sqm=Decimal("50.00"),
        )
        self.listing = Listing.objects.create(
            property=self.property,
            agent=self.agent,
            price=Decimal("450000.00"),
            monthly_rent=Decimal("25000.00"),
            status=ListingStatus.PENDING,
            type=ListingType.TAKEOVER,
        )
        self.lead = Lead.objects.create(
            listing=self.listing,
            full_name="ผู้สนใจทดสอบ",
            phone="0819998877",
            status=LeadStatus.NEW,
            urgency=LeadUrgency.IMMEDIATE,
            assigned_agent=self.agent,
        )
        self.deal = Deal.objects.create(
            listing=self.listing,
            lead=self.lead,
            agent=self.agent,
            stage=DealStage.NEGOTIATION,
            agreed_price=Decimal("450000.00"),
        )
        self.contact_msg = ContactMessage.objects.create(
            name="ผู้ติดต่อ",
            phone="0855556677",
            subject="สอบถามข้อมูล",
            message="ขอรายละเอียดเพิ่ม",
        )

    def test_admin_dashboard_access_denied_for_regular_user(self):
        self.client.force_login(self.regular_user)
        url = reverse("accounts:admin_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_rendered_for_admin(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command Center")
        self.assertContains(response, "ร้านทดสอบใจกลางเมือง")

        # Check CRM tab renders leads
        crm_response = self.client.get(url + "?tab=crm")
        self.assertEqual(crm_response.status_code, 200)
        self.assertContains(crm_response, "ผู้สนใจทดสอบ")

    def test_admin_approve_shop(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_shop_action", args=[self.listing.id])
        response = self.client.post(url, {"action": "approve"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.PUBLISHED)

    def test_admin_update_lead_status(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_lead_action", args=[self.lead.id])
        response = self.client.post(url, {
            "status": LeadStatus.SITE_VISIT,
            "agent_id": self.agent.id,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, LeadStatus.SITE_VISIT)

    def test_admin_update_deal_stage(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_deal_action", args=[self.deal.id])
        response = self.client.post(url, {
            "stage": DealStage.CLOSED_WON,
            "agreed_price": "430000.00",
            "deposit_amount": "50000.00",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, DealStage.CLOSED_WON)
        self.assertEqual(self.deal.agreed_price, Decimal("430000.00"))
        self.assertGreater(self.deal.gross_commission, Decimal("0.00"))

    def test_admin_resolve_contact_message(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_resolve_message", args=[self.contact_msg.id])
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.contact_msg.refresh_from_db()
        self.assertTrue(self.contact_msg.is_resolved)

    def test_admin_fast_create_shop(self):
        self.client.force_login(self.admin)
        url = reverse("accounts:admin_fast_create_shop")
        dummy_img = create_dummy_image("shop1.jpg")
        response = self.client.post(url, {
            "title": "ร้าน Fast Post ผ่านแอดมิน",
            "type": PropertyType.RESTAURANT_SHABU,
            "province": "กรุงเทพมหานคร",
            "district": "พญาไท",
            "address": "ซอยอารีย์ 2",
            "price": "620000.00",
            "monthly_rent": "32000.00",
            "sqm": "80.00",
            "auto_publish": "on",
            "images": [dummy_img],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        created_prop = Property.objects.filter(title="ร้าน Fast Post ผ่านแอดมิน").first()
        self.assertIsNotNone(created_prop)
        listing = created_prop.listings.first()
        self.assertIsNotNone(listing)
        self.assertEqual(listing.status, ListingStatus.PUBLISHED)
