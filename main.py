from fastapi import FastAPI, Query
from ib_insync import IB
import asyncio
from typing import Dict
from threading import Lock

app = FastAPI()

# Dictionary to store IB instances by clientId
ib_connections: Dict[int, IB] = {}
lock = Lock()  # To ensure thread-safe access to the dictionary

@app.get("/connect")
async def connect_ib(
    host: str = Query(..., description="e.g 127.0.0.1"),
    port: int = Query(..., description="e.g 7497"),
    client_id: int = Query(..., description="UserID")):
    """
    Connect to the Interactive Brokers account using the specified client ID.
    """
    try:
        with lock:
            if client_id in ib_connections and ib_connections[client_id].isConnected():
                accounts = await ib_connections[client_id].accountSummaryAsync()
                return {"status": True, "message": "Already connected", "clientId": client_id, 'accounts': accounts}

            # Create a new IB instance for this clientId
            ib = IB()
            ib_connections[client_id] = ib

        # Use asyncio's run_in_executor to avoid event loop conflict
        await ib.connectAsync(host, port=port, clientId=client_id)

        if ib.isConnected():
            accounts = await ib.accountSummaryAsync()
            print(f"IB Connection Successful with clientId: {client_id}")
            return {"status": True, "message": "Connected", "clientId": client_id, 'accounts': accounts}
        else:
            return {"status": False, "message": "Connection failed", "clientId": client_id}
    except Exception as e:
        print(f"Connection Exception for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": client_id}

@app.get("/disconnect")
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

@app.get("/accounts")
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
