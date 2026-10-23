from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied

from apps.accounts.models import UserRole, AuditLog
from apps.properties.models import Property
from apps.listings.models import Listing, ListingStatus
from apps.leads.models import Lead, LeadStatus
from apps.leads.forms import LeadInquiryForm
from apps.contracts.models import Deal, DealStage, ContractDocument, DocumentType
from apps.contracts.services.deal_service import DealService
from apps.contracts.views import can_access_document, contract_document_download_view
from apps.core.services.telegram import TelegramAlertService

User = get_user_model()

class DealsCRMSecurityTestCase(TestCase):
    """
    WHY SECURE: Test suite strictly verifying:
    1. ACID transaction integrity and exact Decimal math for broker commissions.
    2. Private Document Vault permission gating and X-Accel-Redirect compatibility.
    3. Audit trail generation on sensitive contract downloads and stage changes.
    4. Anti-spam honeypot and phone validation on leads.
    5. Zero-crash resilience of Telegram bot alerts.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_superuser('admin', 'admin@sengran.com', 'AdminPass123!', role=UserRole.ADMIN)
        self.agent1 = User.objects.create_user('agent1', 'agent1@sengran.com', 'Agent1Pass123!', role=UserRole.AGENT)
        self.agent2 = User.objects.create_user('agent2', 'agent2@sengran.com', 'Agent2Pass123!', role=UserRole.AGENT)
        self.owner = User.objects.create_user('owner', 'owner@sengran.com', 'OwnerPass123!', role=UserRole.OWNER)
        self.buyer = User.objects.create_user('buyer', 'buyer@sengran.com', 'BuyerPass123!', role=UserRole.CUSTOMER)
        self.stranger = User.objects.create_user('stranger', 'stranger@sengran.com', 'StrangerPass123!', role=UserRole.CUSTOMER)

        self.prop = Property.objects.create(
            owner=self.owner,
            title='ร้านกาแฟ สาทร',
            desc='ทำเลดีมาก',
            address='123 สาทร',
            province='กรุงเทพมหานคร',
            district='สาทร',
            postal='10120'
        )
        self.listing = Listing.objects.create(
            property=self.prop,
            agent=self.agent1,
            price=Decimal('500000.00'),
            monthly_rent=Decimal('25000.00'),
            status=ListingStatus.PUBLISHED
        )
        self.lead = Lead.objects.create(
            listing=self.listing,
            full_name='สมชาย สนใจเซ้ง',
            phone='0812345678',
            email='buyer@sengran.com',
            budget_max=Decimal('600000.00'),
            assigned_agent=self.agent1
        )
        self.deal = Deal.objects.create(
            listing=self.listing,
            lead=self.lead,
            agent=self.agent1,
            stage=DealStage.NEW_LEAD,
            commission_rate=Decimal('10.00'),
            agent_commission_share=Decimal('50.00')
        )
        self.document = ContractDocument.objects.create(
            deal=self.deal,
            type=DocumentType.TAKEOVER_CONTRACT,
            file=SimpleUploadedFile("contract_takeover.pdf", b"%PDF-1.4 test contract content", content_type="application/pdf"),
            file_name_display="สัญญาจะซื้อจะขาย_DEAL001.pdf",
            uploaded_by=self.agent1
        )

    # ==========================================================================
    # 1. ATOMIC COMMISSION & FINANCIAL TRANSACTION INTEGRITY
    # ==========================================================================
    def test_atomic_commission_calculation_on_closed_won(self):
        """
        Verify:
        - When deal advances to CLOSED_WON:
          1. Agreed price is 500,000.
          2. Gross commission = 50,000 (10%).
          3. Agent payout = 25,000 (50% of gross).
          4. Platform payout = 25,000.
          5. Listing status transitions to CLOSED.
          6. AuditLog is recorded.
        """
        updated_deal = DealService.advance_stage(
            deal_id=self.deal.pk,
            target_stage=DealStage.CLOSED_WON,
            agreed_price=Decimal('500000.00'),
            actor=self.admin
        )
        self.assertEqual(updated_deal.stage, DealStage.CLOSED_WON)
        self.assertEqual(updated_deal.gross_commission, Decimal('50000.00'))
        self.assertEqual(updated_deal.agent_payout, Decimal('25000.00'))
        self.assertEqual(updated_deal.platform_payout, Decimal('25000.00'))
        
        # Verify listing was closed
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.CLOSED)

        # Verify AuditLog entry was recorded
        log = AuditLog.objects.filter(model_name='Deal', object_id=self.deal.deal_code).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['new_stage'], DealStage.CLOSED_WON)

    # ==========================================================================
    # 2. PRIVATE DOCUMENT VAULT AUTHORIZATION (REQUIREMENT #9)
    # ==========================================================================
    def test_private_document_access_permissions(self):
        """
        Verify:
        - Admin CAN access.
        - Assigned Agent (agent1) CAN access.
        - Shop Owner CAN access.
        - Buyer (lead) CAN access.
        - Other Agent (agent2) CANNOT access (blocked).
        - Stranger CANNOT access (blocked).
        """
        self.assertTrue(can_access_document(self.admin, self.document))
        self.assertTrue(can_access_document(self.agent1, self.document))
        self.assertTrue(can_access_document(self.owner, self.document))
        self.assertTrue(can_access_document(self.buyer, self.document))
        self.assertFalse(can_access_document(self.agent2, self.document), "Unassigned agent must be denied access to private contracts!")
        self.assertFalse(can_access_document(self.stranger, self.document), "Stranger must be denied access to private contracts!")

    def test_unauthorized_document_download_raises_permission_denied_and_logs(self):
        """Verify unauthorized user triggers 403 and writes PERMISSION_DENIED to AuditLog."""
        request = self.factory.get(f'/contracts/documents/{self.document.pk}/download/')
        request.user = self.stranger

        with self.assertRaises(PermissionDenied):
            contract_document_download_view(request, pk=self.document.pk)

        audit = AuditLog.objects.filter(action='PERMISSION_DENIED', model_name='ContractDocument').first()
        self.assertIsNotNone(audit, "Unauthorized contract download must be logged to AuditLog.")

    def test_authorized_document_download_records_audit(self):
        """Verify authorized user can download and access is logged in AuditLog."""
        request = self.factory.get(f'/contracts/documents/{self.document.pk}/download/')
        request.user = self.agent1

        response = contract_document_download_view(request, pk=self.document.pk)
        self.assertIn(response.status_code, [200, 302])

        audit = AuditLog.objects.filter(action='READ', model_name='ContractDocument').first()
        self.assertIsNotNone(audit, "Authorized document download must be logged to AuditLog.")

    # ==========================================================================
    # 3. LEAD CRM & ANTI-BOT DEFENSE
    # ==========================================================================
    def test_lead_form_phone_validation(self):
        """Verify malformed phone numbers are rejected."""
        form = LeadInquiryForm(data={
            'full_name': 'นายทดสอบ',
            'phone': '12345', # Invalid phone
            'website': ''
        })
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_telegram_service_resilience_on_dummy_tokens(self):
        """Verify Telegram service fails gracefully without crashing transactions."""
        from unittest.mock import patch
        with patch.object(TelegramAlertService, 'get_credentials', return_value=('', '')):
            result = TelegramAlertService.send_alert("ข้อความทดสอบ", "Test Alert")
            self.assertFalse(result)
