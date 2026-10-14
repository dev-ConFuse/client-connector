# Client Connector API Reference

> Current transports are REST/HTTP and MCP over SSE at
> `/api/v1/mcp/sse`. The legacy WebSocket examples retained below are not
> implemented by the current service.

> **REST and MCP Protocol Documentation**

## Overview

The Client Connector provides two API interfaces:
1. **REST API** - Service management and monitoring
2. **MCP over SSE** - Model Context Protocol for AI agents

## REST API

### Base URL
```
http://localhost:3020
```

### Authentication
All REST endpoints require JWT authentication via `Authorization: Bearer <token>` header.

### Endpoints

#### Health Check
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-03-26T01:00:00Z",
  "version": "0.1.0",
  "services": {
    "database": "connected",
    "auth_middleware": "connected",
    "falkordb": "connected"
  }
}
```

#### Service Status
```http
GET /status
Authorization: Bearer <token>
```

**Response**:
```json
{
  "service": "client-connector",
  "version": "0.1.0",
  "uptime": 3600,
  "active_sessions": 5,
  "total_queries": 1250,
  "error_rate": 0.02,
  "dependencies": {
    "auth_middleware": "healthy",
    "falkordb": "healthy",
    "feature_toggle": "healthy"
  }
}
```

#### Agent Management

##### List Connected Agents
```http
GET /agents
Authorization: Bearer <token>
```

**Response**:
```json
{
  "agents": [
    {
      "id": "agent_123",
      "name": "Cursor IDE",
      "user_id": "user_456",
      "connected_at": "2026-03-26T00:30:00Z",
      "last_activity": "2026-03-26T00:45:00Z",
      "queries_count": 25,
      "status": "active"
    }
  ],
  "total": 1
}
```

##### Get Agent Details
```http
GET /agents/{agent_id}
Authorization: Bearer <token>
```

**Response**:
```json
{
  "id": "agent_123",
  "name": "Cursor IDE",
  "user_id": "user_456",
  "connected_at": "2026-03-26T00:30:00Z",
  "last_activity": "2026-03-26T00:45:00Z",
  "queries_count": 25,
  "capabilities": [
    "semantic_search",
    "code_analysis",
    "document_lookup"
  ],
  "session_metadata": {
    "client_version": "1.0.0",
    "protocol_version": "2024-11-05"
  }
}
```

##### Disconnect Agent
```http
POST /agents/{agent_id}/disconnect
Authorization: Bearer <token>
```

**Response**:
```json
{
  "message": "Agent disconnected successfully",
  "agent_id": "agent_123",
  "disconnected_at": "2026-03-26T00:50:00Z"
}
```

#### Metrics
```http
GET /metrics
Authorization: Bearer <token>
```

**Response**:
```json
{
  "timestamp": "2026-03-26T01:00:00Z",
  "metrics": {
    "connections": {
      "active_sessions": 5,
      "total_connections": 150,
      "connection_rate": 2.5
    },
    "queries": {
      "total_queries": 1250,
      "queries_per_second": 0.35,
      "average_latency_ms": 150,
      "success_rate": 0.98
    },
    "resources": {
      "memory_usage_mb": 256,
      "cpu_usage_percent": 15,
      "database_connections": 8
    }
  }
}
```

## Historical WebSocket Design (Not Implemented)

The following examples are retained for historical context only. They are not
supported by the current client-connector runtime. Use the MCP SSE endpoint
`/api/v1/mcp/sse` instead.

### Connection Endpoint
```
ws://localhost:3020/ws?token=<jwt_token>
```

### Connection Flow
1. **Authentication**: Provide valid JWT token as query parameter
2. **Handshake**: Server validates token and establishes connection
3. **MCP Initialization**: Client sends `initialize` message
4. **Capability Exchange**: Server and client exchange capabilities
5. **Message Exchange**: Begin MCP protocol communication

### Connection Headers
```http
Sec-WebSocket-Protocol: mcp
Authorization: Bearer <token>
```

### Connection Response
```json
{
  "type": "connection_established",
  "session_id": "session_123",
  "server_info": {
    "name": "ConFuse Client Connector",
    "version": "0.1.0"
  }
}
```

## MCP Protocol API

### Protocol Version
```
2024-11-05
```

### Message Format
All MCP messages follow JSON-RPC 2.0 format:
```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "method": "method_name",
  "params": { ... }
}
```

### Core Methods

#### Initialize
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "init_001",
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "resources": {"subscribe": true},
      "prompts": {"listChanged": true}
    },
    "clientInfo": {
      "name": "Cursor IDE",
      "version": "1.0.0"
    }
  }
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "init_001",
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {"listChanged": true},
      "resources": {"subscribe": true, "listChanged": true},
      "prompts": {"listChanged": true}
    },
    "serverInfo": {
      "name": "ConFuse Client Connector",
      "version": "0.1.0"
    }
  }
}
```

#### Tools Operations

##### List Tools
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "tools_001",
  "method": "tools/list",
  "params": {}
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "tools_001",
  "result": {
    "tools": [
      {
        "name": "semantic_search",
        "description": "Search knowledge base using semantic similarity",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Search query"
            },
            "limit": {
              "type": "integer",
              "description": "Maximum number of results",
              "default": 10
            },
            "filters": {
              "type": "object",
              "description": "Search filters"
            }
          },
          "required": ["query"]
        }
      },
      {
        "name": "code_analysis",
        "description": "Analyze code structure and complexity",
        "inputSchema": {
          "type": "object",
          "properties": {
            "file_path": {
              "type": "string",
              "description": "Path to code file"
            },
            "analysis_type": {
              "type": "string",
              "enum": ["complexity", "dependencies", "security"],
              "description": "Type of analysis to perform"
            }
          },
          "required": ["file_path", "analysis_type"]
        }
      }
    ]
  }
}
```

##### Call Tool
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "tool_001",
  "method": "tools/call",
  "params": {
    "name": "semantic_search",
    "arguments": {
      "query": "React hooks usage patterns",
      "limit": 5,
      "filters": {
        "language": "javascript",
        "file_type": "jsx"
      }
    }
  }
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "tool_001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 5 results for 'React hooks usage patterns':\n\n1. useState Hook Pattern\nFile: src/components/UserProfile.tsx\nLines: 15-25\n\nconst [user, setUser] = useState(null);\nconst [loading, setLoading] = useState(false);\n\n2. useEffect Hook Pattern\nFile: src/hooks/useApi.js\nLines: 8-18\n\nuseEffect(() => {\n  fetchData();\n}, [dependencies]);\n\n..."
      }
    ],
    "isError": false
  }
}
```

#### Resources Operations

##### List Resources
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "res_001",
  "method": "resources/list",
  "params": {}
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "res_001",
  "result": {
    "resources": [
      {
        "uri": "confuse://knowledge/components",
        "name": "React Components",
        "description": "All React component documentation",
        "mimeType": "text/plain"
      },
      {
        "uri": "confuse://knowledge/api/endpoints",
        "name": "API Endpoints",
        "description": "REST API documentation",
        "mimeType": "application/json"
      }
    ]
  }
}
```

##### Read Resource
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "res_002",
  "method": "resources/read",
  "params": {
    "uri": "confuse://knowledge/components/Button"
  }
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "res_002",
  "result": {
    "contents": [
      {
        "uri": "confuse://knowledge/components/Button",
        "mimeType": "text/typescript",
        "text": "// Button Component Documentation\n\ninterface ButtonProps {\n  variant: 'primary' | 'secondary';\n  size: 'small' | 'medium' | 'large';\n  onClick: () => void;\n}\n\nexport const Button: React.FC<ButtonProps> = ({ variant, size, onClick }) => {\n  // Component implementation\n};"
      }
    ]
  }
}
```

#### Prompts Operations

##### List Prompts
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "prompt_001",
  "method": "prompts/list",
  "params": {}
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "prompt_001",
  "result": {
    "prompts": [
      {
        "name": "code_review",
        "description": "Generate code review comments",
        "arguments": [
          {
            "name": "language",
            "description": "Programming language",
            "required": true
          },
          {
            "name": "focus_area",
            "description": "Area to focus on",
            "required": false
          }
        ]
      },
      {
        "name": "documentation",
        "description": "Generate documentation for code",
        "arguments": [
          {
            "name": "code",
            "description": "Code to document",
            "required": true
          },
          {
            "name": "style",
            "description": "Documentation style",
            "required": false
          }
        ]
      }
    ]
  }
}
```

##### Get Prompt
**Client → Server**:
```json
{
  "jsonrpc": "2.0",
  "id": "prompt_002",
  "method": "prompts/get",
  "params": {
    "name": "code_review",
    "arguments": {
      "language": "typescript",
      "focus_area": "performance"
    }
  }
}
```

**Server → Client**:
```json
{
  "jsonrpc": "2.0",
  "id": "prompt_002",
  "result": {
    "description": "Generate comprehensive code review comments for TypeScript code with focus on performance",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "Please review this TypeScript code for performance issues:\n\n{{code}}\n\nFocus on: performance\n\nProvide specific, actionable feedback with code examples where appropriate."
        }
      }
    ]
  }
}
```

## Error Handling

### Error Response Format
```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "error": {
    "code": -32603,
    "message": "Internal error",
    "data": {
      "details": "Failed to connect to knowledge graph",
      "timestamp": "2026-03-26T01:00:00Z"
    }
  }
}
```

### Error Codes

| Code | Meaning | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON was received |
| -32600 | Invalid Request | JSON-RPC request is invalid |
| -32601 | Method not found | Method does not exist |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Internal server error |
| -32001 | Authentication failed | Invalid or expired token |
| -32002 | Authorization failed | Insufficient permissions |
| -32003 | Query timeout | Query execution timeout |
| -32004 | Resource not found | Requested resource not found |

## Rate Limiting

### Limits
- **Queries per minute**: 100 per agent
- **Concurrent connections**: 10 per user
- **WebSocket message size**: 1MB max
- **Query complexity**: Based on graph traversal depth

### Rate Limit Headers
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 85
X-RateLimit-Reset: 1648230000
```

## Authentication

### JWT Token Format
```json
{
  "sub": "user_123",
  "email": "user@example.com",
  "permissions": ["read", "search", "analyze"],
  "exp": 1648230000,
  "iat": 1648143600
}
```

### Required Scopes
- `confuse:agent` - Basic agent access
- `confuse:search` - Semantic search access
- `confuse:analyze` - Code analysis access
- `confuse:admin` - Administrative access

## SDK Examples

### Python SDK
```python
from confuse_client import ConFuseClient

async def main():
    client = ConFuseClient(
        endpoint="ws://localhost:3020/ws",
        token="your_jwt_token"
    )
    
    await client.connect()
    
    # Semantic search
    results = await client.search(
        query="React hooks patterns",
        limit=5
    )
    
    # Code analysis
    analysis = await client.analyze_code(
        file_path="src/components/Button.tsx",
        analysis_type="complexity"
    )
    
    await client.disconnect()
```

### JavaScript SDK
```javascript
import { ConFuseClient } from '@confuse/client-sdk';

const client = new ConFuseClient({
  endpoint: 'ws://localhost:3020/ws',
  token: 'your_jwt_token'
});

await client.connect();

// Semantic search
const results = await client.tools.call('semantic_search', {
  query: 'React hooks patterns',
  limit: 5
});

// Read resource
const documentation = await client.resources.read(
  'confuse://knowledge/components/Button'
);

await client.disconnect();
```

This API reference provides comprehensive documentation for integrating AI agents with the ConFuse knowledge platform through the Client Connector.
