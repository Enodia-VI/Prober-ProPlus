import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.dns_servers import load_dns_servers_state
from api.dns_servers import router as dns_servers_router
from api.internal import router as internal_router
from api.legacy import router as legacy_router
from api.reports import router as reports_router
from config.loader import get_config

load_dotenv() # loading the env.
os.makedirs("logs",exist_ok=True,) # logs dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/engine.log",encoding="utf-8",),logging.StreamHandler(),
    ],
)

logger = logging.getLogger("api_gateway")

# Configurazione e stato server
get_config()
load_dns_servers_state()

# FastAPI applcazione vera e propria

app = FastAPI( title="DNS Enterprise Testing Engine" )


# TODO: Da modificare per selettività, attualemnte troppo permissivo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(internal_router)
app.include_router(reports_router)
app.include_router(legacy_router)
app.include_router(dns_servers_router)

# Health API
@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Backend connesso e raggiungibile",
    }