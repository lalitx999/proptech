"""
Telegram alert delivery.

WHY:
1. Alerts carry user-typed values (LINE IDs like "@shop_for_sale", usernames, shop
   titles). An unbalanced _ or * makes Telegram reject the Markdown message with
   HTTP 400, so the alert must be resent as plain text instead of being dropped.
2. Missing credentials must be logged at WARNING so the cause is visible in
   production logs (root level WARNING).
"""
import io
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.core.services.telegram import TelegramAlertService

CREDS = ('123:test-token', '-1001234567890')
PARSE_ERROR = "Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 120"


def response(status, text=''):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


@patch.object(TelegramAlertService, 'get_credentials', classmethod(lambda cls: CREDS))
class SendAlertTests(SimpleTestCase):
    @patch('apps.core.services.telegram.requests.post')
    def test_markdown_error_is_resent_as_plain_text(self, post):
        post.side_effect = [response(400, PARSE_ERROR), response(200)]

        sent = TelegramAlertService.send_alert('💬 LINE: @shop_for_sale', event_title='🔥 ลีดใหม่')

        self.assertTrue(sent)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs['json']['parse_mode'], 'Markdown')
        retry = post.call_args_list[1].kwargs['json']
        self.assertNotIn('parse_mode', retry)
        self.assertEqual(retry['text'], '🔥 ลีดใหม่\n💬 LINE: @shop_for_sale')

    @patch('apps.core.services.telegram.requests.post')
    def test_other_errors_are_not_retried_and_are_logged(self, post):
        post.return_value = response(403, 'Forbidden: bot was kicked from the supergroup chat')

        with self.assertLogs('apps.core.services.telegram', level='WARNING') as logs:
            sent = TelegramAlertService.send_alert('ทดสอบ')

        self.assertFalse(sent)
        self.assertEqual(post.call_count, 1)
        self.assertIn('bot was kicked', logs.output[0])

    @patch('apps.core.services.telegram.requests.post')
    def test_photo_with_bad_markdown_caption_still_arrives_as_text(self, post):
        post.side_effect = [response(400, PARSE_ERROR), response(400, PARSE_ERROR), response(200)]

        sent = TelegramAlertService.send_photo('https://example.com/cover.jpg', caption='LINE: a_b', event_title='ร้านใหม่')

        self.assertTrue(sent)
        self.assertIn('/sendPhoto', post.call_args_list[0].args[0])
        self.assertNotIn('parse_mode', post.call_args_list[2].kwargs['json'])


class MissingCredentialsTests(SimpleTestCase):
    @patch('apps.core.services.telegram.requests.post')
    def test_missing_credentials_logged_at_warning(self, post):
        with self.assertLogs('apps.core.services.telegram', level='WARNING') as logs:
            sent = TelegramAlertService.send_alert('ทดสอบ', event_title='🏪 ประกาศใหม่')

        self.assertFalse(sent)
        post.assert_not_called()
        self.assertIn('not configured', logs.output[0])


class CheckTelegramCommandTests(SimpleTestCase):
    def run_command(self, *args):
        out = io.StringIO()
        call_command('check_telegram', *args, stdout=out)
        return out.getvalue()

    def test_reports_missing_credentials(self):
        self.assertIn('TELEGRAM_BOT_TOKEN', self.run_command())

    @patch.object(TelegramAlertService, 'get_credentials', classmethod(lambda cls: CREDS))
    @patch('apps.core.management.commands.check_telegram.requests.get')
    def test_reports_bot_removed_from_group(self, get):
        get.return_value.json.side_effect = [
            {'ok': True, 'result': {'id': 1, 'username': 'proptech2026_th_bot'}},
            {'ok': True, 'result': {'title': 'แจ้งเตือนอสังหา', 'type': 'supergroup'}},
            {'ok': True, 'result': {'status': 'left'}},
        ]
        out = self.run_command()
        self.assertIn('@proptech2026_th_bot', out)
        self.assertIn('status=left', out)

    @patch.object(TelegramAlertService, 'get_credentials', classmethod(lambda cls: CREDS))
    @patch('apps.core.management.commands.check_telegram.requests.get')
    def test_suggests_new_id_when_group_was_upgraded(self, get):
        get.return_value.json.side_effect = [
            {'ok': True, 'result': {'id': 1, 'username': 'proptech2026_th_bot'}},
            {'ok': False, 'description': 'Bad Request: group chat was upgraded to a supergroup chat',
             'parameters': {'migrate_to_chat_id': -1009999999999}},
        ]
        self.assertIn('TELEGRAM_CHAT_ID=-1009999999999', self.run_command())
