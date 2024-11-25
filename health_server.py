# health_server.py

from fastapi import FastAPI
import config
#want uptime
from datetime import datetime

app = FastAPI()

@app.get("/health")
async def health_check():
    uptime = datetime.now() - config.start_time
    return {
        "status": "UP",
        "uptime": str(uptime),
        "auth_log": config.auth_log, 
        "duo_auth_counter": config.duo_auth_counter,  
        "cas_auth_counter": config.cas_auth_counter  
    }
