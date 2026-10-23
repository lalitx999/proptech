# PropTech Technical Roadmap

## Sprint 1: Foundation & Security Scaffolding (COMPLETED)
- [x] Pinned `requirements.txt` with zero CVE supply-chain audit baseline.
- [x] Multi-tier settings (`base.py`, `dev.py`, `prod.py`).
- [x] Session & CSRF hardening (Argon2, Lax, HttpOnly, 30m idle timeout).
- [x] Axes brute-force defense (5 attempts/15 mins).
- [x] Dockerfile (non-root) & Docker Compose (PostgreSQL 16 + Nginx).
- [x] Automated security configuration unit tests.

## Sprint 2: Accounts, Authentication & Row-Level Authorization
- [ ] Custom `User` model with 5 roles (`admin`, `staff`, `agent`, `owner`, `customer`).
- [ ] Email verification & password reset tokens (1-hr TTL).
- [ ] 2FA (TOTP) enrollment & enforcement for admin/staff.
- [ ] Immutable `AuditLog` engine with actor, IP, UA, and JSON diff tracking.
- [ ] Base permission mixins & `@role_required` decorators.

## Sprint 3: Properties & Shop Listings Engine
- [ ] Models: `Property`, `PropertyImage`, `ShopListing`, `ListingApproval`.
- [ ] Secure upload pipeline: magic bytes MIME verification + Pillow EXIF stripper.
- [ ] Comprehensive Permission Matrix unit tests (positive & negative cases).

## Sprint 4: Public Marketplace, HTMX UI & PWA Shell
- [ ] Search & Filter endpoints with anti-DoS rate limiting.
- [ ] PWA `manifest.json` and strict non-sensitive `sw.js`.
- [ ] Three.js 360° Virtual Tour for premium listings.

## Sprint 5: Broker CRM, Deals, Telegram Bot & Go-Live
- [ ] Deal pipeline state machine.
- [ ] Automated commission calculations with PostgreSQL transactions.
- [ ] Telegram Bot webhook integration for instant team alerts.
- [ ] Legacy data migration script from old WordPress site.
