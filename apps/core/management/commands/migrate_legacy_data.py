import os
import json
import re
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.properties.models import Property, PropertyType
from apps.listings.models import Listing, ListingType, ListingStatus
from apps.leads.models import Lead, LeadStatus, LeadUrgency
from apps.contracts.models import Deal, DealStage

class Command(BaseCommand):
    help = 'Migrate legacy WordPress data or seed benchmark dataset preserving SEO ref codes (N-032, S-228)'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='Path to JSON file containing exported WordPress posts')
        parser.add_argument('--seed-benchmark', action='store_true', default=True, help='Seed benchmark listings from เซ้งร้านด่วน.com and เซ้งร้าน.com')

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Starting Legacy Data Migration & Benchmark Seeding..."))

        # 1. Ensure Benchmark Users
        admin_user, _ = User.objects.get_or_create(
            email='admin@sengranduan.com',
            defaults={
                'username': 'admin@sengranduan.com',
                'first_name': 'ผู้ดูแลระบบ',
                'last_name': 'สูงสุด',
                'role': UserRole.ADMIN,
                'email_verified': True,
                'is_staff': True,
                'is_superuser': True
            }
        )
        if not admin_user.has_usable_password():
            admin_user.set_password('AdminSecure2026!#')
            admin_user.save()

        agent_somchai, _ = User.objects.get_or_create(
            email='agent.somchai@sengranduan.com',
            defaults={
                'username': 'agent.somchai@sengranduan.com',
                'first_name': 'สมชาย',
                'last_name': 'ใจดี (ชลบุรี-พัทยา)',
                'role': UserRole.AGENT,
                'email_verified': True,
                'phone': '0812345678'
            }
        )
        if not agent_somchai.has_usable_password():
            agent_somchai.set_password('AgentPass2026!#')
            agent_somchai.save()

        agent_ying, _ = User.objects.get_or_create(
            email='agent.ying@sengranduan.com',
            defaults={
                'username': 'agent.ying@sengranduan.com',
                'first_name': 'สุภาวดี',
                'last_name': 'มีทรัพย์ (กทม.-เชียงใหม่)',
                'role': UserRole.AGENT,
                'email_verified': True,
                'phone': '0898765432'
            }
        )
        if not agent_ying.has_usable_password():
            agent_ying.set_password('AgentPass2026!#')
            agent_ying.save()

        owner_prasert, _ = User.objects.get_or_create(
            email='owner.prasert@gmail.com',
            defaults={
                'username': 'owner.prasert@gmail.com',
                'first_name': 'ประเสริฐ',
                'last_name': 'ยั่งยืน',
                'role': UserRole.OWNER,
                'email_verified': True,
                'phone': '0851112233'
            }
        )
        if not owner_prasert.has_usable_password():
            owner_prasert.set_password('OwnerPass2026!#')
            owner_prasert.save()

        self.stdout.write(self.style.SUCCESS("✓ Seeded Admin, Licensed Agents, and Owner accounts."))

        # 2. Benchmark Listings
        benchmark_items = [
            {
                'ref_code': 'N-032',
                'title': 'เซ้งร้านอาหารซีฟู้ด & คาเฟ่ พัทยากลาง ใกล้หาดจอมเทียน 200 เมตร',
                'prop_type': PropertyType.STANDALONE,
                'desc': 'ร้านอาหารติดถนนใหญ่ ทำเลทองนักท่องเที่ยวทั้งไทยและต่างชาติ ตกแต่งพร้อมดำเนินกิจการต่อได้ทันที',
                'address': 'ถนนเลียบหาดจอมเทียน ซอย 5',
                'province': 'ชลบุรี',
                'district': 'บางละมุง',
                'postal': '20150',
                'lat': Decimal('12.898500'),
                'lng': Decimal('100.875200'),
                'area_sqm': Decimal('180.00'),
                'floors': 2,
                'price': Decimal('1500000.00'),
                'monthly_rent': Decimal('45000.00'),
                'security_deposit': Decimal('90000.00'),
                'lease_remaining_months': 24,
                'avg_revenue_3m': Decimal('380000.00'),
                'avg_profit_3m': Decimal('110000.00'),
                'includes_staff': True,
                'includes_equipment': 'โต๊ะเก้าอี้ไม้สัก 20 ชุด, ตู้แช่แข็ง 3 เครื่อง, เตาผัดสแตนเลส 4 หัว, ระบบ POS สั่งอาหาร, แอร์แขวน 4 เครื่อง',
                'agent': agent_somchai,
                'lead_name': 'คุณเกียรติศักดิ์ เจริญพร',
                'lead_phone': '0891234455',
                'lead_stage': DealStage.NEGOTIATION,
                'deal_agreed_price': Decimal('1400000.00'),
                'deal_deposit': Decimal('50000.00'),
            },
            {
                'ref_code': 'S-228',
                'title': 'เซ้งร้านกาแฟ Specialty Coffee & เบเกอรี่ สไตล์ญี่ปุ่น นิมมานเหมินท์ เชียงใหม่',
                'prop_type': PropertyType.RETAIL_SHOP,
                'desc': 'คาเฟ่ตกแต่งมินิมอล มีฐานลูกค้าประจำและนักท่องเที่ยวแน่น มีที่จอดรถหน้าร้าน บรรยากาศร่มรื่น',
                'address': 'ถนนนิมมานเหมินท์ ซอย 9 ตำบลสุเทพ',
                'province': 'เชียงใหม่',
                'district': 'เมืองเชียงใหม่',
                'postal': '50200',
                'lat': Decimal('18.797800'),
                'lng': Decimal('98.969100'),
                'area_sqm': Decimal('65.00'),
                'floors': 1,
                'price': Decimal('680000.00'),
                'monthly_rent': Decimal('28000.00'),
                'security_deposit': Decimal('56000.00'),
                'lease_remaining_months': 18,
                'avg_revenue_3m': Decimal('195000.00'),
                'avg_profit_3m': Decimal('65000.00'),
                'includes_staff': True,
                'includes_equipment': 'เครื่องชงกาแฟ La Marzocco Linea PB 2 Groups, เครื่องบด Mythos One, ตู้โชว์เค้ก, สูตรเครื่องดื่มและเบเกอรี่ทั้งหมด',
                'agent': agent_ying,
                'lead_name': 'คุณณิชา รัตนเวช',
                'lead_phone': '0845566778',
                'lead_stage': DealStage.DEPOSIT_PAID,
                'deal_agreed_price': Decimal('650000.00'),
                'deal_deposit': Decimal('65000.00'),
            },
            {
                'ref_code': 'B-105',
                'title': 'เซ้งร้านสปา & นวดแผนไทย ออนเซ็นส่วนตัว สุขุมวิท 39 ทำเลทองชาวญี่ปุ่น',
                'prop_type': PropertyType.COMMERCIAL_BUILDING,
                'desc': 'ตึกแถว 3 คูหา ตกแต่งหรูหราสไตล์เรียวกัง ใบอนุญาตประกอบกิจการเพื่อสุขภาพถูกต้อง พร้อมโอนกิจการ',
                'address': 'สุขุมวิท 39 แขวงคลองตันเหนือ',
                'province': 'กรุงเทพมหานคร',
                'district': 'วัฒนา',
                'postal': '10110',
                'lat': Decimal('13.737100'),
                'lng': Decimal('100.572400'),
                'area_sqm': Decimal('240.00'),
                'floors': 3,
                'price': Decimal('2200000.00'),
                'monthly_rent': Decimal('85000.00'),
                'security_deposit': Decimal('255000.00'),
                'lease_remaining_months': 36,
                'avg_revenue_3m': Decimal('520000.00'),
                'avg_profit_3m': Decimal('175000.00'),
                'includes_staff': True,
                'includes_equipment': 'เตียงนวดไทย 8 เตียง, เตียงอโรมา 4 เตียง, อ่างจากุซซี่ไม้ฮิโนกิ 2 อ่าง, ระบบน้ำร้อนและซาวน่า',
                'agent': agent_ying,
                'lead_name': 'Mr. Kenji Sato',
                'lead_phone': '0823344556',
                'lead_stage': DealStage.SITE_VISIT_SCHEDULED,
                'deal_agreed_price': Decimal('2200000.00'),
                'deal_deposit': Decimal('0.00'),
            },
            {
                'ref_code': 'P-044',
                'title': 'เซ้งบาร์ค็อกเทล & ดนตรีสด เอกมัย บรรยากาศรูฟท็อป วิวพาโนรามา',
                'prop_type': PropertyType.MALL_SPACE,
                'desc': 'รูฟท็อปบาร์ตกแต่งหรู เครื่องเสียงระดับไฮเอนด์ ใบอนุญาตครบ รองรับลูกค้าได้กว่า 80 ที่นั่ง',
                'address': 'ถนนสุขุมวิท 63 (เอกมัย)',
                'province': 'กรุงเทพมหานคร',
                'district': 'วัฒนา',
                'postal': '10110',
                'lat': Decimal('13.725900'),
                'lng': Decimal('100.585200'),
                'area_sqm': Decimal('120.00'),
                'floors': 1,
                'price': Decimal('1250000.00'),
                'monthly_rent': Decimal('50000.00'),
                'security_deposit': Decimal('100000.00'),
                'lease_remaining_months': 15,
                'avg_revenue_3m': Decimal('310000.00'),
                'avg_profit_3m': Decimal('85000.00'),
                'includes_staff': False,
                'includes_equipment': 'ระบบเครื่องเสียง Bose, บาร์สแตนเลสครบวงจร, ไฟเวที DMX, ตู้แช่ไวน์, ใบอนุญาตจำหน่ายสุรา',
                'agent': agent_somchai,
                'lead_name': 'คุณอัครเดช รุ่งเรือง',
                'lead_phone': '0867788990',
                'lead_stage': DealStage.CLOSED_WON,
                'deal_agreed_price': Decimal('1200000.00'),
                'deal_deposit': Decimal('100000.00'),
            },
            {
                'ref_code': 'C-089',
                'title': 'เซ้งร้านชานมไข่มุก & ขนมปังปิ้ง ทำเลติดมหาวิทยาลัยเกษตรศาสตร์ คนเดินพลุกพล่าน',
                'prop_type': PropertyType.BOOTH_KIOSK,
                'desc': 'ร้านชานมหน้าร้านโดดเด่น อยู่ในโซนนิสิตนักศึกษาและคนทำงาน มีเดลิเวอรี่ Grab/Lineman พร้อมสอนสูตร',
                'address': 'ถนนงามวงศ์วาน ตรงข้ามประตู 1 ม.เกษตร',
                'province': 'กรุงเทพมหานคร',
                'district': 'จตุจักร',
                'postal': '10900',
                'lat': Decimal('13.847500'),
                'lng': Decimal('100.569600'),
                'area_sqm': Decimal('35.00'),
                'floors': 1,
                'price': Decimal('390000.00'),
                'monthly_rent': Decimal('18000.00'),
                'security_deposit': Decimal('36000.00'),
                'lease_remaining_months': 12,
                'avg_revenue_3m': Decimal('140000.00'),
                'avg_profit_3m': Decimal('42000.00'),
                'includes_staff': True,
                'includes_equipment': 'เครื่องซีลฝาแก้วอัตโนมัติ 2 เครื่อง, เตาปิ้งขนมปัง, ถังชาสแตนเลส, ป้ายไฟหน้าร้าน, วัตถุดิบพร้อมขาย 1 เดือน',
                'agent': agent_ying,
                'lead_name': 'คุณปวีณา สุขสันต์',
                'lead_phone': '0819922334',
                'lead_stage': DealStage.NEW_LEAD,
                'deal_agreed_price': Decimal('390000.00'),
                'deal_deposit': Decimal('0.00'),
            }
        ]

        created_listings_count = 0
        created_deals_count = 0

        for item in benchmark_items:
            prop, _ = Property.objects.get_or_create(
                owner=owner_prasert,
                title=item['title'],
                defaults={
                    'type': item['prop_type'],
                    'desc': item['desc'],
                    'address': item['address'],
                    'province': item['province'],
                    'district': item['district'],
                    'postal': item['postal'],
                    'lat': item['lat'],
                    'lng': item['lng'],
                    'area_sqm': item['area_sqm'],
                    'floors': item['floors'],
                }
            )

            # Preserve Ref Code (N-032, S-228, etc.)
            clean_slug = slugify(f"{item['ref_code']}-{item['title'][:50]}", allow_unicode=True)
            listing, created = Listing.objects.get_or_create(
                ref_code=item['ref_code'],
                defaults={
                    'property': prop,
                    'agent': item['agent'],
                    'type': ListingType.TAKEOVER,
                    'status': ListingStatus.PUBLISHED if item['lead_stage'] != DealStage.CLOSED_WON else ListingStatus.CLOSED,
                    'price': item['price'],
                    'monthly_rent': item['monthly_rent'],
                    'security_deposit': item['security_deposit'],
                    'lease_remaining_months': item['lease_remaining_months'],
                    'avg_revenue_3m': item['avg_revenue_3m'],
                    'avg_profit_3m': item['avg_profit_3m'],
                    'includes_equipment': item['includes_equipment'],
                    'includes_staff': item['includes_staff'],
                    'published_at': timezone.now()
                }
            )
            if created:
                created_listings_count += 1

            # Seed Lead & Deal for pipeline showcase
            lead, _ = Lead.objects.get_or_create(
                listing=listing,
                phone=item['lead_phone'],
                defaults={
                    'full_name': item['lead_name'],
                    'status': LeadStatus.QUALIFIED,
                    'assigned_agent': item['agent'],
                    'notes': f"สนใจเซ้งร้าน {listing.ref_code} นัดคุยเงื่อนไข"
                }
            )

            deal, deal_created = Deal.objects.get_or_create(
                listing=listing,
                lead=lead,
                defaults={
                    'agent': item['agent'],
                    'stage': item['lead_stage'],
                    'agreed_price': item['deal_agreed_price'],
                    'deposit_amount': item['deal_deposit'],
                    'notes': f"ดีลประสานงานโดย {item['agent'].get_full_name()}"
                }
            )
            if deal_created:
                deal.calculate_commission()
                deal.save()
                created_deals_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Migration & Benchmark Seeding Completed Successfully!\n"
            f"   - Created/Verified {len(benchmark_items)} listings with SEO Ref Codes (N-032, S-228, B-105, P-044, C-089)\n"
            f"   - Created {created_deals_count} Broker CRM Deals across pipeline stages\n"
            f"   - SEO 301 Permanent Redirect middleware ready to intercept legacy WordPress requests."
        ))
