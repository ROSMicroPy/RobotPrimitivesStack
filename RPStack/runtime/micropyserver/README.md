# Async node HTTP API

Declare `rpstack.micropyserver:NodeRestApi` in a node manifest's `runtime` list.
The runtime passes its node instance; configuration accepts `host`, `port`,
`request_limit`, `request_timeout_s`, and `max_clients`.

Each connection has its own reader, writer, and response object. Reads and writes
have deadlines. Requests are size-bounded; duplicate Content-Length and unsupported
Transfer-Encoding are rejected. The listener remains responsive while operations
or other clients are waiting.

`GET /manifest` returns the public node discovery projection. Ordinary service
operations use `POST /api/services/{service_id}/{operation}` and return 202 with
a task ID and status URL. Poll `GET /api/task?id=ID` for the final result.
`GET /api/tasks` reports active and retained completed work.

`POST /api/node/stop` and `/api/node/reset` operate outside the motion queue.
`GET /api/node/status` and cached service status do not wait on motion locks.
`POST /api/task/cancel` accepts an operation/flow ID. Workflow control uses
`POST /api/flows/start` and `POST /api/events`.

This replaces the old synchronous `ManifestRestApi` and shared-connection server.
