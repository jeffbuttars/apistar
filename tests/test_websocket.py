from uuid import uuid4
from pprint import pformat as pf

import pytest

from apistar import Route, http, test
from apistar.server.app import ASyncApp
from apistar.server.asgi import ASGIReceive, ASGIScope, ASGISend


async def connect_request(scope: ASGIScope, receive: ASGIReceive):
    print('connect_request scope', pf(scope))
    message = await receive()
    print('connect_request message', pf(message))
    return message


routes = [
    Route('/connect/', 'GET', connect_request),
    #  Route('/method/', 'GET', get_method),
    #  Route('/scheme/', 'GET', get_scheme),
    #  Route('/host/', 'GET', get_host),
    #  Route('/port/', 'GET', get_port),
    #  Route('/path/', 'GET', get_path),
    #  Route('/query_string/', 'GET', get_query_string),
    #  Route('/query_params/', 'GET', get_query_params),
    #  Route('/page_query_param/', 'GET', get_page_query_param),
    #  Route('/url/', 'GET', get_url),
    #  Route('/headers/', 'GET', get_headers),
    #  Route('/accept_header/', 'GET', get_accept_header),
    #  Route('/missing_header/', 'GET', get_missing_header),
    #  Route('/path_params/{example}/', 'GET', get_path_params),
    #  Route('/full_path_params/{+example}', 'GET', get_path_params, name='full_path_params'),
    #  Route('/return_string/', 'GET', return_string),
    #  Route('/return_data/', 'GET', return_data),
    #  Route('/return_response/', 'GET', return_response),
]


ws_headers = {
    'Upgrade': 'websocket',
    'Connection': 'upgrade',
}


@pytest.fixture(scope='module')
def client(request):
    app = ASyncApp(routes=routes)
    return test.TestClient(app, scheme='ws')


def test_connect(client):
    headers = ws_headers.copy()
    headers['Sec-WebSocket-Key'] = uuid4().hex
    headers['Sec-WebSocket-Protocol'] = 'v1.test.encode.io'

    response = client.get('/connect/', headers=headers)
    message = response.json()
    #  print('RESPONSE:', response, dir(response))
    #  print('RESPONSE req:', response.request, response.request.headers)
    #  print('RESPONSE head:', response.headers)
    #  print('RESPONSE conn:', response.connection)
    #  print('RESPONSE content:', response.content)
    print('RESPONSE json:', message)

    assert(len(message.keys()) == 1)
    assert(message == {'type': 'websocket.connect'})
