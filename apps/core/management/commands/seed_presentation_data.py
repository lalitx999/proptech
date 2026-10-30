import os
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile

from apps.accounts.models import User, UserRole, VIPPaymentTransaction
from apps.properties.models import Property, PropertyType, PropertyImage
from apps.listings.models import Listing, ListingType, ListingStatus, FeePayer
from apps.leads.models import Lead, LeadStatus, LeadUrgency
from apps.contracts.models import Deal, DealStage, ContractDocument, DocumentType
from apps.core.models import ContactMessage

class Command(BaseCommand):
    help = 'Seeds presentation-ready rich commercial takeover data, active pipeline deals, and VIP transactions'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Seeding presentation-ready rich dataset for เซ้งร้าน.com..."))

        # 1. Accounts
        admin_user, _ = User.objects.get_or_create(
            username='admin@xn--72ch2atb1d4a4f1fudfc.com',
            defaults={
                'email': 'admin@xn--72ch2atb1d4a4f1fudfc.com',
                'first_name': 'ผู้ดูแลระบบ',
                'last_name': 'แอดมิน',
                'role': UserRole.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'email_verified': True,
            }
        )
        admin_user.set_password('DevPass1234!')
        admin_user.save()

        vip_owner, _ = User.objects.get_or_create(
            username='owner.vip@sengran.com',
            defaults={
                'email': 'owner.vip@sengran.com',
                'first_name': 'ดวงฤทัย',
                'last_name': 'ช้างน้อย',
                'role': UserRole.OWNER,
                'phone': '0891234567',
                'email_verified': True,
                'is_vip': True,
                'vip_expires_at': timezone.now() + datetime.timedelta(days=30),
            }
        )
        vip_owner.set_password('DevPass1234!')
        vip_owner.is_vip = True
        vip_owner.vip_expires_at = timezone.now() + datetime.timedelta(days=30)
        vip_owner.save()

        free_owner, _ = User.objects.get_or_create(
            username='owner.prasert@gmail.com',
            defaults={
                'email': 'owner.prasert@gmail.com',
                'first_name': 'ประเสริฐ',
                'last_name': 'กิจการรุ่งเรือง',
                'role': UserRole.OWNER,
                'phone': '0829876543',
                'email_verified': True,
            }
        )
        free_owner.set_password('DevPass1234!')
        free_owner.save()

        agent_user, _ = User.objects.get_or_create(
            username='agent.somchai@xn--72ch2atb1d4a4f1fudfc.com',
            defaults={
                'email': 'agent.somchai@xn--72ch2atb1d4a4f1fudfc.com',
                'first_name': 'สมชาย',
                'last_name': 'มือทอง (นายหน้า)',
                'role': UserRole.AGENT,
                'phone': '0812345678',
                'email_verified': True,
            }
        )
        agent_user.set_password('DevPass1234!')
        agent_user.save()

        # 2. Rich Commercial Shop Listings
        demo_shops = [
            {
                'title': 'เซ้งด่วน! ร้านชาบูหม้อไฟสไตล์ญี่ปุ่น ซอยอารีย์ พหลโยธิน 7',
                'type': PropertyType.RESTAURANT_SHABU,
                'price': Decimal('550000.00'),
                'monthly_rent': Decimal('38000.00'),
                'deposit': Decimal('76000.00'),
                'lease_months': 18,
                'profit_3m': Decimal('72000.00'),
                'revenue_3m': Decimal('245000.00'),
                'district': 'พญาไท',
                'province': 'กรุงเทพมหานคร',
                'address': 'ซอยอารีย์ 1 ถนนพหลโยธิน 7 แขวงพญาไท เขตพญาไท กรุงเทพฯ',
                'sqm': Decimal('85.00'),
                'equipment': 'โต๊ะเตาแม่เหล็กไฟฟ้า 14 ชุด, ตู้แช่แข็ง 2 เครื่อง, สไลด์เนื้อ, แอร์ 4 ตัว, เคาน์เตอร์คิดเงิน POS',
                'staff': 4,
                'owner': vip_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 412,
            },
            {
                'title': 'เซ้งคาเฟ่มินิมอลสไตล์เกาหลี ย่านทองหล่อ พร้อมเครื่อง La Marzocco',
                'type': PropertyType.CAFE_BEVERAGE,
                'price': Decimal('890000.00'),
                'monthly_rent': Decimal('55000.00'),
                'deposit': Decimal('110000.00'),
                'lease_months': 24,
                'profit_3m': Decimal('95000.00'),
                'revenue_3m': Decimal('310000.00'),
                'district': 'วัฒนา',
                'province': 'กรุงเทพมหานคร',
                'address': 'ปากซอยทองหล่อ 13 แขวงคลองตันเหนือ เขตวัฒนา กรุงเทพฯ',
                'sqm': Decimal('65.00'),
                'equipment': 'เครื่องชงกาแฟ La Marzocco Linea PB, เครื่องบด Mythos One, ตู้โชว์เค้กนำเข้า, ชุดโซฟาโมเดิร์น',
                'staff': 3,
                'owner': vip_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 840,
            },
            {
                'title': 'เซ้งร้านสปาและนวดเพื่อสุขภาพ สุขุมวิท 39 ลูกค้าญี่ปุ่นประจำ 100%',
                'type': PropertyType.MASSAGE_SPA,
                'price': Decimal('1200000.00'),
                'monthly_rent': Decimal('65000.00'),
                'deposit': Decimal('130000.00'),
                'lease_months': 36,
                'profit_3m': Decimal('140000.00'),
                'revenue_3m': Decimal('420000.00'),
                'district': 'วัฒนา',
                'province': 'กรุงเทพมหานคร',
                'address': 'สุขุมวิท 39 ใกล้ BTS พร้อมพงษ์ เขตวัฒนา กรุงเทพฯ',
                'sqm': Decimal('140.00'),
                'equipment': 'เตียงนวดอโรมา 6 เตียง, ห้อง VIP ส่วนตัว 3 ห้อง, อ่างจากุซซี่, เก้าอี้นวดเท้า 8 ตัว, อุปกรณ์สปาครบชุด',
                'staff': 6,
                'owner': vip_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 560,
            },
            {
                'title': 'เซ้ง Rooftop Bar วิวเมือง ถ.สีลม ใบอนุญาตสุราและดนตรีสดครบ',
                'type': PropertyType.BAR_PUB_KARAOKE,
                'price': Decimal('1450000.00'),
                'monthly_rent': Decimal('75000.00'),
                'deposit': Decimal('150000.00'),
                'lease_months': 20,
                'profit_3m': Decimal('160000.00'),
                'revenue_3m': Decimal('580000.00'),
                'district': 'บางรัก',
                'province': 'กรุงเทพมหานคร',
                'address': 'ชั้น 7 อาคารติดถนนสีลม ใกล้ BTS ศาลาแดง เขตบางรัก กรุงเทพฯ',
                'sqm': Decimal('180.00'),
                'equipment': 'ระบบไฟเวทีดนตรีสด, มิกเซอร์และเครื่องเสียง JBL, บาร์ค็อกเทลสแตนเลสยาว 6 เมตร, ถังเบียร์สด',
                'staff': 5,
                'owner': free_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 920,
            },
            {
                'title': 'เซ้งร้านบุฟเฟต์ปิ้งย่างริมหาด พัทยาสาย 2 ทำเลทองนักท่องเที่ยว',
                'type': PropertyType.RESTAURANT_SHABU,
                'price': Decimal('750000.00'),
                'monthly_rent': Decimal('42000.00'),
                'deposit': Decimal('84000.00'),
                'lease_months': 15,
                'profit_3m': Decimal('85000.00'),
                'revenue_3m': Decimal('340000.00'),
                'district': 'บางละมุง',
                'province': 'ชลบุรี',
                'address': 'ถนนพัทยาสาย 2 อำเภอบางละมุง ชลบุรี',
                'sqm': Decimal('110.00'),
                'equipment': 'เตาปิ้งย่างไร้ควัน 20 โต๊ะ, ตู้แช่ไลน์อาหารสด 4 ตู้, แอร์ 5 ตัว, ระบบดูดควันติดตั้งใหม่',
                'staff': 5,
                'owner': vip_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 670,
            },
            {
                'title': 'เซ้ง Specialty Coffee นิมมานเหมินท์ เชียงใหม่ พร้อมที่จอดรถ',
                'type': PropertyType.CAFE_BEVERAGE,
                'price': Decimal('480000.00'),
                'monthly_rent': Decimal('28000.00'),
                'deposit': Decimal('56000.00'),
                'lease_months': 24,
                'profit_3m': Decimal('52000.00'),
                'revenue_3m': Decimal('185000.00'),
                'district': 'เมืองเชียงใหม่',
                'province': 'เชียงใหม่',
                'address': 'ถนนนิมมานเหมินท์ ซอย 9 อำเภอเมือง เชียงใหม่',
                'sqm': Decimal('70.00'),
                'equipment': 'เครื่องชงกาแฟ Synesso 2 หัว, บาร์ไม้โอ๊คแท้, เครื่องกรองน้ำ RO, เมล็ดกาแฟ Single Origin',
                'staff': 2,
                'owner': free_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 380,
            },
            {
                'title': 'เซ้งร้านทำเล็บและต่อขนตา สยามสแควร์ แหล่งวัยรุ่นใจกลางเมือง',
                'type': PropertyType.BEAUTY_SALON_NAILS,
                'price': Decimal('390000.00'),
                'monthly_rent': Decimal('35000.00'),
                'deposit': Decimal('70000.00'),
                'lease_months': 12,
                'profit_3m': Decimal('48000.00'),
                'revenue_3m': Decimal('160000.00'),
                'district': 'ปทุมวัน',
                'province': 'กรุงเทพมหานคร',
                'address': 'สยามสแควร์ ซอย 3 เขตปทุมวัน กรุงเทพฯ',
                'sqm': Decimal('40.00'),
                'equipment': 'เก้าอี้สปาเท้าปรับนอน 4 ตัว, สีเจลเกาหลีและญี่ปุ่นกว่า 300 สี, เครื่องอบเล็บ LED, เตียงต่อขนตา',
                'staff': 3,
                'owner': free_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 510,
            },
            {
                'title': 'เซ้งคลินิกเวชกรรมความงาม เอกมัย ใบอนุญาตสถานพยาบาลพร้อมดำเนินต่อ',
                'type': PropertyType.BEAUTY_SALON_NAILS,
                'price': Decimal('1850000.00'),
                'monthly_rent': Decimal('85000.00'),
                'deposit': Decimal('170000.00'),
                'lease_months': 36,
                'profit_3m': Decimal('210000.00'),
                'revenue_3m': Decimal('750000.00'),
                'district': 'วัฒนา',
                'province': 'กรุงเทพมหานคร',
                'address': 'ซอยสุขุมวิท 63 (เอกมัย) แขวงคลองตันเหนือ เขตวัฒนา กรุงเทพฯ',
                'sqm': Decimal('160.00'),
                'equipment': 'เครื่องเลเซอร์ Q-Switch, เครื่อง HIFU, เตียงตรวจคนไข้, ห้องทำหัตถการปลอดเชื้อ 3 ห้อง, แอร์ทุกห้อง',
                'staff': 4,
                'owner': vip_owner,
                'status': ListingStatus.PUBLISHED,
                'views': 780,
            },
            {
                'title': 'เซ้งร้านชานมไข่มุกและเบเกอรี่ ใกล้มหาวิทยาลัยเกษตรศาสตร์',
                'type': PropertyType.CAFE_BEVERAGE,
                'price': Decimal('280000.00'),
                'monthly_rent': Decimal('22000.00'),
                'deposit': Decimal('44000.00'),
                'lease_months': 14,
                'profit_3m': Decimal('38000.00'),
                'revenue_3m': Decimal('135000.00'),
                'district': 'จตุจักร',
                'province': 'กรุงเทพมหานคร',
                'address': 'ถนนงามวงศ์วาน ตรงข้ามประตู 1 ม.เกษตรศาสตร์ เขตจตุจักร กรุงเทพฯ',
                'sqm': Decimal('32.00'),
                'equipment': 'เครื่องซีลฝาแก้วอัตโนมัติ, ถังชาสแตนเลสเก็บความร้อน, เครื่องปั่น Smoothie วัตต์สูง, ตู้เย็น 2 ประตู',
                'staff': 2,
                'owner': free_owner,
                'status': ListingStatus.PENDING, # Pending for Admin Review Demo!
                'views': 45,
            }
        ]

        created_listings = []
        for sdata in demo_shops:
            prop, _ = Property.objects.get_or_create(
                title=sdata['title'],
                defaults={
                    'owner': sdata['owner'],
                    'type': sdata['type'],
                    'district': sdata['district'],
                    'province': sdata['province'],
                    'address': sdata['address'],
                    'postal': '10400' if 'กรุงเทพ' in sdata['province'] else ('20150' if 'ชลบุรี' in sdata['province'] else '50200'),
                    'desc': f"{sdata['title']} ทำเลทองพร้อมอุปกรณ์ดำเนินกิจการต่อได้ทันที มีพนักงานพร้อมทำงานต่อ {sdata['staff']} คน",
                    'area_sqm': sdata['sqm'],
                }
            )

            listing, _ = Listing.objects.get_or_create(
                property=prop,
                defaults={
                    'agent': agent_user,
                    'price': sdata['price'],
                    'monthly_rent': sdata['monthly_rent'],
                    'security_deposit': sdata['deposit'],
                    'lease_remaining_months': sdata['lease_months'],
                    'avg_profit_3m': sdata['profit_3m'],
                    'avg_revenue_3m': sdata['revenue_3m'],
                    'includes_equipment': sdata['equipment'],
                    'includes_staff': sdata['staff'] > 0,
                    'status': sdata['status'],
                    'type': ListingType.TAKEOVER,
                    'lease_transfer_fee_payer': FeePayer.HALF_HALF,
                    'view_count': sdata['views'],
                }
            )

            # Attach sample image if property doesn't have one
            if not prop.images.exists():
                sample_img_map = {
                    PropertyType.CAFE_BEVERAGE: 'uploads/properties/nimman_cafe.jpg',
                    PropertyType.MASSAGE_SPA: 'uploads/properties/sukhumvit_spa.jpg',
                    PropertyType.RESTAURANT_SHABU: 'uploads/properties/pattaya_seafood.jpg',
                }
                img_rel = sample_img_map.get(sdata['type'], 'uploads/properties/nimman_cafe.jpg')
                PropertyImage.objects.create(
                    property=prop,
                    image=img_rel,
                    is_cover=True
                )

            created_listings.append(listing)

        # 3. Simulated Leads & CRM
        sample_leads = [
            {'name': 'คุณวิภาดา จิตรอารีย์', 'phone': '0829998877', 'line': 'wiphada_c', 'budget': Decimal('600000.00'), 'urgency': LeadUrgency.IMMEDIATE, 'status': LeadStatus.NEW, 'idx': 0},
            {'name': 'คุณธนกร สุขสวัสดิ์', 'phone': '0815551234', 'line': 'tanakorn_bkk', 'budget': Decimal('1000000.00'), 'urgency': LeadUrgency.ONE_TO_THREE_MONTHS, 'status': LeadStatus.CONTACTED, 'idx': 1},
            {'name': 'คุณกิตติศักดิ์ พรหมมินทร์', 'phone': '0897774411', 'line': 'kitti_spa', 'budget': Decimal('1300000.00'), 'urgency': LeadUrgency.IMMEDIATE, 'status': LeadStatus.SITE_VISIT, 'idx': 2},
            {'name': 'คุณปิยะมาศ ลิ้มทอง', 'phone': '0842223366', 'line': 'piyamas_cafe', 'budget': Decimal('500000.00'), 'urgency': LeadUrgency.IMMEDIATE, 'status': LeadStatus.QUALIFIED, 'idx': 5},
            {'name': 'คุณอัศวิน เดชดำรง', 'phone': '0863339900', 'line': 'aswin_bar', 'budget': Decimal('1500000.00'), 'urgency': LeadUrgency.LOOKING, 'status': LeadStatus.CLOSED, 'idx': 3},
        ]

        created_leads = []
        for ldata in sample_leads:
            matched_listing = created_listings[ldata['idx']] if ldata['idx'] < len(created_listings) else created_listings[0]
            lead, _ = Lead.objects.get_or_create(
                phone=ldata['phone'],
                defaults={
                    'full_name': ldata['name'],
                    'line_id': ldata['line'],
                    'listing': matched_listing,
                    'budget_max': ldata['budget'],
                    'urgency': ldata['urgency'],
                    'status': ldata['status'],
                    'assigned_agent': agent_user,
                }
            )
            created_leads.append(lead)

        # 4. Simulated Deals in Pipeline
        deals_data = [
            {'listing': created_listings[0], 'lead': created_leads[0], 'price': Decimal('530000.00'), 'stage': DealStage.NEGOTIATION},
            {'listing': created_listings[1], 'lead': created_leads[1], 'price': Decimal('850000.00'), 'stage': DealStage.SITE_VISIT_SCHEDULED},
            {'listing': created_listings[2], 'lead': created_leads[2], 'price': Decimal('1150000.00'), 'stage': DealStage.DEPOSIT_PAID, 'deposit': Decimal('100000.00')},
            {'listing': created_listings[3], 'lead': created_leads[4], 'price': Decimal('1400000.00'), 'stage': DealStage.CLOSED_WON, 'deposit': Decimal('150000.00')},
        ]

        for ddata in deals_data:
            deal, created = Deal.objects.get_or_create(
                listing=ddata['listing'],
                defaults={
                    'lead': ddata['lead'],
                    'agent': agent_user,
                    'agreed_price': ddata['price'],
                    'deposit_amount': ddata.get('deposit', Decimal('0.00')),
                    'stage': ddata['stage'],
                    'commission_rate': Decimal('5.00'),
                    'agent_commission_share': Decimal('50.00'),
                }
            )
            deal.calculate_commission()
            deal.save()

        # 5. Simulated VIP Payment Transactions
        VIPPaymentTransaction.objects.get_or_create(
            ref_number='VIP-20261019-EAS01',
            defaults={
                'user': vip_owner,
                'amount': Decimal('1000.00'),
                'slip_hash': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                'status': VIPPaymentTransaction.Status.AUTO_VERIFIED,
                'bank_trans_ref': 'KBANK20261019849201',
                'easyslip_response': {
                    'success': True,
                    'data': {
                        'amountInSlip': 1000.0,
                        'isAmountMatched': True,
                        'isDuplicate': False,
                        'rawSlip': {
                            'receiver': {'displayName': 'ดวงฤทัย ช้างน้อย', 'account': {'name': 'KBANK 054-1-27630-0'}}
                        }
                    }
                }
            }
        )

        VIPPaymentTransaction.objects.get_or_create(
            ref_number='VIP-20261019-REV02',
            defaults={
                'user': free_owner,
                'amount': Decimal('1000.00'),
                'slip_hash': 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e',
                'status': VIPPaymentTransaction.Status.PENDING,
            }
        )

        # 6. Simulated Contact Messages
        ContactMessage.objects.get_or_create(
            phone='0815554433',
            defaults={
                'name': 'คุณธนพล เจริญกิตติ์',
                'email': 'tanapon@gmail.com',
                'subject': 'ปรึกษาเรื่องการประเมินราคาเซ้งร้านอาหาร',
                'message': 'มีร้านอาหารแถวอารีย์ต้องการให้ทีมงานช่วยเข้าไปประเมินราคาเซ้งที่เหมาะสม และขอทราบเงื่อนไขการส่งต่อสัญญาครับ',
                'is_resolved': False
            }
        )

        ContactMessage.objects.get_or_create(
            phone='0898881234',
            defaults={
                'name': 'คุณรัชนีวรรณ สดใส',
                'email': 'ratchanee@yahoo.com',
                'subject': 'สนใจหาเซ้งร้านคาเฟ่',
                'message': 'งบประมาณ 500,000 - 800,000 บาท โซนสุขุมวิทหรือทองหล่อ มีที่จอดรถ ถ้ามีทรัพย์ใหม่รบกวนโทรแจ้งด้วยค่ะ',
                'is_resolved': True
            }
        )

        self.stdout.write(self.style.SUCCESS("✅ Successfully seeded rich presentation dataset for เซ้งร้าน.com!"))
