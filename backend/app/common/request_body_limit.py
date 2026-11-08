import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None and content_length.isdigit():
            if int(content_length) > self.max_body_bytes:
                await self._reject_large_body(send)
                return

        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            size += len(message.get("body", b""))
            if size > self.max_body_bytes:
                await self._reject_large_body(send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject_large_body(send: Send) -> None:
        body = json.dumps(
            {
                "detail": "Request body is too large.",
                "code": "request_body_too_large",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
