from fastapi import FastAPI
from dotenv import load_dotenv
from src.routes.public import health, home
from src.routes.private import data_process, diagrams, insights, ml_ready, scrapper
from src.routes.private import login
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()
api = FastAPI()

api.include_router(home.router)
api.include_router(login.router)
api.include_router(health.router)
api.include_router(diagrams.router)
api.include_router(scrapper.router)
api.include_router(insights.router)
api.include_router(ml_ready.router)
api.include_router(data_process.router)
