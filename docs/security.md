# PropTech Security Architecture & Compliance Document

## 1. Threat Modeling & OWASP Top 10 Mitigation Matrix

| OWASP Top 10 (2021) | Threat Description | PropTech Mitigation Control | Implementation Details |
| :--- | :--- | :--- | :--- |
| **A01: Broken Access Control** | Privilege escalation, IDOR / parameter tampering on properties & listings | Row-level authorization, `get_queryset()` overriding, `@role_required` decorators | Every object access verifies `user == obj.owner` or assigned agent. Raw PK in URL is never trusted. |
| **A02: Cryptographic Failures** | Credential stuffing, weak password hash cracking | Argon2 password hasher, strict TLS 1.2+, HSTS Preload (1 year) | `Argon2PasswordHasher` as primary hasher. Password reset tokens expire in 1 hr. |
| **A03: Injection** | SQL Injection, XSS, Template injection | Django ORM parameterized queries, Nonce-based CSP, Bleach sanitization | Strict CSP with script nonces. `autoescape=True` enforced. Zero raw SQL with string interpolation. |
| **A04: Insecure Design** | Brute force login, session hijacking | `django-axes` throttling (5 attempts/15 min), 30-min idle timeout | `SessionIdleTimeoutMiddleware` flushes session on 1800s inactivity. 2FA (TOTP) mandatory for staff/admin. |
| **A05: Security Misconfiguration** | Debug mode on prod, exposed admin panel | `DEBUG=False`, zero Django Admin in production routing | `django.contrib.admin` omitted from `INSTALLED_APPS` and URL conf in `config.settings.prod`. |
| **A06: Vulnerable Components** | Outdated libraries with known CVEs | Pinned dependencies, regular `pip-audit` runs | All dependencies strictly pinned in `requirements.txt`. |
| **A07: Identification & Auth Failures** | Session fixation, credential reuse | Cookie `HttpOnly=True`, `SameSite=Lax`, `Secure=True`, Session rotation on logout | Session key rotated on privilege change and cleared on logout. |
| **A08: Software & Data Integrity** | Malicious file upload (RCE / webshell) | MIME magic bytes inspection, EXIF stripping via Pillow, UUID filenames | Filenames renamed to `uuid4()`. User-supplied extensions never trusted. |
| **A09: Security Logging Failures** | Undetected breaches, lack of audit trail | `AuditLog` table, structured rotating log files, Sentry error monitoring | Sensitive models log all mutations with Actor, IP, UA, and JSON diff. Logs retained >= 90 days. |
| **A10: Server-Side Request Forgery** | Attacker probes internal cloud metadata | Strict URL validation, no unverified outbound HTTP requests | Any webhook or external URL is strictly checked against private IP ranges. |

---

## 2. Media Vault Architecture (Private Documents)
Sensitive documents (takeover contracts, lease agreements, government IDs, deposit payment slips) are stored in `media/private/` and served via **Nginx `X-Accel-Redirect`**.
* Direct HTTP requests to `/internal-media/*` return `404 Not Found` immediately at the Nginx layer.
* Downloads are only permitted after Django checks user permissions and issues an internal redirect header.
