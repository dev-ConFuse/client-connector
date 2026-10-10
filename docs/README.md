# Client Connector

MCP Host Connector — the gateway for AI agents to connect to ConFuse
knowledge search through the Model Context Protocol.

> This is the canonical README for the service; **all documentation lives in
> [`docs/`](./)** (this folder). See [index.md](index.md) for the docs index.

**Service**: `client-connector/` · **Port**: `3020` (`CLIENT_CONNECTOR_PORT`)
**Stack**: Python 3.12, FastAPI, FastMCP, gRPC, WebSockets

## Overview

`client-connector` exposes ConFuse's knowledge search to AI agents (Claude and
other MCP clients):

- **MCP server** (FastMCP) with tools: `search_knowledge` (vector search),
  `query_knowledge` (natural-language, streaming), `health_check`
- **SSE/WebSocket transports** for MCP sessions (`/api/v1/mcp/sse`)
- **Agent registry** — JSON-MCP config bootstrap per agent
  (`GET /api/agents/{agent_id}/mcp-config`)
- **Prompt compression** — compacts results for LLM context budgets
- **Tiered rate limiting** — free / pro / team / enterprise budgets
- **gRPC clients** — auth-middleware token validation and mcp-server tools

## Key API surface

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/admin/sessions` | GET | Active sessions (auth required) |
| `/admin/stats` | GET | Gateway statistics (auth required) |
| `/api/agents` | GET/POST | List / register agents |
| `/api/agents/{id}/mcp-config` | GET | JSON-MCP bootstrap config |
| `/api/v1/mcp/sse` | GET | MCP SSE stream (`?agent_id=`) |

Full schemas: [api-reference.md](api-reference.md).

## How to run the microservice

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CLIENT_CONNECTOR_PORT` | HTTP port | `3020` |
| `AUTH_MIDDLEWARE_GRPC_ADDR` | auth-middleware gRPC | `auth-middleware:50058` |
| `MCP_SERVER_GRPC_ADDR` | mcp-server gRPC | `mcp-server:50056` |
| `DATA_VENT_URL` | retrieval backend | `http://localhost:3002` |

## Testing

Tests for this service live in the central test module (this service contains
no tests):

```bash
cd ../ConFuse-test-module
pip install -r requirements.txt
pytest client_connector mcp_integration -v
```

## Documentation

| Document | Contents |
|----------|----------|
| [index.md](index.md) | Overview & docs index |
| [api-reference.md](api-reference.md) | Full endpoint reference |
| [architecture.md](architecture.md) | Internal architecture |
| [setup.md](setup.md) | Local development setup |
