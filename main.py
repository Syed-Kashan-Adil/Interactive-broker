import nest_asyncio
nest_asyncio.apply()

from fastapi import FastAPI, Query
from ib_insync import IB, PnL, Stock, MarketOrder, StopOrder, LimitOrder, Option
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

class OrderRequest(BaseModel):
    client_id: int  # e.g., 1
    symbol: str  # Stock symbol (e.g., 'AAPL')
    exchange: str = 'SMART'  # Default exchange
    currency: str = 'USD'  # Default currency
    position_qty: int # e.g.,
    stop_price: float #
    limit_price: float # e.g.,
    tif: str = 'GTC' # e.g.,

class FlattenOrderRequest(BaseModel):
    client_id: int  # e.g., 1
    symbol: str  # Stock symbol (e.g., 'AAPL')
    exchange: str = 'SMART'  # Default exchange
    currency: str = 'USD'  # Default currency
    tif: str = 'GTC' # e.g.,


@app.post("/api/connect")
async def connect_ib(request: ConnectRequest):
    """
    Connect to the Interactive Brokers account using the specified client ID.
    """
    ib = None  # Initialize `ib` to ensure it's always defined
    try:
        async with lock:  # Use asyncio.Lock for async locking
            if (
                request.client_id in ib_connections
                and ib_connections[request.client_id].isConnected()
            ):
                accounts = await ib_connections[request.client_id].accountSummaryAsync()

                net_liquidity = None
                currency = None
                for item in accounts:
                    if item.tag == 'NetLiquidation':
                        net_liquidity = item.value
                        currency = item.currency
                        break
                return {
                    "status": True,
                    "message": "Already connected",
                    "data": {
                        "clientId": request.client_id,
                        "net_liquidity": net_liquidity,
                        "currency": currency,
                        "account_id": accounts[0].account,
                    }
                }

            # Create a new IB instance for this clientId
            ib = IB()
            ib_connections[request.client_id] = ib

        # Connect asynchronously
        await ib.connectAsync(request.host, port=request.port, clientId=request.client_id)

        if ib.isConnected():
            accounts = await ib.accountSummaryAsync()

            net_liquidity = None
            currency = None
            for item in accounts:
                if item.tag == 'NetLiquidation':
                    net_liquidity = item.value
                    currency = item.currency
                    break
                        
            print(f"IB Connection Successful with clientId: {request.client_id}")
            return {
                "status": True,
                "message": "Connected",
                "data": {
                    "clientId": request.client_id,
                    "net_liquidity": net_liquidity,
                    "currency": currency,
                    "account_id": accounts[0].account
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
    

@app.get("/api/account-detail")
async def get_accounts(client_id: int = Query(..., description="Unique client ID for the IB connection")):
    try:
        
        if client_id not in ib_connections:
            return {"status": False, "message": "No connection found for clientId", "clientId": client_id}

        ib = ib_connections[client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": client_id}

        # Fetch account summary within the current event loop
        accounts = await ib.accountSummaryAsync()
        net_liquidity = None
        currency = None
        for item in accounts:
             if item.tag == 'NetLiquidation':
                net_liquidity = item.value
                currency = item.currency
                break
        return {"status": True, "message": "Accounts retrieved successfully", "accounts": accounts,"currency": currency, "net_liquidity" : net_liquidity, "clientId": client_id}
    except Exception as e:
        print(f"Accounts Exception for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "accounts": [], "clientId": client_id}

@app.post("/api/send-order")
async def place_gtc_orders(request: OrderRequest):
    try:
        async with lock:
            if request.client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": request.client_id}

            ib = ib_connections[request.client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": request.client_id}
        
        # Step 1: Create a Contract object
        contract = Stock(request.symbol, request.exchange, request.currency)
        ib.qualifyContracts(contract)  # Ensure contract is valid
        print(f"Qualified Contract: {contract}")

        market_order = MarketOrder('BUY', request.position_qty)
        ib.placeOrder(contract, market_order)
        ib.sleep(2)
        
        # Stop-Loss Order: A StopOrder will be placed as a stop-loss GTC order
        stop_loss_order = StopOrder('SELL', abs(request.position_qty), request.stop_price) #low-forecast
        stop_loss_order.tif = request.tif  # Good-Til-Canceled
        ib.placeOrder(contract, stop_loss_order)
        print(f"Placed Stop-Loss GTC Order (StopOrder): {stop_loss_order}")
        ib.sleep(2)

        # Profit Target Order: A LimitOrder will be placed as a profit target GTC order
        profit_target_order = LimitOrder('SELL', abs(request.position_qty), request.limit_price) #high forecast
        profit_target_order.tif = request.tif  # Good-Til-Canceled
        ib.placeOrder(contract, profit_target_order)
        print(f"Placed Profit Target GTC Order (LimitOrder): {profit_target_order}")
        ib.sleep(2)

        positions = ib.reqPositions()
        symbol_position = next((pos for pos in positions if pos.contract.symbol == request.symbol), None)

        return {"status": True, "message": "Orders placed successfully", "clientId": request.client_id, "position": symbol_position}
    except Exception as e:
        print(f"Order Exception for clientId {request.client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": request.client_id}

@app.post("/api/flatten")
async def flatten_order(request: FlattenOrderRequest):
    try:
        async with lock:
            if request.client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": request.client_id}

            ib = ib_connections[request.client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": request.client_id}
        
        trades = ib.openTrades()

        symbol_trades = [trade for trade in trades if trade.contract.symbol == request.symbol]

        if not symbol_trades:
            return {
                "status": False,
                "message": f"No open trades found for symbol: {symbol}",
                "clientId": client_id
            }
        
        for trade in symbol_trades:
            try:
                ib.cancelOrder(trade.order)
            except Exception as e:
                print(f"Failed to cancel order {trade.order.orderId} for symbol {symbol}: {e}")

        contract = Stock(request.symbol, request.exchange, request.currency)
        ib.qualifyContracts(contract)  # Ensure contract is valid
        print(f"Qualified Contract: {contract}")

        # Step 2: Get positions and find the relevant position quantity
        positions = ib.reqPositions()
        position_qty = None  # Initialize position_qty variable

        for pos in positions:
            if pos.contract.symbol == request.symbol:
                position_qty = pos.position
                print(f"Found Position: {position_qty} for symbol {request.symbol}")
                break  # Stop looping once the position for the symbol is found

        if position_qty is None:
            return {"status": False, "message": f"No position found for symbol {request.symbol}", "clientId": request.client_id}

        # Step 3: Flatten the position (Close the position)
        if position_qty > 0:
            # If it's a long position, sell to flatten
            flatten_order = MarketOrder('SELL', position_qty)
        elif position_qty < 0:
            # If it's a short position, buy to flatten
            flatten_order = MarketOrder('BUY', abs(position_qty))
        else:
            # If no position exists, return an error message
            return {"status": False, "message": "No position to flatten", "clientId": request.client_id}

        # Flatten Order: Set TIF (Good-Til-Canceled)
        flatten_order.tif = request.tif
        ib.placeOrder(contract, flatten_order)
        print(f"Placed Flatten Order: {flatten_order}")

        return {"status": True, "message": "Symbol flatten successfully", "clientId": request.client_id, "position": position_qty}
    
    except Exception as e:
        print(f"Flatten Order Exception for clientId {request.client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": request.client_id}

@app.get("/api/contracts-position")
async def get_contracts_position(client_id: int = Query(..., description="Unique client ID for the IB connection")):
    try:
        async with lock:
            if client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": client_id}

            ib = ib_connections[client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": client_id}
    
        # Fetch contracts position within the current event loop
        positions = ib.reqPositions()
        return {"status": True, "message": "Contracts position retrieved successfully", "positions": positions, "clientId": client_id}
    except Exception as e:
        print(f"Flatten Order Exception for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": client_id}

@app.get("/api/orders")
async def get_orders(client_id: int = Query(..., description="Unique client ID for the IB connection")):
    try:
        async with lock:
            if client_id not in ib_connections:
                return {"status": False, "message": "No connection found for clientId", "clientId": client_id}

            ib = ib_connections[client_id]

        if not ib.isConnected():
            return {"status": False, "message": "Not connected", "clientId": client_id}

        open_trades = ib.openTrades()

        orders_with_contracts = []
        for trade in open_trades:
            order = trade.order
            contract = trade.contract

            order_data = {
                "orderId": order.orderId,
                "clientId": order.clientId,
                "permId": order.permId,
                "action": order.action,
                "totalQuantity": order.totalQuantity,
                "orderType": order.orderType,
                "lmtPrice": order.lmtPrice,
                "auxPrice": order.auxPrice,
                "tif": order.tif,
                "symbol": contract.symbol,
                "exchange": contract.exchange,
                "currency": contract.currency,
                "orderStatus": trade.orderStatus
            }
            orders_with_contracts.append(order_data)

        return {"status": True, "message": "Fetched orders successfully", "clientId": client_id, "orders": orders_with_contracts}
    except Exception as e:
        print(f"Error while fetching orders for clientId {client_id}: {e}")
        return {"status": False, "message": f"Error: {e}", "clientId": client_id}

