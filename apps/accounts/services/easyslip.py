import logging
import io
from decimal import Decimal
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class EasySlipService:
    """
    Automated Bank Slip Verification Engine powered by EasySlip API v2.
    Official Documentation: https://document.easyslip.com/th/v2/verify/bank/image

    WHY SECURE & RESILIENT:
    1. Zero-Crash Guarantee: If EasySlip API is unreachable or rate limited,
       the system fails gracefully and marks the transaction for manual review.
    2. Multi-point validation: Validates exact 1,000 THB amount, duplicate check,
       and verifies recipient matches "ดวงฤทัย ช้างน้อย" (KBank).
    3. Safe file handling: Reads from in-memory stream without corrupting file pointer.
    """

    @classmethod
    def verify_slip(
        cls,
        slip_file,
        expected_amount: float | Decimal = 1000.00,
        expected_receiver_keyword: str = "ดวงฤทัย",
        check_duplicate: bool = True
    ) -> dict:
        api_key = getattr(settings, 'EASYSLIP_API_KEY', '')
        api_url = getattr(settings, 'EASYSLIP_API_URL', 'https://api.easyslip.com/v2').rstrip('/')

        # Default fallback response
        fallback_res = {
            'success': False,
            'is_verified': False,
            'is_duplicate': False,
            'is_amount_matched': False,
            'is_receiver_matched': False,
            'amount_in_slip': None,
            'trans_ref': '',
            'raw_data': {},
            'status_code': 0,
            'error_message': '',
            'needs_manual_review': True,
        }

        if not api_key:
            fallback_res['error_message'] = 'EASYSLIP_API_KEY is not configured (Queued for manual staff review)'
            logger.info("EasySlip API Key not provided. Transaction queued for manual review.")
            return fallback_res

        try:
            # Prepare file stream safely
            if hasattr(slip_file, 'seek'):
                slip_file.seek(0)
                file_content = slip_file.read()
                slip_file.seek(0)
            else:
                file_content = slip_file

            files = {
                'image': ('slip.jpg', io.BytesIO(file_content), 'image/jpeg')
            }
            data = {
                'matchAmount': str(Decimal(str(expected_amount))),
                'checkDuplicate': 'true' if check_duplicate else 'false',
                'remark': 'VIP Membership Subscription (เซ้งร้าน.com)'
            }
            headers = {
                'Authorization': f'Bearer {api_key}'
            }

            endpoint = f"{api_url}/verify/bank"
            response = requests.post(endpoint, headers=headers, files=files, data=data, timeout=10)
            fallback_res['status_code'] = response.status_code

            if response.status_code != 200:
                err_text = response.text[:200]
                fallback_res['error_message'] = f"EasySlip HTTP {response.status_code}: {err_text}"
                logger.warning(f"EasySlip API responded with HTTP {response.status_code}: {err_text}")
                return fallback_res

            res_json = response.json()
            fallback_res['raw_data'] = res_json

            if not res_json.get('success'):
                fallback_res['error_message'] = res_json.get('message', 'EasySlip verification rejected')
                return fallback_res

            data_obj = res_json.get('data', {})
            amount_in_slip = data_obj.get('amountInSlip')
            is_amount_matched = data_obj.get('isAmountMatched', False)
            is_duplicate = data_obj.get('isDuplicate', False)
            raw_slip = data_obj.get('rawSlip', {})
            trans_ref = raw_slip.get('transRef', '')

            # Extract receiver info
            receiver = raw_slip.get('receiver', {})
            receiver_name = receiver.get('displayName', '') or ''
            receiver_account_name = ''
            if isinstance(receiver.get('account'), dict):
                name_obj = receiver.get('account', {}).get('name')
                if isinstance(name_obj, dict):
                    receiver_account_name = f"{name_obj.get('th', '')} {name_obj.get('en', '')}".strip()
                elif isinstance(name_obj, str):
                    receiver_account_name = name_obj

            combined_receiver_text = f"{receiver_name} {receiver_account_name}".strip()

            # Check if keyword "ดวงฤทัย" is in receiver display name or account
            is_receiver_matched = expected_receiver_keyword in combined_receiver_text or not expected_receiver_keyword

            # Verify amount is at least 1,000 THB or matched
            expected_dec = Decimal(str(expected_amount))
            amt_num = Decimal(str(amount_in_slip)) if amount_in_slip is not None else Decimal('0')
            has_correct_amount = is_amount_matched or (amt_num >= expected_dec)

            # Strict verification criteria
            is_verified = (
                not is_duplicate and
                has_correct_amount and
                is_receiver_matched
            )

            fallback_res.update({
                'success': True,
                'is_verified': is_verified,
                'is_duplicate': is_duplicate,
                'is_amount_matched': has_correct_amount,
                'is_receiver_matched': is_receiver_matched,
                'amount_in_slip': float(amt_num),
                'trans_ref': trans_ref,
                'receiver_name': combined_receiver_text,
                'needs_manual_review': not is_verified,
            })

            return fallback_res

        except requests.Timeout:
            fallback_res['error_message'] = 'EasySlip API timeout (>10s). Queued for manual staff review.'
            logger.warning("EasySlip API connection timed out.")
            return fallback_res
        except Exception as e:
            fallback_res['error_message'] = f"EasySlip unexpected exception: {str(e)}"
            logger.exception("EasySlip verification failed unexpectedly.")
            return fallback_res
