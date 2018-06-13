import enum
import typing

from apistar.exceptions import HTTPException
from apistar.server.asgi import ASGIReceive, ASGIScope, ASGISend
from apistar.server.components import Component


class Status():
    ok = 1000
    leaving = 1001
    prot_error = 1002
    unsupported_type = 1003
    reserved_1004 = 1004
    no_status = 1005
    closed_abnormal = 1006
    inalid_data = 1007
    policy_violation = 1008
    too_big = 1009
    tls_fail = 1010

    @property
    def OK(self):
        """
        1000 indicates a normal closure, meaning that the purpose for
        which the connection was established has been fulfilled.
        """
        return self.ok

    @property
    def LEAVING(self):
        """
        1001 indicates that an endpoint is "going away", such as a server
        going down or a browser having navigated away from a page.
        """
        return self.leaving

    @property
    def PROT_ERROR(self):
        """
        1002 indicates that an endpoint is terminating the connection due
        to a protocol error.
        """
        return self.prot_error

    @property
    def UNSUPPORTED_TYPE(self):
        """
        1003 indicates that an endpoint is terminating the connection
        because it has received a type of data it cannot accept (e.g., an
        endpoint that understands only text data MAY send this if it
        receives a binary message).
        """
        return self.unsupported_type

    @property
    def RESERVED_1004(self):
        """
        Reserved.  The specific meaning might be defined in the future.
        """
        return self.reserved_1004

    @property
    def NO_STATUS(self):
        """
        1005 is a reserved value and MUST NOT be set as a status code in a
        Close control frame by an endpoint.  It is designated for use in
        applications expecting a status code to indicate that no status
        code was actually present.
        """
        return self.no_status

    @property
    def CLOSED_ABNORMAL(self):
        """
        1006 is a reserved value and MUST NOT be set as a status code in a
        Close control frame by an endpoint.  It is designated for use in
        applications expecting a status code to indicate that the
        connection was closed abnormally, e.g., without sending or
        receiving a Close control frame.
        """
        return self.closed_abnormal

    @property
    def INALID_DATA(self):
        """
        1007 indicates that an endpoint is terminating the connection
        because it has received data within a message that was not
        consistent with the type of the message (e.g., non-UTF-8 [RFC3629]
        data within a text message).
        """
        return self.inalid_data

    @property
    def POLICY_VIOLATION(self):
        """
        1008 indicates that an endpoint is terminating the connection
        because it has received a message that violates its policy.  This
        is a generic status code that can be returned when there is no
        other more suitable status code (e.g., 1003 or 1009) or if there
        is a need to hide specific details about the policy.
        """
        return self.policy_violation

    @property
    def TOO_BIG(self):
        """
        1009 indicates that an endpoint is terminating the connection
        because it has received a message that is too big for it to
        process.
        """
        return self.too_big

    @property
    def TLS_FAIL(self):
        """
        1010 indicates that an endpoint (client) is terminating the
        connection because it has expected the server to negotiate one or
        more extension, but the server didn't return them in the response
        message of the WebSocket handshake.  The list of extensions that
        """
        return self.tls_fail


status = Status()


class WSState(enum.Enum):
    CONNECTING = 0
    CONNECTED = 1
    CLOSED = 2


class WebSocketNotConnected(HTTPException):
    def __init__(self,
                 detail: str = 'WebSocket is not connected or open',
                 status_code: int = status.OK) -> None:
        super().__init__(detail, 200)


class WebSocketProtocolError(HTTPException):
    def __init__(self,
                 detail: str = 'WebSocket protocol error',
                 status_code: int = status.PROT_ERROR) -> None:
        super().__init__(detail, status_code)


class WebSocket(object):
    def __init__(self,
                 asgi_scope: ASGIScope,
                 asgi_send: ASGISend,
                 asgi_receive: ASGIReceive,
                 ) -> None:

        if asgi_scope['type'] != 'websocket':
            raise WebSocketProtocolError(
                detail="ASGI scope is not 'websocket'"
            )

        self._scope = asgi_scope
        self._asgi_send = asgi_send
        self._asgi_receive = asgi_receive
        self._state = WSState.CLOSED

    @property
    def state(self):
        return self._state

    async def send(self, data: typing.Union[str, bytes]):
        if self.state == WSState.CLOSED:
            raise WebSocketNotConnected()

        msg = {
            'type': 'websocket.send',
        }

        if data:
            if isinstance(data, bytes):
                msg['bytes'] = data
            else:
                msg['text'] = data

        return await self._asgi_send(msg)

    async def receive(self):
        if self.state != WSState.CONNECTED:
            raise WebSocketNotConnected()

        msg = await self._asgi_receive()
        return msg.get('text', msg.get('bytes'))

    async def connect(self):
        if self.state != WSState.CLOSED:
            raise WebSocketProtocolError(
                detail="Attempting to connect a WebSocket that is not closed"
            )

        # Try to accept and upgrade the websocket
        msg = await self._asgi_receive()

        if msg['type'] != 'websocket.connect':
            raise WebSocketProtocolError(
                'Expected websocket connection but got: %s' % msg['type'])

        self._state = WSState.CONNECTING

        await self._asgi_send({'type': 'websocket.accept'})

    async def accept(self, subprotocol: str = None):
        if self.state != WSState.CONNECTING:
            raise WebSocketProtocolError(
                detail="Attempting to accept a WebSocket that is not connecting"
            )

        msg = {'type': 'websocket.accept'}
        if subprotocol:
            msg['subprotocol'] = subprotocol

        await self._asgi_send(msg)
        self._state = WSState.CONNECTED

    async def close(self, code: int = status.OK):
        if self.state != WSState.CONNECTED:
            raise WebSocketNotConnected()

        message = {
            'type': 'websocket.disconnect',
            'code': code,
        }

        await self._asgi_send(message)
        self._state = WSState.CLOSED


class WebSocketComponent(Component):
    def resolve(self,
                scope: ASGIScope,
                send: ASGISend,
                receive: ASGIReceive) -> WebSocket:

        return WebSocket(scope, send, receive)
