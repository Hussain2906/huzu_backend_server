# Database Schema README

## Purpose

This document describes the actual database schema used by the backend in this repository.

Source of truth:

- `backend/db/models.py`
- `backend/db/gst_models.py`

Runtime notes:

- the backend uses SQLAlchemy models
- the default local database is SQLite: `sqlite:///./erp.db`
- schema creation is automatic on startup
- some SQLite compatibility patches are applied in `backend/db/ensure_sqlite_schema.py`

---

## Schema overview

The schema is organized into these functional areas:

- company and access control
- catalog and master data
- sales, purchases, quotations
- inventory
- payments and money entries
- accounting
- audit and system jobs
- GST support tables

Most business tables are company-scoped through a `company_id` column.

Primary keys are UUID strings in almost all tables.

---

## Enum values used in the schema

### Company status

- `ACTIVE`
- `SUSPENDED`
- `INACTIVE`

### User status

- `ACTIVE`
- `INACTIVE`
- `LOCKED`

### Invoice type

- `SALES`
- `PURCHASE`

### Tax mode

- `GST`
- `NON_GST`

### Invoice status

- `DRAFT`
- `POSTED`
- `CANCELLED`

### Stock reason

- `SALE`
- `PURCHASE`
- `ADJUSTMENT`
- `CANCEL`
- `RETURN`

### Payment mode

- `CASH`
- `CARD`
- `CHEQUE`
- `BANK_TRANSFER`
- `UPI`
- `OTHER`

### Money direction

- `IN`
- `OUT`

### Quotation status

- `DRAFT`
- `SENT`
- `CONFIRMED`
- `CANCELLED`
- `CONVERTED`

### Quotation line type

- `PRODUCT`
- `DESCRIPTION`

### Quotation party type

- `CUSTOMER`
- `SUPPLIER`

### Ledger type

- `ASSET`
- `LIABILITY`
- `EQUITY`
- `INCOME`
- `EXPENSE`

### Role scope

- `PLATFORM`
- `COMPANY`

### GST period status

- `OPEN`
- `LOCKED`
- `FILED`

---

## Relationship map

High-level relationships:

- one `Company` has many `User`
- one `Company` has many `ProductCategory`
- one `Company` has many `Product`
- one `Company` has many `Customer`
- one `Company` has many `Supplier`
- one `Company` has many `Invoice`
- one `Invoice` has many `InvoiceLine`
- one `Company` has many `Quotation`
- one `Quotation` has many `QuotationLine`
- one `Company` has many `StockItem`
- one `Company` has many `InventoryLedger` rows
- one `Company` has many `Payment`
- one `Payment` has many `PaymentAllocation`
- one `Company` has many `MoneyEntry`
- one `Company` has many `Ledger`
- one `Company` has many `JournalVoucher`
- one `JournalVoucher` has many `JournalLine`
- one `User` can have many `UserRole`
- one `Role` can have many `RolePermission`

---

## Company and access-control tables

## `companies`

Main tenant table.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `name` | `String(200)` | required |
| `status` | `Enum(CompanyStatus)` | default `ACTIVE` |
| `gstin` | `String(20)` | nullable |
| `phone` | `String(20)` | nullable |
| `address` | `String(255)` | nullable |
| `city` | `String(100)` | nullable |
| `state` | `String(100)` | nullable |
| `pincode` | `String(10)` | nullable |
| `seat_limit` | `Integer` | default `1` |
| `plan_expiry_at` | `DateTime` | nullable |
| `enforce_single_manager` | `Boolean` | default `False` |
| `enforce_single_cashier` | `Boolean` | default `False` |
| `created_at` | `DateTime` | default now |
| `updated_at` | `DateTime` | default now |

## `company_profiles`

Extended editable profile data for a company.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id`, unique |
| `business_name` | `String(200)` | required |
| `gst_number` | `String(20)` | nullable |
| `phone` | `String(20)` | nullable |
| `address` | `String(255)` | nullable |
| `state` | `String(100)` | nullable |
| `created_at` | `DateTime` | default now |
| `updated_at` | `DateTime` | default now |

## `users`

All authenticated people, including company users and platform admins.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id`, nullable for platform admins |
| `username` | `String(50)` | unique |
| `email` | `String(255)` | nullable |
| `password_hash` | `String(255)` | required |
| `full_name` | `String(120)` | nullable |
| `phone` | `String(20)` | nullable |
| `role_label` | `String(80)` | nullable |
| `allowed_modules` | `JSON` | nullable; permission list used by frontend |
| `is_platform_admin` | `Boolean` | default `False` |
| `status` | `Enum(UserStatus)` | default `ACTIVE` |
| `created_at` | `DateTime` | default now |
| `last_seen_at` | `DateTime` | nullable |

## `roles`

System role definitions.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `scope` | `Enum(RoleScope)` | `PLATFORM` or `COMPANY` |
| `code` | `String(50)` | unique within scope |
| `name` | `String(100)` | required |
| `is_system` | `Boolean` | default `True` |

Unique constraint:

- `uq_roles_scope_code` on `(scope, code)`

## `permissions`

Permission definitions.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `scope` | `Enum(RoleScope)` | platform/company |
| `code` | `String(100)` | permission code |
| `description` | `String(255)` | nullable |

Unique constraint:

- `uq_permissions_scope_code` on `(scope, code)`

## `user_roles`

Join table between users and roles.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `user_id` | `String(36)` | FK -> `users.id` |
| `role_id` | `String(36)` | FK -> `roles.id` |

Unique constraint:

- `uq_user_roles` on `(user_id, role_id)`

## `role_permissions`

Join table between roles and permissions.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `role_id` | `String(36)` | FK -> `roles.id` |
| `permission_id` | `String(36)` | FK -> `permissions.id` |

Unique constraint:

- `uq_role_permissions` on `(role_id, permission_id)`

## `company_permission_overrides`

Per-company permission override table.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `role_id` | `String(36)` | FK -> `roles.id` |
| `permission_id` | `String(36)` | FK -> `permissions.id` |
| `allowed` | `Boolean` | default `True` |

Unique constraint:

- `uq_company_permission_overrides` on `(company_id, role_id, permission_id)`

## `auth_sessions`

Refresh-token session storage.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `user_id` | `String(36)` | FK -> `users.id` |
| `refresh_token_hash` | `String(255)` | hashed refresh token |
| `expires_at` | `DateTime` | required |
| `revoked_at` | `DateTime` | nullable |
| `created_at` | `DateTime` | default now |

---

## Catalog and master data tables

## `product_categories`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `name` | `String(120)` | required |
| `status` | `String(20)` | default `ACTIVE` |
| `created_at` | `DateTime` | default now |

Unique constraint:

- `uq_category_company_name` on `(company_id, name)`

## `products`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `category_id` | `String(36)` | FK -> `product_categories.id`, nullable |
| `name` | `String(200)` | required |
| `product_code` | `String(60)` | nullable, unique per company if present |
| `hsn` | `String(20)` | nullable |
| `selling_rate` | `Numeric(12,2)` | nullable |
| `purchase_rate` | `Numeric(12,2)` | nullable |
| `unit` | `String(20)` | nullable |
| `taxable` | `Boolean` | default `True` |
| `tax_rate` | `Numeric(5,2)` | nullable |
| `reorder_level` | `Numeric(12,3)` | nullable |
| `status` | `String(20)` | default `ACTIVE` |
| `created_at` | `DateTime` | default now |
| `updated_at` | `DateTime` | default now |

Unique constraint:

- `uq_products_company_code` on `(company_id, product_code)`

## `customers`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `name` | `String(200)` | required |
| `phone` | `String(20)` | nullable |
| `gstin` | `String(20)` | nullable |
| `address` | `String(255)` | nullable |
| `customer_type` | `String(50)` | nullable |
| `status` | `String(20)` | default `ACTIVE` |
| `created_at` | `DateTime` | default now |

## `suppliers`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `name` | `String(200)` | required |
| `business_name` | `String(200)` | nullable |
| `phone` | `String(20)` | nullable |
| `email` | `String(255)` | nullable |
| `gstin` | `String(20)` | nullable |
| `gst_registration_type` | `String(60)` | nullable |
| `gst_state` | `String(80)` | nullable |
| `address` | `String(255)` | nullable |
| `address_line1` | `String(255)` | nullable |
| `address_line2` | `String(255)` | nullable |
| `city` | `String(80)` | nullable |
| `state` | `String(80)` | nullable |
| `pincode` | `String(12)` | nullable |
| `status` | `String(20)` | default `ACTIVE` |
| `created_at` | `DateTime` | default now |

---

## Sales and purchase tables

## `invoices`

This table stores both sales and purchase invoices.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `invoice_type` | `Enum(InvoiceType)` | `SALES` or `PURCHASE` |
| `tax_mode` | `Enum(TaxMode)` | `GST` or `NON_GST` |
| `status` | `Enum(InvoiceStatus)` | default `POSTED` |
| `invoice_no` | `String(60)` | required |
| `invoice_date` | `DateTime` | required |
| `voucher_id` | `String(36)` | FK -> `journal_vouchers.id`, nullable |
| `paid_amount` | `Numeric(12,2)` | default `0` |
| `balance_due` | `Numeric(12,2)` | default `0` |
| `customer_id` | `String(36)` | FK -> `customers.id`, nullable |
| `supplier_id` | `String(36)` | FK -> `suppliers.id`, nullable |
| `source_quotation_id` | `String(36)` | FK -> `quotations.id`, nullable |
| `source_quotation_no` | `String(60)` | nullable |
| `subtotal` | `Numeric(12,2)` | default `0` |
| `tax_total` | `Numeric(12,2)` | default `0` |
| `round_off` | `Numeric(12,2)` | default `0` |
| `grand_total` | `Numeric(12,2)` | default `0` |
| `cgst_rate` | `Numeric(5,2)` | nullable |
| `sgst_rate` | `Numeric(5,2)` | nullable |
| `igst_rate` | `Numeric(5,2)` | nullable |
| `cgst_amount` | `Numeric(12,2)` | nullable |
| `sgst_amount` | `Numeric(12,2)` | nullable |
| `igst_amount` | `Numeric(12,2)` | nullable |
| `payment_mode` | `Enum(PaymentMode)` | nullable |
| `payment_reference` | `String(100)` | nullable |
| `customer_snapshot_json` | `JSON` | nullable |
| `supplier_snapshot_json` | `JSON` | nullable |
| `company_snapshot_json` | `JSON` | nullable |
| `created_by` | `String(36)` | FK -> `users.id` |
| `cancelled_by` | `String(36)` | FK -> `users.id`, nullable |
| `cancelled_at` | `DateTime` | nullable |
| `created_at` | `DateTime` | default now |
| `updated_at` | `DateTime` | default now |

Unique constraint:

- `uq_company_invoice_no` on `(company_id, invoice_type, invoice_no)`

## `invoice_lines`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `invoice_id` | `String(36)` | FK -> `invoices.id` |
| `product_id` | `String(36)` | FK -> `products.id`, nullable |
| `description` | `String(255)` | required |
| `hsn` | `String(20)` | nullable |
| `qty` | `Numeric(12,3)` | default `0` |
| `unit` | `String(20)` | nullable |
| `price` | `Numeric(12,2)` | default `0` |
| `discount_percent` | `Numeric(5,2)` | default `0` |
| `taxable` | `Boolean` | default `True` |
| `tax_rate` | `Numeric(5,2)` | nullable |
| `line_total` | `Numeric(12,2)` | default `0` |
| `tax_amount` | `Numeric(12,2)` | default `0` |

---

## Quotation tables

## `quotations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `quotation_no` | `String(60)` | required |
| `quotation_date` | `DateTime` | default now |
| `valid_until` | `DateTime` | nullable |
| `status` | `Enum(QuotationStatus)` | default `DRAFT` |
| `party_type` | `Enum(QuotationPartyType)` | default `CUSTOMER` |
| `customer_id` | `String(36)` | FK -> `customers.id`, nullable |
| `customer_snapshot_json` | `JSON` | nullable |
| `supplier_id` | `String(36)` | FK -> `suppliers.id`, nullable |
| `supplier_snapshot_json` | `JSON` | nullable |
| `company_snapshot_json` | `JSON` | nullable |
| `salesperson` | `String(120)` | nullable |
| `notes` | `Text` | nullable |
| `terms` | `Text` | nullable |
| `revision_of_id` | `String(36)` | FK -> `quotations.id`, nullable |
| `revision_no` | `Integer` | default `1` |
| `subtotal` | `Numeric(12,2)` | default `0` |
| `grand_total` | `Numeric(12,2)` | default `0` |
| `converted_invoice_id` | `String(36)` | FK -> `invoices.id`, nullable |
| `converted_at` | `DateTime` | nullable |
| `created_by` | `String(36)` | FK -> `users.id` |
| `created_at` | `DateTime` | default now |
| `updated_at` | `DateTime` | default now |

Unique constraint:

- `uq_company_quotation_no` on `(company_id, quotation_no)`

## `quotation_lines`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `quotation_id` | `String(36)` | FK -> `quotations.id` |
| `line_type` | `Enum(QuotationLineType)` | `PRODUCT` or `DESCRIPTION` |
| `line_order` | `Integer` | default `0` |
| `product_id` | `String(36)` | FK -> `products.id`, nullable |
| `description` | `String(255)` | required |
| `qty` | `Numeric(12,3)` | default `0` |
| `unit` | `String(20)` | nullable |
| `price` | `Numeric(12,2)` | default `0` |
| `discount_percent` | `Numeric(5,2)` | default `0` |
| `line_total` | `Numeric(12,2)` | default `0` |

SQLite migration note:

- `line_order` is explicitly backfilled in `ensure_sqlite_schema.py`

---

## Inventory tables

## `stock_items`

Current on-hand stock per product.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `product_id` | `String(36)` | FK -> `products.id` |
| `qty_on_hand` | `Numeric(12,3)` | default `0` |
| `updated_at` | `DateTime` | default now |

Unique constraint:

- `uq_company_product_stock` on `(company_id, product_id)`

## `inventory_ledger`

Stock movement history.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `product_id` | `String(36)` | FK -> `products.id` |
| `qty_change` | `Numeric(12,3)` | positive or negative |
| `reason` | `Enum(StockReason)` | sale, purchase, adjustment, cancel, return |
| `ref_type` | `String(50)` | nullable |
| `ref_id` | `String(36)` | nullable |
| `notes` | `String(255)` | nullable |
| `created_by` | `String(36)` | FK -> `users.id` |
| `created_at` | `DateTime` | default now |

---

## Payment and cashflow tables

## `payments`

Generic payment register.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `counterparty_type` | `String(20)` | customer/supplier/other |
| `counterparty_id` | `String(36)` | nullable |
| `mode` | `Enum(PaymentMode)` | required |
| `amount` | `Numeric(14,2)` | required |
| `currency` | `String(10)` | default `INR` |
| `ref_no` | `String(60)` | nullable |
| `ref_date` | `DateTime` | nullable |
| `notes` | `String(255)` | nullable |
| `status` | `String(20)` | default `POSTED` |
| `created_at` | `DateTime` | default now |

## `payment_allocations`

Link payments to invoices.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `payment_id` | `String(36)` | FK -> `payments.id` |
| `invoice_id` | `String(36)` | FK -> `invoices.id` |
| `amount_applied` | `Numeric(14,2)` | required |

## `money_entries`

Ad hoc inflow and outflow register.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `direction` | `Enum(MoneyDirection)` | `IN` or `OUT` |
| `amount` | `Numeric(14,2)` | required |
| `currency` | `String(10)` | default `INR` |
| `entry_date` | `DateTime` | default now |
| `mode` | `Enum(PaymentMode)` | required |
| `reference` | `String(60)` | nullable |
| `notes` | `String(255)` | nullable |
| `category` | `String(100)` | nullable |
| `voucher_id` | `String(36)` | FK -> `journal_vouchers.id`, nullable |
| `created_at` | `DateTime` | default now |

---

## Accounting tables

## `chart_of_accounts`

Stored as model `Ledger`.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `code` | `String(50)` | required |
| `name` | `String(200)` | required |
| `type` | `Enum(LedgerType)` | required |
| `parent_id` | `String(36)` | self-FK to `chart_of_accounts.id`, nullable |
| `is_bank` | `Boolean` | default `False` |
| `status` | `String(20)` | default `ACTIVE` |

Unique constraint:

- `uq_coa_code_company` on `(company_id, code)`

## `journal_vouchers`

Accounting voucher header.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `voucher_type` | `String(50)` | sales, purchase, receipt, payment, contra, journal, etc. |
| `number` | `String(60)` | required |
| `date` | `DateTime` | default now |
| `ref_type` | `String(50)` | nullable |
| `ref_id` | `String(36)` | nullable |
| `narration` | `String(255)` | nullable |
| `status` | `String(20)` | default `POSTED` |
| `created_by` | `String(36)` | FK -> `users.id`, nullable |
| `approved_by` | `String(36)` | FK -> `users.id`, nullable |
| `approved_at` | `DateTime` | nullable |

Unique constraint:

- `uq_voucher_number_company` on `(company_id, number)`

## `journal_lines`

Accounting voucher lines.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `voucher_id` | `String(36)` | FK -> `journal_vouchers.id` |
| `ledger_id` | `String(36)` | FK -> `chart_of_accounts.id` |
| `dr` | `Numeric(14,2)` | default `0` |
| `cr` | `Numeric(14,2)` | default `0` |
| `line_ref` | `String(100)` | nullable |

---

## System and audit tables

## `audit_logs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id`, nullable |
| `actor_id` | `String(36)` | FK -> `users.id` |
| `action` | `String(100)` | required |
| `ref_type` | `String(50)` | nullable |
| `ref_id` | `String(36)` | nullable |
| `details_json` | `JSON` | nullable |
| `created_at` | `DateTime` | default now |

## `notifications`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `user_id` | `String(36)` | FK -> `users.id`, nullable |
| `title` | `String(120)` | required |
| `body` | `Text` | required |
| `read_at` | `DateTime` | nullable |
| `created_at` | `DateTime` | default now |

## `download_jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `job_type` | `String(50)` | required |
| `status` | `String(20)` | default `PENDING` |
| `filters_json` | `JSON` | nullable |
| `result_path` | `String(255)` | nullable |
| `created_by` | `String(36)` | FK -> `users.id` |
| `created_at` | `DateTime` | default now |

## `import_jobs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `job_type` | `String(50)` | required |
| `status` | `String(20)` | default `PENDING` |
| `source_path` | `String(255)` | nullable |
| `result_json` | `JSON` | nullable |
| `created_by` | `String(36)` | FK -> `users.id` |
| `created_at` | `DateTime` | default now |

---

## GST-specific tables

These are registered through `backend/db/gst_models.py`.

## `gst_periods`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `period` | `String(10)` | format `YYYY-MM` |
| `status` | `Enum(GstrPeriodStatus)` | default `OPEN` |
| `created_at` | `DateTime` | default now |

## `gstr1_docs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `invoice_id` | `String(36)` | FK -> `invoices.id`, nullable |
| `section` | `String(20)` | B2B/B2C/EXP/SEZ style bucket |
| `payload` | `JSON` | nullable |
| `status` | `String(20)` | default `DRAFT` |
| `ack_no` | `String(50)` | nullable |
| `created_at` | `DateTime` | default now |

## `gstr2b_lines`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `String(36)` | PK |
| `company_id` | `String(36)` | FK -> `companies.id` |
| `supplier_gstin` | `String(20)` | required |
| `doc_no` | `String(60)` | required |
| `doc_date` | `DateTime` | required |
| `taxable_value` | `Numeric(12,2)` | required |
| `tax_value` | `Numeric(12,2)` | required |
| `igst` | `Numeric(12,2)` | nullable |
| `cgst` | `Numeric(12,2)` | nullable |
| `sgst` | `Numeric(12,2)` | nullable |
| `cess` | `Numeric(12,2)` | nullable |
| `match_status` | `String(20)` | default `UNMATCHED` |
| `match_ref_invoice_id` | `String(36)` | FK -> `invoices.id`, nullable |
| `created_at` | `DateTime` | default now |

---

## Important uniqueness constraints

These are the main uniqueness rules enforced in the schema:

- `roles(scope, code)`
- `permissions(scope, code)`
- `user_roles(user_id, role_id)`
- `role_permissions(role_id, permission_id)`
- `company_permission_overrides(company_id, role_id, permission_id)`
- `product_categories(company_id, name)`
- `products(company_id, product_code)`
- `chart_of_accounts(company_id, code)`
- `journal_vouchers(company_id, number)`
- `stock_items(company_id, product_id)`
- `invoices(company_id, invoice_type, invoice_no)`
- `quotations(company_id, quotation_no)`
- `company_profiles(company_id)` through unique `company_id`
- `users.username` globally

---

## Important denormalized snapshot fields

Several transactional tables store JSON snapshots so documents remain stable even if master data changes later.

Snapshot columns:

- `invoices.customer_snapshot_json`
- `invoices.supplier_snapshot_json`
- `invoices.company_snapshot_json`
- `quotations.customer_snapshot_json`
- `quotations.supplier_snapshot_json`
- `quotations.company_snapshot_json`

This means:

- invoice/quotation rendering does not need to fully depend on current master data
- historical document identity can survive later edits to customer, supplier, or company records

---

## Important derived behavior tied to the schema

Although this document is about schema, some tables are tightly tied to backend behavior:

- `invoices` + `invoice_lines` drive stock and accounting side effects
- `stock_items` is the current quantity snapshot
- `inventory_ledger` is the historical movement trail
- `journal_vouchers` + `journal_lines` hold the accounting impact of invoices, money entries, and allocations
- `payment_allocations` updates invoice paid/balance state
- `auth_sessions` powers refresh-token rotation

---

## Recommended frontend mental model

If you are rebuilding the frontend, use these main entity groups in your data model:

- tenant and identity:
  - company
  - company profile
  - users
  - roles
- master data:
  - categories
  - products
  - customers
  - suppliers
- transactions:
  - invoices
  - invoice lines
  - quotations
  - quotation lines
  - payments
  - money entries
- operations:
  - stock items
  - stock moves
- finance:
  - ledgers
  - vouchers
  - voucher lines

---

## File references

- [models.py](/Volumes/Husayn(D)/telegram_bot/ERP-React-Native/backend/db/models.py)
- [gst_models.py](/Volumes/Husayn(D)/telegram_bot/ERP-React-Native/backend/db/gst_models.py)
- [ensure_sqlite_schema.py](/Volumes/Husayn(D)/telegram_bot/ERP-React-Native/backend/db/ensure_sqlite_schema.py)
