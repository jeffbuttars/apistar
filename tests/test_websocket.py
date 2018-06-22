import json
import asyncio
from uuid import uuid4

import pytest

from apistar.utils import encode_json
from apistar import Route, test
from apistar.server.app import ASyncApp
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


def ws_run(func, *args, **kwargs):
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(func(*args, **kwargs))


def ws_setup(state=None, msgs=None):
    asgi = test.ASGIDataFaker(msgs)
    ws = WebSocket(default_scope, asgi.send, asgi.receive)

    if state:
        ws._state = state

    return (asgi, ws)


# ### WebScoket Class Tests ###
def test_bad_scope():
    asgi = test.ASGIDataFaker()

    with pytest.raises(AssertionError):
        WebSocket({}, asgi.send, asgi.receive)


def test_initial_state():
    asgi = test.ASGIDataFaker()

    ws = WebSocket(default_scope, asgi.send, asgi.receive)
    assert ws._scope == default_scope
    assert ws._asgi_send == asgi.send
    assert ws._asgi_receive == asgi.receive
    assert ws._state == WSState.CLOSED
    assert ws.closed
    assert ws.subprotocols == []


def test_connect_not_closed():
    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.connecting
    assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
    assert 'is not closed' in e.value.detail


def test_connect_not_connect():
    # Connect doesn't get a connect message
    _, ws = ws_setup(msgs=[{'type': 'websocket.receive'}])

    with pytest.raises(WebSocketProtocolError) as e:
        ws_run(ws.connect)

    assert ws.closed
    assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
    assert 'Expected WebSocket `connection` but got: websocket.receive' in e.value.detail


def test_connect_close():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True)

    assert ws.closed
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': ws_status.WS_1000_OK,
    }


def test_connect_close_with_code():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect, close=True, close_code=ws_status.WS_1001_LEAVING)

    assert ws.closed
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.close',
        'code': ws_status.WS_1001_LEAVING,
    }


def test_connect_accept():
    asgi, ws = ws_setup(msgs=[{'type': 'websocket.connect'}])

    ws_run(ws.connect)

    assert ws.connected
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

    assert ws.connected
    assert asgi.sq.get_nowait() == {'type': 'websocket.accept'}


def test_accept_not_connecting():
    for state in (WSState.CLOSED, WSState.CONNECTED):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketProtocolError) as e:
            ws_run(ws.accept)

        assert ws._state == state
        assert e.value.status_code == ws_status.WS_1002_PROT_ERROR
        assert 'Attempting to accept a WebSocket that is not connecting' in e.value.detail


def test_send_not_connected():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.closed
    assert e.value.status_code == ws_status.WS_1000_OK
    assert 'WebSocket is not connected or open' in e.value.detail

    _, ws = ws_setup(state=WSState.CONNECTING)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.send, '')

    assert ws.connecting
    assert e.value.status_code == ws_status.WS_1000_OK
    assert 'WebSocket is not connected or open' in e.value.detail


def test_send_text():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, '{"json": "message"}')

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'text':  '{"json": "message"}',
    }


def test_send_bytes():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send, b'{"json": "message"}')

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'bytes':  b'{"json": "message"}',
    }


def test_send_json():
    asgi, ws = ws_setup(state=WSState.CONNECTED)

    ws_run(ws.send_json, {"message": "payload"})

    assert ws.connected
    assert asgi.sq.get_nowait() == {
        'type': 'websocket.send',
        'text':  encode_json({"message": "payload"})
    }


def test_receive_not_connected():
    for state in (WSState.CLOSED, WSState.CONNECTING):
        _, ws = ws_setup(state=state)

        with pytest.raises(WebSocketNotConnected) as e:
            ws_run(ws.receive)

        assert ws._state == state
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

    assert ws.closed
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

    assert ws.connected
    assert resp == '{"json": "message"}'


def test_receive_bytes():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  b'{"json": "message"}',
        }])

    resp = ws_run(ws.receive)

    assert ws.connected
    assert resp == b'{"json": "message"}'


def test_receive_json():
    _, ws = ws_setup(
        state=WSState.CONNECTED,
        msgs=[{
            'type': 'websocket.receive',
            'text':  json.dumps({"message": "payload"}),
        }])

    resp = ws_run(ws.receive_json)

    assert ws.connected
    assert resp == {"message": "payload"}


def test_close_closed():
    _, ws = ws_setup(state=WSState.CLOSED)

    with pytest.raises(WebSocketNotConnected) as e:
        ws_run(ws.close)

    assert ws.closed
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

        assert ws.closed


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

            assert ws.closed


# ## Client Tests ###
async def client_connect_accept(ws: WebSocket):
    await ws.connect()
    assert ws.connected


async def client_connect_deny(ws: WebSocket):
    # Explicitly connect and close connection
    await ws.connect(close=True)
    assert ws.closed


async def client_disconnect(ws: WebSocket):
    await ws.connect()
    assert ws.connected

    with pytest.raises(WebSocketDisconnect) as e:
        await ws.receive()

    assert e.value.status_code == ws_status.WS_1001_LEAVING
    assert 'WebSocket has been disconnected' in e.value.detail
    assert ws.closed


async def client_ping_pong(ws: WebSocket):
    await ws.connect()
    assert ws.connected

    assert await ws.receive() == 'ping'

    await ws.send('pong')
    assert ws.connected

    await ws.close()
    assert ws.closed


async def client_ping_pong_kong(ws: WebSocket):
    await ws.connect()
    assert ws.connected

    assert await ws.receive() == 'ping'

    await ws.send('pong')
    assert ws.connected

    return 'kong'


async def client_ping_pong_kong_json(ws: WebSocket):
    await ws.connect()
    assert ws.connected

    assert await ws.receive_json() == {"play": "ping"}

    await ws.send_json({"play": "pong"})
    assert ws.connected

    return {"play": "kong"}

routes = [
    Route('/connect/accept/', 'GET', client_connect_accept),
    Route('/connect/deny/', 'GET', client_connect_deny),
    Route('/disconnect/', 'GET', client_disconnect),
    Route('/ping/pong/', 'GET', client_ping_pong),
    Route('/ping/pong/kong/', 'GET', client_ping_pong_kong),
    Route('/ping/pong/kong/json', 'GET', client_ping_pong_kong_json),
]


ws_headers = {
    'Upgrade': 'websocket',
    'Connection': 'upgrade',
    'Sec-WebSocket-Protocol': 'v1.test.encode.io',
}


@pytest.fixture(scope='module')
def client():
    def asgi_client(msgs: list = None):
        app = ASyncApp(routes=routes)
        asgi_faker = None

        if msgs:
            asgi_faker = test.ASGIDataFaker(msgs)

        return test.TestClient(app, scheme='ws', asgi_faker=asgi_faker), asgi_faker

    return asgi_client


def get_headers():
    headers = ws_headers.copy()
    headers['Sec-WebSocket-Key'] = uuid4().hex

    return headers


# Some basic ASGI level tests
def test_client_connect_accept(client):
    cl, _ = client()
    response = cl.get('/connect/accept/', headers=get_headers())
    message = response.text

    assert(message == '')


def test_client_connect_deny(client):
    headers = get_headers()
    cl, _ = client()

    response = cl.get('/connect/deny/', headers=headers)
    assert(response.status_code == 403)


def test_client_disconnect(client):
    headers = get_headers()

    cl, faker = client([
        {'type': 'websocket.connect'},
        {'type': 'websocket.disconnect', 'code': ws_status.WS_1001_LEAVING},
    ])
    cl.get('/disconnect/', headers=headers)


def test_client_ping_pong(client):
    headers = get_headers()

    cl, faker = client([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': 'ping'}
    ])
    cl.get('/ping/pong/', headers=headers)

    assert faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert faker.send_q.get_nowait() == {'type': 'websocket.send', 'text': 'pong'}


def test_client_ping_pong_kong(client):
    headers = get_headers()

    cl, faker = client([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': 'ping'}
    ])
    cl.get('/ping/pong/kong/', headers=headers)

    assert faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert faker.send_q.get_nowait() == {'type': 'websocket.send', 'text': 'pong'}
    assert faker.send_q.get_nowait() == {'type': 'websocket.send', 'bytes': b'kong'}


def test_client_ping_pong_kong_json(client):
    headers = get_headers()

    cl, faker = client([
        {'type': 'websocket.connect'},
        {'type': 'websocket.receive', 'text': encode_json({"play": "ping"})}
    ])
    cl.get('/ping/pong/kong/json', headers=headers)

    assert faker.send_q.get_nowait() == {'type': 'websocket.accept'}
    assert faker.send_q.get_nowait() == {
        'type': 'websocket.send',
        'text': encode_json({"play": "pong"}),
    }
    assert faker.send_q.get_nowait() == {
        'type': 'websocket.send',
        'bytes': encode_json({"play": "kong"}),
    }
