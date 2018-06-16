import asyncio
import io
import typing
#  from pprint import pformat as pf
from urllib.parse import unquote, urlparse

import requests


class _HeaderDict(requests.packages.urllib3._collections.HTTPHeaderDict):
    def get_all(self, key, default):
        return self.getheaders(key)


class _MockOriginalResponse(object):
    """
    We have to jump through some hoops to present the response as if
    it was made using urllib3.
    """
    def __init__(self, headers):
        self.msg = _HeaderDict(headers)
        self.closed = False

    def isclosed(self):
        return self.closed

    def close(self):
        self.closed = True


class _WSGIAdapter(requests.adapters.HTTPAdapter):
    """
    A transport adapter for `requests` that makes requests directly to a
    WSGI app, rather than making actual HTTP requests over the network.
    """
    def __init__(self, app: typing.Callable) -> None:
        self.app = app

    def get_environ(self, request: requests.PreparedRequest) -> typing.Dict[str, typing.Any]:
        """
        Given a `requests.PreparedRequest` instance, return a WSGI environ dict.
        """
        body = request.body
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")  # type: bytes
        else:
            body_bytes = body

        url_components = urlparse(request.url)
        environ = {
            'REQUEST_METHOD': request.method,
            'wsgi.url_scheme': url_components.scheme,
            'SCRIPT_NAME': '',
            'PATH_INFO': unquote(url_components.path),
            'wsgi.input': io.BytesIO(body_bytes),
        }  # type: typing.Dict[str, typing.Any]

        if url_components.query:
            environ['QUERY_STRING'] = url_components.query

        if url_components.port:
            environ['SERVER_NAME'] = url_components.hostname
            environ['SERVER_PORT'] = str(url_components.port)
        else:
            environ['HTTP_HOST'] = url_components.hostname

        for key, value in request.headers.items():
            key = key.upper().replace('-', '_')
            if key not in ('CONTENT_LENGTH', 'CONTENT_TYPE'):
                key = 'HTTP_' + key
            environ[key] = value

        return environ

    def send(self, request, *args, **kwargs):
        """
        Make an outgoing request to a WSGI application.
        """
        raw_kwargs = {}

        def start_response(wsgi_status, wsgi_headers, exc_info=None):
            if exc_info is not None:
                raise exc_info[0].with_traceback(exc_info[1], exc_info[2])
            status, _, reason = wsgi_status.partition(' ')
            raw_kwargs['status'] = int(status)
            raw_kwargs['reason'] = reason
            raw_kwargs['headers'] = wsgi_headers
            raw_kwargs['version'] = 11
            raw_kwargs['preload_content'] = False
            raw_kwargs['original_response'] = _MockOriginalResponse(wsgi_headers)

        # Make the outgoing request via WSGI.
        environ = self.get_environ(request)
        wsgi_response = self.app(environ, start_response)

        # Build the underlying urllib3.HTTPResponse
        raw_kwargs['body'] = io.BytesIO(b''.join(wsgi_response))
        raw = requests.packages.urllib3.HTTPResponse(**raw_kwargs)

        # Build the requests.Response
        return self.build_response(request, raw)


class ASGIDataFaker():
    """
    Prime and save receive and send messages, respectively, for ASGI test
    data.
    """
    def __init__(self, msgs: list = None):
        self.rq = asyncio.Queue()
        self.sq = asyncio.Queue()

        if msgs:
            [self.rq.put_nowait(m) for m in msgs]

    async def receive(self):
        return await self.rq.get()

    async def send(self, msg):
        return await self.sq.put(msg)

    @property
    def send_q(self):
        return self.sq


class _ASGIAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, app: typing.Callable, asgi_faker: ASGIDataFaker = None) -> None:
        self.app = app
        self.asgi_faker = asgi_faker
        # For websocket connections just enforce the expected connection state
        # and it's transistions
        self.websocket_state = 'closed'

    def send(self, request, *args, **kwargs):
        #  print('_ASGIAdapter: outer send')
        scheme, netloc, path, params, query, fragement = urlparse(request.url)
        if ':' in netloc:
            host, port = netloc.split(':', 1)
            port = int(port)
        else:
            host = netloc
            port = {'http': 80, 'https': 443, 'ws': 80, 'wss': 443}[scheme]

        type_ = {'http': 'http', 'https': 'http', 'ws': 'websocket', 'ws': 'websocket'}[scheme]

        # Include the 'host' header.
        if 'host' in request.headers:
            headers = []
        elif port == 80:
            headers = [[b'host', host.encode()]]
        else:
            headers = [[b'host', ('%s:%d' % (host, port)).encode()]]

        # Include other request headers.
        headers += [
            [key.encode(), value.encode()]
            for key, value in request.headers.items()
        ]

        scope = {
            'type': type_,
            'http_version': '1.1',
            'method': request.method,
            'path': unquote(path),
            'root_path': '',
            'scheme': scheme,
            'query_string': query.encode(),
            'headers': headers,
            'client': ['testclient', 50000],
            'server': [host, port],
            'raise_exceptions': True  # Not actually part of the spec.
        }

        if type_ == 'websocket' and 'Sec-WebSocket-Protocol' in request.headers:
            scope['subprotocols'] = request.headers['Sec-WebSocket-Protocol'].split(',')

        async def receive():
            #  print('_ASGIAdapter:receive', type_)
            # If a faker is present, use it's message data.
            if self.asgi_faker:
                msg = await self.asgi_faker.receive()

                if type_ == 'websocket':
                    if msg['type'] == 'websocket.connect':
                        self.websocket_state = 'connecting'
                    if msg['type'] == 'websocket.disconnect':
                        self.websocket_state = 'closed'

                #  print('_ASGIAdapter:receive faking:', msg)
                return msg

            #  print('_ASGIAdapter:receive scope', pf(scope))
            body = request.body
            if isinstance(body, str):
                body_bytes = body.encode("utf-8")  # type: bytes
            elif body is None:
                body_bytes = b''
            else:
                body_bytes = body

            if type_ == 'websocket':
                self.websocket_state = 'connecting'
                #  print('_ASGIAdapter:receive', type_, self.websocket_state)

                return {
                    'type': 'websocket.connect',
                }

            return {
                'type': 'http.request',
                'body': body_bytes,
            }

        async def send(message):
            #  print('_ASGIAdapter:send', type_, message)

            if self.asgi_faker:
                #  print('_ASGIAdapter:send to faker:', message)
                await self.asgi_faker.send(message)

            if message['type'] == 'http.response.start':
                raw_kwargs['version'] = 11
                raw_kwargs['status'] = message['status']
                raw_kwargs['headers'] = [
                    (key.decode(), value.decode())
                    for key, value in message['headers']
                ]
                raw_kwargs['preload_content'] = False
                raw_kwargs['original_response'] = _MockOriginalResponse(raw_kwargs['headers'])
            elif message['type'] == 'http.response.body':
                raw_kwargs['body'] = io.BytesIO(message['body'])
            elif message['type'] == 'websocket.accept':
                if self.websocket_state != 'connecting':
                    raise Exception(
                        "Sent accept when WebSocket is not connecting, it is %s",
                        self.websocket_state)
                self.websocket_state = 'connected'
            elif message['type'] == 'websocket.close':
                if self.websocket_state == 'closed':
                    raise Exception("Closing a closed websocket")

                # The one case we return an HTTP response, if the
                # socket connection upgrade is refused
                if self.websocket_state == 'connecting':
                    raw_kwargs['status'] = 403
                    raw_kwargs['reason'] = 'WebSocket closed'
                    raw_kwargs['body'] = io.BytesIO(b'')

                self.websocket_state = 'closed'
            elif message['type'] == 'websocket.send':
                if self.websocket_state != 'connected':
                    raise Exception("WebSocket not connected, it is %s", self.websocket_state)

            elif message['type'] == 'http.exc_info':
                exc_info = message['exc_info']
                raise exc_info[0].with_traceback(exc_info[1], exc_info[2])
            else:
                raise Exception("Unknown ASGI message type: %s" % message['type'])

        raw_kwargs = {}
        connection = self.app(scope)

        loop = asyncio.get_event_loop()
        #  print('_ASGIAdapter:send running app in loop...')
        loop.run_until_complete(connection(receive, send))

        if scope['type'] == 'websocket':
            # Since we don't handle the websocket protocol directly in testing
            # and the test client at this time is not websocket aware, we need
            # to return a friendly response if there is no HTTP response from
            # the websocket testing.
            if not raw_kwargs.get('status'):
                raw_kwargs['status'] = 200
                raw_kwargs['body'] = io.BytesIO(b'')

        #  print('_ASGIAdapter:send building http response', pf(raw_kwargs))
        raw = requests.packages.urllib3.HTTPResponse(**raw_kwargs)
        return self.build_response(request, raw)


class _TestClient(requests.Session):
    def __init__(self,
                 app: typing.Callable,
                 scheme: str,
                 hostname: str,
                 asgi_faker: ASGIDataFaker = None) -> None:
        super(_TestClient, self).__init__()
        interface = getattr(app, 'interface', None)

        if interface == 'asgi':
            adapter = _ASGIAdapter(app, asgi_faker)
            self.mount('ws://', adapter)
            self.mount('wss://', adapter)
        else:
            adapter = _WSGIAdapter(app)

        self.mount('http://', adapter)
        self.mount('https://', adapter)
        self.headers.update({'User-Agent': 'testclient'})
        self.scheme = scheme
        self.hostname = hostname

    def request(self, method: str, url: str, **kwargs) -> requests.Response:  # type: ignore
        if not (url.startswith('http:') or url.startswith('https:')):
            assert url.startswith('/'), (
                "TestClient expected either "
                "an absolute URL starting 'http:' / 'https:', "
                "or a relative URL starting with '/'. URL was '%s'." % url
            )
            url = '%s://%s%s' % (self.scheme, self.hostname, url)
        return super().request(method, url, **kwargs)


def TestClient(app: typing.Callable, scheme: str='http', hostname: str='testserver') -> _TestClient:
    """
    We have to work around py.test discovery attempting to pick up
    the `TestClient` class, by declaring this as a function.
    """
    return _TestClient(app, scheme, hostname)


def ASGITestClient(
                   app: typing.Callable,
                   scheme: str='http',
                   hostname: str='testserver',
                   asgi_faker: ASGIDataFaker = None) -> _TestClient:
    """
    We have to work around py.test discovery attempting to pick up
    the `TestClient` class, by declaring this as a function.
    """
    return _TestClient(app, scheme, hostname, asgi_faker=asgi_faker)
