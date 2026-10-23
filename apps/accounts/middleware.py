import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages

class SessionIdleTimeoutMiddleware:
    """
    WHY SECURE: Enforces a strict 30-minute idle session timeout.
    Even if the browser stays open, inactivity exceeding 1800 seconds
    automatically flushes the session and logs the user out.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last_activity = request.session.get('last_activity')
            timeout = getattr(settings, 'SESSION_IDLE_TIMEOUT_SECONDS', 1800)

            if last_activity and (now - last_activity) > timeout:
                # ⚠️ Force session destruction and cycle key
                logout(request)
                request.session.flush()
                messages.warning(request, 'เซสชันของคุณหมดอายุเนื่องจากไม่มีการใช้งานเกิน 30 นาที กรุณาเข้าสู่ระบบใหม่')
                return redirect('accounts:login')

            request.session['last_activity'] = now

        return self.get_response(request)
