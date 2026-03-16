from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.db.models import Permission, Role, RolePermission, RoleScope


PERMISSIONS = [
    ("platform.companies.read", "List companies", RoleScope.PLATFORM),
    ("platform.companies.write", "Create/update companies", RoleScope.PLATFORM),
    ("company.users.read", "View users", RoleScope.COMPANY),
    ("company.users.write", "Create/update users", RoleScope.COMPANY),
    ("products.read", "View products", RoleScope.COMPANY),
    ("products.write", "Create/update products", RoleScope.COMPANY),
    ("masters.read", "View customers/suppliers", RoleScope.COMPANY),
    ("masters.write", "Create/update customers/suppliers", RoleScope.COMPANY),
    ("inventory.read", "View stock", RoleScope.COMPANY),
    ("inventory.adjust", "Adjust stock", RoleScope.COMPANY),
    ("sales.read", "View sales invoices", RoleScope.COMPANY),
    ("sales.write", "Create/cancel sales invoices", RoleScope.COMPANY),
    ("purchase.read", "View purchase invoices", RoleScope.COMPANY),
    ("purchase.write", "Create/cancel purchase invoices", RoleScope.COMPANY),
    ("downloads.read", "Download exports", RoleScope.COMPANY),
    ("imports.write", "Import data", RoleScope.COMPANY),
    ("settings.write", "Update company settings", RoleScope.COMPANY),
]

ROLES = [
    (RoleScope.PLATFORM, "PLATFORM_ADMIN", "Platform Admin"),
    (RoleScope.COMPANY, "SUPER_ADMIN", "Company Super Admin"),
    (RoleScope.COMPANY, "MANAGER", "Manager"),
    (RoleScope.COMPANY, "CASHIER", "Cashier"),
    (RoleScope.COMPANY, "PURCHASE", "Purchase"),
    (RoleScope.COMPANY, "AUDITOR", "Auditor"),
    (RoleScope.COMPANY, "EMPLOYEE", "Employee"),
]

ROLE_PERMISSIONS = {
    "PLATFORM_ADMIN": ["platform.companies.read", "platform.companies.write"],
    "SUPER_ADMIN": [
        "company.users.read",
        "company.users.write",
        "products.read",
        "products.write",
        "masters.read",
        "masters.write",
        "inventory.read",
        "inventory.adjust",
        "sales.read",
        "sales.write",
        "purchase.read",
        "purchase.write",
        "downloads.read",
        "imports.write",
        "settings.write",
    ],
    "MANAGER": [
        "company.users.read",
        "products.read",
        "products.write",
        "masters.read",
        "masters.write",
        "inventory.read",
        "inventory.adjust",
        "sales.read",
        "sales.write",
        "purchase.read",
        "purchase.write",
        "downloads.read",
        "imports.write",
    ],
    "CASHIER": [
        "products.read",
        "masters.read",
        "inventory.read",
        "sales.read",
        "sales.write",
        "downloads.read",
    ],
    "PURCHASE": [
        "products.read",
        "products.write",
        "masters.read",
        "masters.write",
        "inventory.read",
        "inventory.adjust",
        "purchase.read",
        "purchase.write",
    ],
    "AUDITOR": [
        "products.read",
        "masters.read",
        "inventory.read",
        "sales.read",
        "purchase.read",
        "downloads.read",
    ],
    "EMPLOYEE": [
        "products.read",
        "inventory.read",
    ],
}


def main() -> None:
    db = SessionLocal()
    try:
        permissions = {}
        for code, desc, scope in PERMISSIONS:
            perm = db.query(Permission).filter(Permission.code == code, Permission.scope == scope).first()
            if not perm:
                perm = Permission(code=code, description=desc, scope=scope)
                db.add(perm)
            permissions[(scope, code)] = perm

        roles = {}
        for scope, code, name in ROLES:
            role = db.query(Role).filter(Role.scope == scope, Role.code == code).first()
            if not role:
                role = Role(scope=scope, code=code, name=name, is_system=True)
                db.add(role)
            roles[(scope, code)] = role

        db.flush()

        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role = roles[(RoleScope.COMPANY if role_code != "PLATFORM_ADMIN" else RoleScope.PLATFORM, role_code)]
            for perm_code in perm_codes:
                scope = RoleScope.PLATFORM if perm_code.startswith("platform.") else RoleScope.COMPANY
                perm = permissions[(scope, perm_code)]
                exists = (
                    db.query(RolePermission)
                    .filter(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
                    .first()
                )
                if not exists:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
