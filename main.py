from fastapi import FastAPI, Query
from ib_insync import IB
import asyncio
from typing import Dict
from threading import Lock
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific origins for better security
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Dictionary to store IB instances by clientId
ib_connections: Dict[int, IB] = {}
lock = asyncio.Lock()

class ConnectRequest(BaseModel):
    host: str  # e.g., 127.0.0.1
    port: int  # e.g., 7497
    client_id: int  # UserID

@app.post("/api/connect")
async def connect_ib(request: ConnectRequest):
    """
    Connect to the Interactive Brokers account using the specified client ID.
    """
    try:
        async with lock:  # Use asyncio.Lock for async locking
            if (
                request.client_id in ib_connections
                and ib_connections[request.client_id].isConnected()
            ):
                accounts = await ib_connections[request.client_id].accountSummaryAsync()
                return {
                    "status": True,
                    "message": "Already connected",
                    "data": {
                        "clientId": request.client_id,
                        "accounts": accounts,
                    }
                }

            # Create a new IB instance for this clientId
            ib = IB()
            ib_connections[request.client_id] = ib

        # Connect asynchronously
        await ib.connectAsync(request.host, port=request.port, clientId=request.client_id)

        if ib.isConnected():
            accounts = await ib.accountSummaryAsync()
            print(f"IB Connection Successful with clientId: {request.client_id}")
            return {
                "status": True,
                "message": "Connected",
                "data": {
                    "clientId": request.client_id,
                    "accounts": accounts,
                }
            }
        else:
            return {
                "status": False,
                "message": "Connection failed",
                "data": {
                    "clientId": request.client_id,
                }
            }
    except Exception as e:
        print(f"Connection Exception for clientId {request.client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": request.client_id}

@app.get("/api/disconnect")
async def disconnect_ib(client_id: int = Query(..., description="Unique client ID for the IB connection")):
    """
    Disconnect from the Interactive Brokers account for the specified client ID.
    """
    try:
        with lock:
            if client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": client_id}

            ib = ib_connections[client_id]

        if not ib.isConnected():
            return {"status": True, "message": "Already disconnected", "clientId": client_id}

        # Use asyncio's run_in_executor to disconnect without event loop conflict
        await asyncio.get_running_loop().run_in_executor(None, ib.disconnect)

        with lock:
            del ib_connections[client_id]

        return {"status": True, "message": "Disconnected", "clientId": client_id}
    except Exception as e:
        print(f"Disconnection Exception for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": client_id}

@app.get("/api/accounts")
async def get_accounts(client_id: int = Query(..., description="Unique client ID for the IB connection")):
    """
    Retrieve account information from Interactive Brokers for the specified client ID.
    """
    try:
        with lock:
            if client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": client_id}

            ib = ib_connections[client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": client_id}

        # Fetch account summary within the current event loop
        accounts = await ib.accountSummaryAsync()
        return {"status": True, "message": "Accounts retrieved successfully", "accounts": accounts, "clientId": client_id}
    except Exception as e:
        print(f"Accounts Exception for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "accounts": [], "clientId": client_id}
