import asyncio
from uuid import uuid4
from pprint import pformat as pf

import pytest

from apistar import Route, http, test
from apistar.server.app import ASyncApp
from apistar.server.asgi import ASGIReceive, ASGIScope, ASGISend
from apistar.server.websocket import (
    WebSocket,
    WSState,
    WebSocketProtocolError,
    WebSocketNotConnected,
    WebSocketDisconnect,
    status as ws_status,
)

default_scope = {
    'type': 'websocket',
    'subprotocols': [],
}


class ws_asgi_faker():
    def __init__(self, msgs: list = None):
        self.rq = asyncio.Queue()
        self.sq = asyncio.Queue()

        if msgs:
            [self.rq.put_nowait(m) for m in msgs]

    async def receive(self):
        return await self.rq.get()

    async def send(self, msg):
        return await self.sq.put(msg)


def ws_run(func, *args, **kwargs):
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(func(*args, **kwargs))


def ws_setup(state=None, msgs=None):
    asgi = ws_asgi_faker(msgs)
    ws = WebSocket(default_scope, asgi.send, asgi.receive)

    if state:
        ws._state = state

    return (asgi, ws)


# ## WebScoket Class Tests ###
def test_bad_scope():
    asgi = ws_asgi_faker()

    with pytest.raises(AssertionError):
        WebSocket({}, asgi.send, asgi.receive)


def test_initial_state():
    asgi = ws_asgi_faker()

    ws = WebSocket(default_scope, asgi.send, asgi.receive)
    assert ws._scope == default_scope
    assert ws._asgi_send == asgi.send
    assert ws._asgi_receive == asgi.receive
    assert ws._state == WSState.CLOSED
    assert ws.state == WSState.CLOSED
    assert ws.subprotocols == []


def test_connect_not_closed():
    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.state == WSState.CONNECTING
    assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
    assert 'is not closed' in e.value.detail


def test_connect_not_connect():
    # Connect doesn't get a connect message
    _, ws = ws_setup(msgs=[{'type': 'websocket.receive'}])

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.state == WSState.CLOSED
    assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
    assert 'Expected WebSocket `connection` but got: websocket.receive' in e.value.detail


def test_connect_close():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True)

    assert ws.state == WSState.CLOSED
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': ws_status.WS_1000_OK,
    }


def test_connect_close_with_code():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True, close_code=ws_status.WS_1001_LEAVING)

    assert ws.state == WSState.CLOSED
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': ws_status.WS_1001_LEAVING,
    }


def test_connect_accept():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect)

    assert ws.state == WSState.CONNECTED
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.accept',
    }


def test_connect_accept_subprotocol():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, subprotocol='v1.test.encode.io')

    assert asgi.sq.get_nowait() == {
        'type': 'websocket.accept',
        'subprotocol': 'v1.test.encode.io',
    }


def test_accept():
    asgi, ws = ws_setup(state=WSState.CONNECTING)

    ws_run(ws.accept)

    assert ws.state == WSState.CONNECTED
    assert asgi.sq.get_nowait() == {'type': 'websocket.accept'}


def test_accept_not_connecting():
    for state in (WSState.CLOSED, WSState.CONNECTED):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketProtocolError) as e:
            ws_run(ws.accept)

        assert ws.state == state
        assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
        assert 'Attempting to accept a WebSocket that is not connecting' in e.value.detail


def test_send_not_connected():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.state == WSState.CLOSED
    assert e.value.status_code == ws_status.WS_1000_OK
    assert 'WebSocket is not connected or open' in e.value.detail

    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.state == WSState.CONNECTING
    assert e.value.status_code == ws_status.WS_1000_OK
    assert 'WebSocket is not connected or open' in e.value.detail


def test_send_text():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, '{"json": "message"}')

    assert ws.state == WSState.CONNECTED
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'text':  '{"json": "message"}',
    }


def test_send_bytes():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, b'{"json": "message"}')

    assert ws.state == WSState.CONNECTED
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'bytes':  b'{"json": "message"}',
    }


def test_receive_not_connected():
    for state in (WSState.CLOSED, WSState.CONNECTING):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketNotConnected) as e:
            ws_run(ws.receive)

        assert ws.state == state
        assert e.value.status_code == ws_status.WS_1000_OK
        assert 'WebSocket is not connected or open' in e.value.detail


def test_receive_disconnect():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.disconnect',
            'code': ws_status.WS_1001_LEAVING,
        }])

    with pytest.raises(WebSocketDisconnect) as e:
        ws_run(ws.receive)

    assert ws.state == WSState.CLOSED
    assert e.value.status_code == ws_status.WS_1001_LEAVING
    assert 'WebSocket has been disconnected' in e.value.detail


def test_receive_text():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  '{"json": "message"}',
        }])

    resp = ws_run(ws.receive)

    assert ws.state == WSState.CONNECTED
    assert resp == '{"json": "message"}'


def test_receive_bytes():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  b'{"json": "message"}',
        }])

    resp = ws_run(ws.receive)

    assert ws.state == WSState.CONNECTED
    assert resp == b'{"json": "message"}'


def test_close_closed():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.close)

    assert ws.state == WSState.CLOSED
    assert e.value.status_code == ws_status.WS_1000_OK
    assert 'WebSocket is not connected or open' in e.value.detail


def test_close():
    for state in (WSState.CONNECTED, WSState.CONNECTING):
        asgi, ws = ws_setup(state=state)

        ws_run(ws.close)
        asgi.sq.get_nowait() == {
            'type': 'websocket.close',
            'code': ws_status.WS_1000_OK,
        }

        assert ws.state == WSState.CLOSED


def test_close_codes():
    for state in (WSState.CONNECTED, WSState.CONNECTING):
        for code in (
            ws_status.WS_1000_OK,
            ws_status.WS_1001_LEAVING,
            ws_status.WS_1002_PROT_ERROR,
            ws_status.WS_1003_UNSUPPORTED_TYPE,
            ws_status.WS_1007_INALID_DATA,
            ws_status.WS_1008_POLICY_VIOLATION,
            ws_status.WS_1009_TOO_BIG,
            ws_status.WS_1010_TLS_FAIL,
        ):

            asgi, ws = ws_setup(state=state)

            ws_run(ws.close)
            asgi.sq.get_nowait() == {
                'type': 'websocket.close',
                'code': code,
            }

            assert ws.state == WSState.CLOSED


# ## Client Tests ###
async def connect_accept(receive: ASGIReceive, send: ASGISend):
    print('connect_request receiving message...', receive)
    message = await receive()
    assert(len(message.keys()) == 1)
    assert(message == {'type': 'websocket.connect'})

    print('connect_request message:', pf(message))
    await send({'type': 'websocket.accept'})

    return http.Response('')


async def connect_deny(scope: ASGIScope, receive: ASGIReceive, send: ASGISend):
    print('connect_deny receiving message...', receive)
    message = await receive()
    #  print('connect_request scope', pf(scope))
    print('connect_deny message:', pf(message))
    assert(len(message.keys()) == 1)
    assert(message == {'type': 'websocket.connect'})

    print('connect_deny sending close message:')
    await send({
        'type': 'websocket.close',
        'code': 1001,
    })


async def connect_deny_on_return(receive: ASGIReceive):
    print('connect_deny receiving message...', receive)
    message = await receive()
    #  print('connect_request scope', pf(scope))
    print('connect_deny message:', pf(message))
    assert(len(message.keys()) == 1)
    assert(message == {'type': 'websocket.connect'})

    print('connect_deny_on_return sending close message:')
    return 'Denied!'


routes = [
    Route('/connect/accept/', 'GET', connect_accept),
    Route('/connect/deny/', 'GET', connect_deny),
    Route('/connect/deny/return/', 'GET', connect_deny_on_return),
]


ws_headers = {
    'Upgrade': 'websocket',
    'Connection': 'upgrade',
    'Sec-WebSocket-Protocol': 'v1.test.encode.io',
}


@pytest.fixture(scope='module')
def client():
    app = ASyncApp(routes=routes)
    return test.TestClient(app, scheme='ws')


def get_headers(hdrs: dict = None):
    headers = ws_headers.copy()
    headers['Sec-WebSocket-Key'] = uuid4().hex

    if hdrs:
        headers.update(hdrs)

    return headers


#  def test_connect_accept(client):
#      response = client.get('/connect/accept/', headers=get_headers())
#      message = response.text
#      print('test_connect_accept', message)

#      assert(message == '')


def test_connect_deny(client):
    headers = ws_headers.copy()
    headers['Sec-WebSocket-Key'] = uuid4().hex

    response = client.get('/connect/deny/', headers=headers)
    print('test_connect_deny', response)
    print('test_connect_deny headers', response.headers)
    print('test_connect_deny content', response.content)
    assert(response.status_code == 403)
