# Websockets

__NOTE: Using the `ASyncApp` is required for using websockets.__

Use the `WebSocket` component in a handler.

* [Basic Usage](#basic-usage)
* [Advanced Usage](#advanced-usage)
* [Event Hooks](#event-hooks)
* [More Examples](#more-examples)
* [WebSocket Object](#websocket-object)
* [WebSocket Status Codes](#websocket-status-codes)


## Basic Usage

The Basic WebSocket flow is:

1. connect with the client
2. handle the data flow
3. close the connection or handle the client closing the connection
4. perform any post processing or cleanup needed.

```python
import asyncio
from apistar import ASyncApp, Route, WebSocket
from apistar.exceptions import WebSocketDisconnect
from datetime import datetime


async def websocket_helloworld(websocket: WebSocket):
    await ws.connect()

    # Send 100 Hello World!
    for _ in range(100):
       await ws.send('Hello World!')

    await ws.close()
```

If you don't close the WebSocket in your handler it will automatically be closed after
the handler returns allowing you to ommit the `ws.close()`:

```python
async def websocket_helloworld(websocket: WebSocket):
    await ws.connect()

    # Send 100 Hello World!
    for _ in range(100):
       await ws.send('Hello World!')
```


## Event Hooks

Event hooks `on_request` and `on_response` are slightly different with WebSockets.

### on_request

`on_request` is only called during the initial connection of the WebSocket. Therefore you can only
use `on_request` with the connect phase of the WebSocket. This can be handy for doing things such as
finishing the connection on behalf of your WebSocket handlers and enforcing sub protocols on a wide
scale.

An `on_request` hook that finishes WebSocket connections for all handlers:

```python
class WebSocketEvents():
    async def on_request(self, ws: WebSocket, scope: ASGIScope):
        if scope['type'] == 'websocket':
            # Connect the WebSocket, always. Take care of that boilerplate.
            await ws.connect()
```

An `on_request` hook that rejects WebSocket connections that are not using a particular protocol
but connects those that are:

```python
from apistar.websocket import status

class WebSocketEvents():
    async def on_request(self, ws: WebSocket, scope: ASGIScope):
        if scope['type'] == 'websocket' and 'my.protocol.example.io' not in ws.protocols:
            raise WebSocketProtocolError(
                detail='Protocol %s is required' % 'my.protocol.example.io')
        else:
            await ws.connect()
```

### on_response

An `on_response` hook is called only after a WebSocket handler has returned. _It is not called for
every WebSocket message sent back to a client_. In `on_response` the WebSocket may already be closed
if the handler closed it. But if the handler has not closed it you could use `on_response` to
interact with the open WebSocket. This is not recommended except for the simplist of cases.
Perhaps you use a subprotocol that always sends the same message before it closes the WebSocket.
In that case you could use an `on_response` to help close all WebSockets:

```python
class WebSocketEvents():
    async def on_response(self, ws: WebSocket, scope: ASGIScope):
        if scope['type'] == 'websocket' and ws.connected:
            await ws.send_json({
                'status': 'ok',
                'message': 'Have a nice Day!',
            })
```

## More Examples

Easily send JSON using `send_json()`:
```python
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
```

Handling client disconnection in the handler is a matter of catching the
`WebSocketDisconnect` exception.
This sends a JSON message to the client, about once a second, until the client disconnects.

```python
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
```

```python


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

## WebSocket Object

### Attributes

WebSocket.**subprotocols**  
&nbsp;&nbsp;&nbsp;&nbsp; A list of subprotocols provided by the client's connection

WebSocket.**connected**  
&nbsp;&nbsp;&nbsp;&nbsp; Is `True` if the `WebSocket` is connected

WebSocket.**connecting**  
&nbsp;&nbsp;&nbsp;&nbsp; Is `True` if the `WebSocket` is connecting

WebSocket.**closed**  
&nbsp;&nbsp;&nbsp;&nbsp; Is `True` if the `WebSocket` is closed

WebSocket.**connect**(_subprotocol, close, close_code_) -> **None**
<div style="padding-left: 2rem;">
Called after a client initiates a connection to finish the connection
and optionaly reject the connection.
</div>  


WebSocket.**accept**()  
    async def accept(self, subprotocol: str = None) -> None:

WebSocket.**receive_json**()  
    async def receive_json(self, loads: typing.Callable = None) -> typing.Union[dict, list]:

WebSocket.**receive**()  
    async def receive(self) -> typing.Union[str, bytes]:

WebSocket.**send_msg**()  
    async def send_msg(self, msg: dict) -> None:

WebSocket.**send**()  
    async def send(self, data: typing.Union[str, bytes]) -> None:

WebSocket.**send_json**()  
    async def send_json(self,
                        data: typing.Union[dict, list],
                        dumps: typing.Callable = None) -> None:

WebSocket.**close**()  
    async def close(self, code: int = status.WS_1000_OK) -> None:

## WebSocket Status Codes
