# Websockets

__NOTE: Using the `ASyncApp` is required for using websockets.__

Use the `WebSocket` component in a handler.

```python
import asyncio
from apistar import ASyncApp, Route, WebSocket
from apistar.exceptions import WebSocketDisconnect
from datetime import datetime


# The Basic WebSocket flow is:
# 1. connect with the client
# 2. handle the data flow
# 3. close the connection or handle the client closing the connection
# 4. perform any post processing or cleanup needed.
async def websocket_helloworld(websocket: WebSocket):
    await ws.connect()

    # Send 100 Hello World!
    for _ in range(100):
       await ws.send('Hello World!')

    await ws.close()


# Easily send JSON
async def websocket_helloworld_msg(websocket: WebSocket):
    await ws.connect()

    # Send 100 Hello World! JSON messages
    for idx in range(100):
        await ws.send_json(
            {
                'index': idx,
                'text': 'Hello World!'
            }
        )

    await ws.close()

# Send a JSON message to the client, about once a second, until the client goes away.
async def websocket_helloworld_forever(websocket: WebSocket):
    await ws.connect()

    try:
        while True:
            await ws.send_json(
                {
                    'timestamp': datetime.now().isoformat(),
                    'text': 'Hello World!'
                }
            )

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        # The WebSocket was closed by the client
        pass

    # Do any needed post processing here


# Ping Pong, until the client goes away
async def websocket_pingpong_forever(websocket: WebSocket):
    await ws.connect()

    try:
        while True:
            # wait for the ping. ws.receive() will block until a message comes in.
            ping = await ws.receive()
            await ws.send('pong')
    except WebSocketDisconnect:
        pass

# Ping Pong JSON, until the client goes away
async def websocket_pingpong_forever(websocket: WebSocket):
    await ws.connect()

    try:
        while True:
            # wait for the ping. ws.receive_json() will block until a message comes in.
            ping = await ws.receive_json()
            await ws.send_json(
                {
                    'paddle': 'pong'
                }
            )
    except WebSocketDisconnect:
        pass

app = ASyncApp(
    routes=routes
)
```

