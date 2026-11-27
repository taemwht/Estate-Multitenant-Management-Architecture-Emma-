from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import (
    auth, rental_units, tenants, leases, rent_receipts, security_deposits,
    contractors, maintenance_requests, contractor_payments, annual_checkins,
    signup, bulk_import, dashboard, users, companies,
)
from .scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Property Platform API", version="0.1.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Actor-Type"],
    )

app.include_router(users.router)
app.include_router(companies.router)
app.include_router(auth.router)
app.include_router(signup.router)
app.include_router(bulk_import.router)
app.include_router(dashboard.router)
app.include_router(rental_units.router)
app.include_router(tenants.router)
app.include_router(leases.router)
app.include_router(rent_receipts.router)
app.include_router(security_deposits.router)
app.include_router(contractors.router)
app.include_router(maintenance_requests.router)
app.include_router(contractor_payments.router)
app.include_router(annual_checkins.router)


@app.get("/health")
def health():
    return {"status": "ok"}
