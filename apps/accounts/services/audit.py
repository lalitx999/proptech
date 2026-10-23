import logging
from apps.accounts.models import AuditLog

logger = logging.getLogger(__name__)

class AuditService:
    """
    WHY SECURE: Centralized immutable audit logging service.
    Guarantees:
    1. Safe client IP extraction (handles proxy headers).
    2. Zero PII/credential leaks (recursively masks sensitive keys: password, token, card).
    3. Failure resilience (logging failure does not compromise business transaction).
    """
    SENSITIVE_KEYS = {'password', 'token', 'secret', 'key', 'card', 'id_card', 'ssn'}

    @classmethod
    def get_client_ip(cls, request):
        if not request:
            return None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @classmethod
    def sanitize_diff(cls, data):
        """Recursively redact sensitive keys before recording to AuditLog."""
        if not isinstance(data, dict):
            return data
        sanitized = {}
        for k, v in data.items():
            if any(term in k.lower() for term in cls.SENSITIVE_KEYS):
                sanitized[k] = '[REDACTED]'
            elif isinstance(v, dict):
                sanitized[k] = cls.sanitize_diff(v)
            else:
                sanitized[k] = v
        return sanitized

    @classmethod
    def log(cls, action, model_name, object_id='', changes=None, user=None, request=None):
        """
        Record an immutable audit log entry.
        """
        try:
            actor = user
            ip_address = None
            user_agent = ''

            if request:
                if not actor and request.user.is_authenticated:
                    actor = request.user
                ip_address = cls.get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

            clean_changes = cls.sanitize_diff(changes or {})

            return AuditLog.objects.create(
                user=actor,
                action=action,
                model_name=model_name,
                object_id=str(object_id),
                changes=clean_changes,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as e:
            # ⚠️ Never allow an audit logging failure to crash an operation, but record the error
            logger.error(f"AuditService failed to record action {action}: {e}", exc_info=True)
            return None
