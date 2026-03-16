from datetime import datetime

from app.security.passwords import hash_password
from app.db.models import (
    Company,
    InventoryLedger,
    Invoice,
    InvoiceType,
    Product,
    StockItem,
    User,
    UserRole,
    UserStatus,
    Role,
    RoleScope,
)


def _create_platform_admin(db_session, username="platform_admin", password="ChangeMe123!"):
    user = User(
        username=username,
        email=None,
        password_hash=hash_password(password),
        is_platform_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, username, password):
    res = client.post("/v1/auth/login", json={"username_or_email": username, "password": password})
    assert res.status_code == 200
    return res.json()["access_token"], res.json()["refresh_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_auth_login_refresh(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, refresh_token = _login(client, "platform_admin", "ChangeMe123!")

    res = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    assert res.json()["access_token"] != access_token


def test_platform_create_company_and_super_admin(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, _ = _login(client, "platform_admin", "ChangeMe123!")

    payload = {
        "name": "Acme Traders",
        "gstin": "27ABCDE1234F1Z5",
        "phone": "9876543210",
        "address": "Street 1",
        "city": "Pune",
        "state": "MH",
        "pincode": "411001",
        "seat_limit": 2,
        "plan_days": 30,
        "super_admin_username": "owner",
        "super_admin_email": "owner@acme.com",
        "super_admin_password": "Pass@1234",
    }

    res = client.post("/v1/platform/companies", json=payload, headers=_auth_headers(access_token))
    assert res.status_code == 200
    company_id = res.json()["id"]

    company = db_session.get(Company, company_id)
    assert company is not None

    super_admin = db_session.query(User).filter(User.company_id == company_id).first()
    assert super_admin is not None

    role = (
        db_session.query(Role)
        .filter(Role.scope == RoleScope.COMPANY, Role.code == "SUPER_ADMIN")
        .first()
    )
    user_role = db_session.query(UserRole).filter(UserRole.user_id == super_admin.id).first()
    assert user_role is not None
    assert user_role.role_id == role.id


def test_company_users_seat_limit_and_roles(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, _ = _login(client, "platform_admin", "ChangeMe123!")

    res = client.post(
        "/v1/platform/companies",
        json={
            "name": "Seat Check",
            "seat_limit": 1,
            "plan_days": 30,
            "super_admin_username": "owner",
            "super_admin_password": "Pass@1234",
        },
        headers=_auth_headers(access_token),
    )
    assert res.status_code == 200

    owner_access, _ = _login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/company/users",
        json={"username": "user1", "password": "Pass@1234", "role_code": "MANAGER", "allowed_modules": ["sales"]},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Seat limit reached"


def test_products_masters_inventory(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, _ = _login(client, "platform_admin", "ChangeMe123!")

    res = client.post(
        "/v1/platform/companies",
        json={
            "name": "Inventory Co",
            "seat_limit": 5,
            "plan_days": 30,
            "super_admin_username": "owner",
            "super_admin_password": "Pass@1234",
        },
        headers=_auth_headers(access_token),
    )
    assert res.status_code == 200

    owner_access, _ = _login(client, "owner", "Pass@1234")

    # Category
    res = client.post("/v1/products/categories", json={"name": "Adhesives"}, headers=_auth_headers(owner_access))
    assert res.status_code == 200
    category_id = res.json()["id"]

    # Product
    res = client.post(
        "/v1/products",
        json={
            "name": "Glue",
            "product_code": "P001",
            "category_id": category_id,
            "selling_rate": 100,
            "purchase_rate": 80,
            "unit": "pcs",
            "taxable": True,
            "tax_rate": 18,
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    product_id = res.json()["id"]

    # Customer
    res = client.post(
        "/v1/masters/customers",
        json={"name": "Rahul", "phone": "9000000000"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200

    # Supplier
    res = client.post(
        "/v1/masters/suppliers",
        json={"name": "ABC Distributors", "phone": "9111111111"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200

    # Inventory adjust
    res = client.post(
        "/v1/inventory/adjust",
        json={"product_id": product_id, "new_qty": 10, "notes": "Initial"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    assert res.json()["qty_on_hand"] == 10


def test_sales_purchase_and_cancel_flow(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, _ = _login(client, "platform_admin", "ChangeMe123!")

    res = client.post(
        "/v1/platform/companies",
        json={
            "name": "Invoice Co",
            "seat_limit": 5,
            "plan_days": 30,
            "super_admin_username": "owner",
            "super_admin_password": "Pass@1234",
        },
        headers=_auth_headers(access_token),
    )
    assert res.status_code == 200

    owner_access, _ = _login(client, "owner", "Pass@1234")

    # Product
    res = client.post(
        "/v1/products/categories",
        json={"name": "General"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    category_id = res.json()["id"]
    res = client.post(
        "/v1/products",
        json={
            "name": "Tape",
            "product_code": "T001",
            "category_id": category_id,
            "selling_rate": 100,
            "purchase_rate": 80,
            "unit": "pcs",
            "taxable": True,
            "tax_rate": 18,
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    product_id = res.json()["id"]

    # Purchase invoice (stock +10)
    res = client.post(
        "/v1/masters/suppliers",
        json={"name": "ABC Distributors", "phone": "9111111111", "gstin": "22AAAAA0000A1Z5"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    supplier_id = res.json()["id"]
    res = client.post(
        "/v1/purchase/invoices",
        json={
            "invoice_no": "P-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "supplier_id": supplier_id,
            "lines": [
                {"product_id": product_id, "description": "Tape", "qty": 10, "price": 80, "tax_rate": 18}
            ],
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200

    # Sales invoice (stock -2)
    res = client.post(
        "/v1/masters/customers",
        json={"name": "Rahul", "phone": "9000000000", "gstin": "22AAAAA0000A1Z5"},
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    customer_id = res.json()["id"]
    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "customer_id": customer_id,
            "lines": [
                {"product_id": product_id, "description": "Tape", "qty": 2, "price": 100, "tax_rate": 18}
            ],
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200
    sales_invoice_id = res.json()["id"]

    stock = (
        db_session.query(StockItem)
        .filter(StockItem.product_id == product_id)
        .first()
    )
    assert float(stock.qty_on_hand) == 8

    # Duplicate invoice number
    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-1",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "GST",
            "lines": [
                {"product_id": product_id, "description": "Tape", "qty": 1, "price": 100, "tax_rate": 18}
            ],
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 400

    # Cancel sales invoice (stock +2)
    res = client.post(
        f"/v1/sales/invoices/{sales_invoice_id}/cancel",
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 200

    db_session.expire_all()
    stock = (
        db_session.query(StockItem)
        .filter(StockItem.product_id == product_id)
        .first()
    )
    assert float(stock.qty_on_hand) == 10


def test_invalid_payment_mode(client, db_session, seed_roles):
    _create_platform_admin(db_session)
    access_token, _ = _login(client, "platform_admin", "ChangeMe123!")

    res = client.post(
        "/v1/platform/companies",
        json={
            "name": "Pay Check",
            "seat_limit": 5,
            "plan_days": 30,
            "super_admin_username": "owner",
            "super_admin_password": "Pass@1234",
        },
        headers=_auth_headers(access_token),
    )
    assert res.status_code == 200

    owner_access, _ = _login(client, "owner", "Pass@1234")

    res = client.post(
        "/v1/sales/invoices",
        json={
            "invoice_no": "S-10",
            "invoice_date": datetime.utcnow().isoformat(),
            "tax_mode": "NON_GST",
            "payment_mode": "CRYPTO",
            "lines": [
                {"description": "Service", "qty": 1, "price": 100, "tax_rate": 18}
            ],
        },
        headers=_auth_headers(owner_access),
    )
    assert res.status_code == 422
