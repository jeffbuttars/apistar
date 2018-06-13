from uuid import uuid4
from pprint import pformat as pf

import pytest

from apistar import Route, http, test
from apistar.server.app import ASyncApp
from apistar.server.asgi import ASGIReceive, ASGIScope, ASGISend


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
