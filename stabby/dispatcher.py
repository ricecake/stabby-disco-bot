
# Make a coroutine for each websocket when it connects
# it should read off the websocket while the websocket is open, and put the message into an asyncio queue
# There should be another routine that reads from the queue, looks up the request id and passes the message as the result of the associated future
# When a thing wants to enque a request, it calls a function which generates a future, and stores it associated with the message id.
# it then finds the next websocket in the rotation and sends the message to it, and returns the future for the caller to await.

import asyncio
import dataclasses
import enum
import random
from typing import Optional
from uuid import uuid4

import websockets
from pydantic import BaseModel


from stabby import conf

config = conf.load_conf()

MessageType = enum.Enum('MessageType', [
    'GenerationRequest',
    'GenerationResponse',
])

class ServerMessage(BaseModel):
    id: str
    signature: str
    type: MessageType
    base64_image: Optional[str] = None


def parse_message(raw) -> ServerMessage:
    msg = ServerMessage.model_validate_json(raw)
    # validate the signature here
    return msg

@dataclasses.dataclass
class Dispatcher:
    _websocket: websockets.WebSocketServer
    _requests: dict[str, asyncio.Future[str]] = dict()
    _servers: dict[websockets.WebSocketServerProtocol, set[asyncio.Future[str]]] = dict()

    async def start(self) -> None:
        async def process(websocket: websockets.WebSocketServerProtocol):
            serv_set: set[asyncio.Future[str]] = set()
            self._servers[websocket] = serv_set
            try:
                async for message in websocket:
                    msg = parse_message(message)
                    req = self._requests.get(msg.id)
                    if req is not None and not req.done():
                        if msg.base64_image is not None:
                            req.set_result(msg.base64_image)
                        else:
                            req.cancel()  # exception?
            finally:
                for fut in serv_set:
                    fut.cancel()
                self._servers.pop(websocket, None)

        self._websocket = await websockets.serve(process, config.listen_host, config.listen_port)

    def request(self, req: dict) -> asyncio.Future[str]:
        id = str(uuid4())
        serv = random.choice(list(self._servers))

        def followup(fut) -> None:
            serv_set = self._servers.get(serv)
            if serv_set:
                serv_set.discard(fut)
            self._requests.pop(id, None)

        fut = asyncio.get_event_loop().create_future()
        fut.add_done_callback(followup)

        self._requests[id] = fut

        asyncio.create_task(serv.send(req))

        return fut
