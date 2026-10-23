import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

class EmailNotificationService:
    """
    Robust Transactional Email Notification Service for เซ้งร้านด่วน.com (tchhi.online)
    Features:
    1. Zero-Crash Guarantee: Email delivery issues will never crash user workflows.
    2. HTML + Plaintext: Rich responsive email templates with plain text fallbacks.
    3. Hostinger SMTP & Local Fallbacks.
    """

    @classmethod
    def _send(cls, subject: str, html_content: str, to_emails: list, from_email: str = None) -> bool:
        if not to_emails:
            return False

        sender = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'เซ้งร้านด่วน.com <sengranduan@tchhi.online>')
        text_content = strip_tags(html_content)

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=sender,
                to=to_emails,
                reply_to=['sengranduan@tchhi.online']
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info(f"Email dispatched successfully: '{subject}' to {to_emails}")
            return True
        except Exception as e:
            logger.warning(f"Email delivery failed (non-critical): {e} for subject '{subject}' to {to_emails}")
            return False

    @classmethod
    def _wrap_template(cls, title: str, preheader: str, body_html: str) -> str:
        """
        Wraps content in a responsive, branded HTML email template.
        """
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
    body {{ margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
    .wrapper {{ width: 100%; max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; margin-top: 24px; margin-bottom: 24px; }}
    .header {{ background: #0f172a; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; color: #ffffff; font-size: 20px; font-weight: 900; letter-spacing: -0.5px; }}
    .header span {{ color: #e11d74; }}
    .content {{ padding: 32px 24px; color: #334155; line-height: 1.6; font-size: 14px; }}
    .btn {{ display: inline-block; background: #e11d74; color: #ffffff !important; text-decoration: none; padding: 12px 28px; font-size: 14px; font-weight: bold; border-radius: 12px; margin: 20px 0; }}
    .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 8px; font-weight: bold; font-size: 11px; }}
    .badge-green {{ background: #dcfce7; color: #166534; }}
    .badge-pink {{ background: #fce7f3; color: #9d174d; }}
    .box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin: 16px 0; }}
</style>
</head>
<body>
    <div style="display:none;font-size:1px;color:#333;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
        {preheader}
    </div>
    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc;">
        <tr>
            <td align="center">
                <div class="wrapper">
                    <div class="header">
                        <h1>เซ้งร้าน<span>ด่วน.com</span></h1>
                        <p style="margin: 4px 0 0; color: #94a3b8; font-size: 11px;">แพลตฟอร์มเซ้งร้านและธุรกิจทำเลทองอันดับ 1</p>
                    </div>
                    <div class="content">
                        {body_html}
                    </div>
                    <div class="footer">
                        <p style="margin:0 0 6px;">อีเมลนี้ส่งจากระบบอัตโนมัติ เซ้งร้านด่วน.com (tchhi.online)</p>
                        <p style="margin:0;">หากมีข้อสงสัย ติดต่อฝ่ายบริการลูกค้า: sengranduan@tchhi.online</p>
                    </div>
                </div>
            </td>
        </tr>
    </table>
</body>
</html>"""

    @classmethod
    def send_registration_otp_email(cls, user, otp_code: str) -> bool:
        """
        Dispatches 6-digit OTP verification email for new user registration.
        Designed with high-deliverability anti-spam standards (SPF/DKIM compatible).
        """
        name = user.first_name or user.username
        subject = f"รหัส OTP ยืนยันตัวตน: {otp_code} — เซ้งร้านด่วน"
        preheader = f"รหัส OTP 6 หลักสำหรับยืนยันการเปิดบัญชี เซ้งร้านด่วน คือ {otp_code} (หมดอายุใน 15 นาที)"

        body = f"""
            <div style="text-align: center; margin-bottom: 16px;">
                <span class="badge badge-pink" style="font-size: 12px; padding: 6px 14px;">🔐 ยืนยันตัวตนการสมัครสมาชิก</span>
            </div>
            <h2 style="margin-top:0; color:#0f172a; font-size:20px; text-align:center;">รหัส OTP ยืนยันอีเมลของคุณ</h2>
            <p style="text-align:center; color:#64748b; font-size:13px; margin-top:4px;">
                สวัสดีคุณ <strong>{name}</strong> ขอบคุณที่ลงทะเบียนกับ <strong>เซ้งร้านด่วน.com</strong><br>
                กรุณานำรหัส OTP 6 หลักด้านล่างนี้ ไปกรอกในหน้าต่างยืนยันตัวตนเพื่อเปิดใช้งานบัญชีของคุณ:
            </p>
            
            <div style="text-align: center; margin: 26px 0;">
                <div style="display: inline-block; background: #0f172a; color: #ffffff; padding: 18px 32px; border-radius: 16px; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.15);">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: #f472b6; font-weight: bold; margin-bottom: 6px;">รหัสยืนยัน OTP (6 หลัก)</div>
                    <div style="font-size: 38px; font-weight: 900; letter-spacing: 12px; font-family: 'Courier New', Courier, monospace; color: #ffffff; padding-left: 12px;">{otp_code}</div>
                </div>
            </div>

            <div class="box" style="background:#f8fafc; border-left: 4px solid #e11d74; font-size: 12px; color: #475569;">
                <p style="margin: 0 0 6px;"><strong>ข้อควรระวังเพื่อความปลอดภัย:</strong></p>
                <ul style="margin: 0; padding-left: 18px; line-height: 1.6;">
                    <li>รหัส OTP นี้มีอายุการใช้งาน <strong>15 นาที</strong> นับจากเวลาที่ส่ง</li>
                    <li>ห้ามเปิดเผยรหัสนี้แก่ผู้อื่น เจ้าหน้าที่เซ้งร้านด่วนจะไม่มีวันขอรหัส OTP จากคุณ</li>
                    <li>หากคุณไม่ได้เป็นผู้ขอสมัครสมาชิก สามารถเพิกเฉยต่ออีเมลฉบับนี้ได้อย่างปลอดภัย</li>
                </ul>
            </div>
        """

        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        return cls._send(subject=subject, html_content=html, to_emails=[user.email])

    @classmethod
    def send_verification_email(cls, user, verification_url: str) -> bool:
        """
        Dispatches account activation email with secure token.
        """
        name = user.first_name or user.username
        subject = "ยืนยันอีเมลเพื่อเปิดใช้งานบัญชี — เซ้งร้านด่วน.com"
        preheader = f"สวัสดีคุณ {name} กรุณากดยืนยันอีเมลของคุณเพื่อเริ่มใช้งาน"

        body = f"""
            <h2 style="margin-top:0; color:#0f172a; font-size:18px;">ยินดีต้อนรับสู่ เซ้งร้านด่วน.com!</h2>
            <p>สวัสดีคุณ <strong>{name}</strong>,</p>
            <p>ขอบคุณที่ลงทะเบียนเป็นสมาชิกกับเรา เพื่อความปลอดภัยและเปิดสิทธิ์การใช้งานเต็มรูปแบบ กรุณากดปุ่มด้านล่างเพื่อยืนยันที่อยู่อีเมลของคุณ:</p>
            <div style="text-align: center;">
                <a href="{verification_url}" class="btn">✓ ยืนยันอีเมลทันที</a>
            </div>
            <p style="font-size:12px; color:#64748b;">หรือคัดลอกลิงก์นี้ไปวางในเบราว์เซอร์:<br><a href="{verification_url}" style="color:#e11d74; word-break:break-all;">{verification_url}</a></p>
            <p style="font-size:11px; color:#94a3b8; margin-top:24px;">* หากคุณไม่ได้เป็นผู้สร้างบัญชีนี้ กรุณาเพิกเฉยต่อข้อความนี้ ลิงก์จะหมดอายุโดยอัตโนมัติ</p>
        """

        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        return cls._send(subject=subject, html_content=html, to_emails=[user.email])

    @classmethod
    def send_vip_activation_email(cls, user, tier_label: str, amount: float, expires_at, ref_number: str) -> bool:
        """
        Dispatches VIP membership confirmation & receipt to customer.
        """
        name = user.first_name or user.username
        subject = f"ยืนยันการเปิดสิทธิ์ {tier_label} สำเร็จ — เซ้งร้านด่วน.com"
        preheader = f"ยินดีด้วยคุณ {name}! สิทธิ์ {tier_label} ของคุณเปิดใช้งานเรียบร้อยแล้ว"
        exp_text = expires_at.strftime('%d/%m/%Y') if expires_at else 'ไม่จำกัดระยะเวลา (ตลอดชีพ)'

        body = f"""
            <div style="text-align: center; margin-bottom: 20px;">
                <span class="badge badge-green">✓ ชำระเงินและเปิดสิทธิ์สำเร็จ</span>
            </div>
            <h2 style="margin-top:0; color:#0f172a; font-size:18px; text-align: center;">ยินดีต้อนรับสมาชิก {tier_label}!</h2>
            <p>สวัสดีคุณ <strong>{name}</strong>,</p>
            <p>ระบบตรวจสอบการชำระเงินเรียบร้อยแล้ว บัญชีของคุณได้รับการอัปเกรดเป็น <strong>{tier_label}</strong> ทันที โดยมีรายละเอียดดังนี้:</p>
            
            <div class="box">
                <table width="100%" style="font-size: 13px;">
                    <tr>
                        <td style="color:#64748b; padding: 4px 0;">แพ็กเกจ:</td>
                        <td align="right" style="font-weight:bold; color:#0f172a;">{tier_label}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b; padding: 4px 0;">ยอดชำระ:</td>
                        <td align="right" style="font-weight:bold; color:#059669; font-family: monospace;">฿{amount:,.2f}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b; padding: 4px 0;">เลขอ้างอิง:</td>
                        <td align="right" style="font-family: monospace; color:#64748b;">{ref_number}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b; padding: 4px 0;">อายุสมาชิกถึง:</td>
                        <td align="right" style="font-weight:bold; color:#e11d74;">{exp_text}</td>
                    </tr>
                </table>
            </div>

            <p>สิทธิประโยชน์ของคุณ:</p>
            <ul style="padding-left: 20px; font-size: 13px;">
                <li>โพสต์ประกาศเซ้งร้านขึ้นหน้าแรกและลำดับแรกๆ</li>
                <li>ป้ายกำกับ VIP เด่นสะดุดตา ดึงดูดผู้รับเซ้ง</li>
                <li>กระจายโพสต์ลงกลุ่ม Facebook และช่องทางพาร์ทเนอร์</li>
            </ul>

            <div style="text-align: center; margin-top: 24px;">
                <a href="http://127.0.0.1:8000/accounts/dashboard/" class="btn">ไปที่ระบบจัดการร้านค้า</a>
            </div>
        """

        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        return cls._send(subject=subject, html_content=html, to_emails=[user.email])

    @classmethod
    def send_listing_approved_email(cls, listing) -> bool:
        """
        Notifies owner that their shop listing is approved and published live.
        """
        owner = listing.property.owner
        if not owner or not owner.email:
            return False

        name = owner.first_name or owner.username
        shop_title = listing.property.title
        subject = f"ร้านค้า '{shop_title}' ของคุณได้รับการอนุมัติเผยแพร่แล้ว! — เซ้งร้านด่วน.com"
        preheader = f"ประกาศร้าน '{shop_title}' เปิดแสดงผลออนไลน์เรียบร้อยแล้ว"

        body = f"""
            <div style="text-align: center; margin-bottom: 20px;">
                <span class="badge badge-green">✓ อนุมัติเผยแพร่ออนไลน์</span>
            </div>
            <h2 style="margin-top:0; color:#0f172a; font-size:18px;">ประกาศของคุณขึ้นหน้าเว็บแล้ว!</h2>
            <p>สวัสดีคุณ <strong>{name}</strong>,</p>
            <p>ทีมงานได้ตรวจสอบและอนุมัติประกาศเซ้งร้านค้าของคุณเรียบร้อยแล้ว ผู้สนใจสามารถค้นหาและติดต่อคุณได้ทันที:</p>
            
            <div class="box">
                <div style="font-size:11px; color:#64748b;">รหัสทรัพย์: <strong style="color:#e11d74;">{listing.ref_code}</strong></div>
                <div style="font-size:15px; font-weight:bold; color:#0f172a; margin: 4px 0;">{shop_title}</div>
                <div style="font-size:12px; color:#64748b;">ทำเล: {listing.property.district}, {listing.property.province}</div>
                <div style="font-size:14px; font-weight:bold; color:#059669; margin-top: 6px;">ราคาเซ้ง: ฿{listing.price:,.0f}</div>
            </div>

            <div style="text-align: center; margin-top: 24px;">
                <a href="http://127.0.0.1:8000/listings/{listing.pk}/" class="btn">เปิดดูหน้าร้านของคุณ</a>
            </div>
        """

        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        return cls._send(subject=subject, html_content=html, to_emails=[owner.email])

    @classmethod
    def send_contact_inquiry_email(cls, name: str, phone: str, email: str, subject_text: str, message_text: str) -> bool:
        """
        Sends inquiry copy to admin team inbox.
        """
        admin_email = getattr(settings, 'EMAIL_HOST_USER', 'sengranduan@tchhi.online')
        subject = f"ข้อความติดต่อใหม่จากคุณ {name} ({subject_text})"
        preheader = f"มีผู้ส่งข้อความติดต่อใหม่: {name} ({phone})"

        body = f"""
            <h2 style="margin-top:0; color:#0f172a; font-size:18px;">มีข้อความติดต่อใหม่จากหน้าเว็บ</h2>
            <div class="box">
                <table width="100%" style="font-size: 13px;">
                    <tr><td style="color:#64748b; width:90px;">ผู้ติดต่อ:</td><td><strong>{name}</strong></td></tr>
                    <tr><td style="color:#64748b;">เบอร์โทร:</td><td><strong><a href="tel:{phone}" style="color:#059669;">{phone}</a></strong></td></tr>
                    <tr><td style="color:#64748b;">อีเมล:</td><td>{email or '-'}</td></tr>
                    <tr><td style="color:#64748b;">หัวข้อ:</td><td>{subject_text}</td></tr>
                </table>
                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #1e293b;">
                    <strong>ข้อความ:</strong><br>
                    {message_text}
                </div>
            </div>
        """

        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        return cls._send(subject=subject, html_content=html, to_emails=[admin_email])

    @classmethod
    def test_smtp_connection(cls, recipient_email: str) -> dict:
        """
        Utility test function to verify Hostinger SMTP credentials in real-time.
        """
        subject = "ทดสอบการเชื่อมต่อระบบอีเมล Hostinger — เซ้งร้านด่วน.com"
        preheader = "ยินดีด้วย! การเชื่อมต่อ Hostinger SMTP สำเร็จเรียบร้อยแล้ว"
        body = f"""
            <div style="text-align:center;">
                <span class="badge badge-green">✓ การเชื่อมต่อสำเร็จ (Connection OK)</span>
            </div>
            <h2 style="margin-top:16px; color:#0f172a; font-size:18px; text-align:center;">ทดสอบระบบอีเมล Hostinger SMTP</h2>
            <p>สวัสดีครับ,</p>
            <p>หากคุณได้รับอีเมลฉบับนี้ แสดงว่าระบบอีเมล <strong>Hostinger SMTP ({settings.EMAIL_HOST}:{settings.EMAIL_PORT})</strong> ผ่านบัญชี <strong>{settings.EMAIL_HOST_USER}</strong> ทำงานได้อย่างสมบูรณ์แบบแล้วครับ!</p>
            <div class="box" style="font-size:12px; font-family:monospace;">
                <div>STATUS: ACTIVE</div>
                <div>HOST: {settings.EMAIL_HOST}</div>
                <div>PORT: {settings.EMAIL_PORT} (SSL: {settings.EMAIL_USE_SSL})</div>
                <div>SENDER: {settings.DEFAULT_FROM_EMAIL}</div>
            </div>
        """
        html = cls._wrap_template(title=subject, preheader=preheader, body_html=body)
        success = cls._send(subject=subject, html_content=html, to_emails=[recipient_email])
        return {
            'success': success,
            'recipient': recipient_email,
            'sender': settings.DEFAULT_FROM_EMAIL,
            'host': settings.EMAIL_HOST,
        }
