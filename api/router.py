from fastapi import APIRouter
from app.api.routes.health import router as health_router
from app.api.routes.v1.auth import router as auth_router
from app.api.routes.v1.lookups import router as lookups_router
from app.api.routes.v1.platform import router as platform_router
from app.api.routes.v1.company import router as company_router
from app.api.routes.v1.products import router as products_router
from app.api.routes.v1.masters import router as masters_router
from app.api.routes.v1.inventory import router as inventory_router
from app.api.routes.v1.sales import router as sales_router
from app.api.routes.v1.quotations import router as quotations_router
from app.api.routes.v1.purchase import router as purchase_router
from app.api.routes.v1.downloads import router as downloads_router
from app.api.routes.v1.imports import router as imports_router
from app.api.routes.v1.accounting import router as accounting_router
from app.api.routes.v1.payments import router as payments_router
from app.api.routes.v1.reports import router as reports_router
from app.api.routes.v1.money import router as money_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(lookups_router)
api_router.include_router(platform_router)
api_router.include_router(company_router)
api_router.include_router(products_router)
api_router.include_router(masters_router)
api_router.include_router(inventory_router)
api_router.include_router(sales_router)
api_router.include_router(quotations_router)
api_router.include_router(purchase_router)
api_router.include_router(downloads_router)
api_router.include_router(imports_router)
api_router.include_router(accounting_router)
api_router.include_router(payments_router)
api_router.include_router(reports_router)
api_router.include_router(money_router)
