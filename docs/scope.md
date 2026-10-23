# PropTech Scope of Work & System Boundaries

## 1. System Scope
PropTech Monolith platform tailored for shop lease takeovers (เซ้งร้าน) and broker management:
* **Public Marketplace**:
  * Shop search & faceted filtering (by budget, monthly rent, location, transit, business category).
  * High-transparency financial cards (takeover fee, monthly rent, 3-month average revenue, profit, remaining lease).
  * PWA mobile experience (Add to Home Screen, offline shell, bottom navigation).
  * Three.js 360° Virtual Panorama Viewer (for premium listings).
* **Backoffice & Broker CRM**:
  * Zero Django Admin on production — custom role-based staff dashboard.
  * Deal Pipeline tracking (New Lead -> Site Visit -> Deposit -> Contract -> Closed Won).
  * Commission calculation engine (Split between platform & agents).
  * Secure Document Vault with permission-based access control.
  * Real-time Telegram Bot alerts on new leads and closed deals.

## 2. User Roles & Permission Hierarchy
1. **Admin**: Global administrative authority, user management, audit logs, financial reports.
2. **Staff / Broker Manager**: Listing review & approval, agent assignment, deal supervision.
3. **Agent**: Manages assigned leads, updates deal stages, uploads contract proof, views own commissions.
4. **Owner**: Submits shop listings, tracks views and inquiries, uploads shop ownership proofs.
5. **Customer / Buyer**: Browses listings, saves bookmarks, submits site visit inquiries.
