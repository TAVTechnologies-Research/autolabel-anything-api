import json
import asyncio
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from settings import settings
from db import get_redis_client


class WebSocketManager:
    def __init__(self) -> None:
        self.activate_connections: List[WebSocket] = []
        self.communication_queues: Dict[WebSocket, Dict[str, asyncio.Queue[dict]]] = (
            dict()
        )
        self.connection_locks: Dict[WebSocket, asyncio.Lock] = dict()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.activate_connections.append(websocket)
        self.communication_queues[websocket] = {
            "client": asyncio.Queue(),
            "server": asyncio.Queue(),
        }
        self.connection_locks[websocket] = asyncio.Lock()
        print("Connection established")

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.activate_connections:
            self.activate_connections.remove(websocket)
        if websocket in self.communication_queues:
            del self.communication_queues[websocket]
        if websocket in self.connection_locks:
            async with self.connection_locks[websocket]:
                if websocket.client_state == 1:
                    await websocket.close()
                    del self.connection_locks[websocket]
        print("Connection terminated")

    async def receive_message(self, websocket: WebSocket):
        try:
            while True:
                #async with self.connection_locks[websocket]:
                #    data = await websocket.receive_text()
                data = await websocket.receive_text()
                try:
                    await self.communication_queues[websocket]["client"].put(
                        json.loads(data)
                    )
                except KeyError:
                    print("Error receiving message. Connection closed.")
                    break
        except asyncio.CancelledError or WebSocketDisconnect:
            await self.disconnect(websocket)

    async def send_message(self, websocket: WebSocket):
        try:
            while True:
                try:
                    data = await self.communication_queues[websocket]["server"].get()
                except KeyError:
                    print("Error sending message. Connection closed.")
                    break
                try:
                    #async with self.connection_locks[websocket]:
                    #    await websocket.send_text(json.dumps(data))
                    to_send = json.dumps(data) if isinstance(data, dict) else data
                    await websocket.send_text(to_send)
                except RuntimeError as e:
                    print(f"Error sending message. Connection closed. {e}")
        except asyncio.CancelledError or WebSocketDisconnect:
            await self.disconnect(websocket)
