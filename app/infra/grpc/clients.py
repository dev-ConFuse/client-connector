"""
Client Connector - MCP Server gRPC Client

Calls mcp-server for internal MCP tool implementations via gRPC
"""

import os

import grpc
import structlog

logger = structlog.get_logger()

# Note: Generate from proto with:
# python -m grpc_tools.protoc -I../mcp-server/proto --python_out=./proto --grpc_python_out=./proto ../mcp-server/proto/mcp.proto


class McpServerClient:
    """
    gRPC client for calling mcp-server's internal tool implementations
    """

    def __init__(self):
        self.channel = None
        self.stub = None

    async def connect(self):
        """Connect to mcp-server via gRPC"""
        mcp_server_addr = os.environ["MCP_SERVER_GRPC_ADDR"]

        self.channel = grpc.aio.insecure_channel(mcp_server_addr)
        # self.stub = mcp_pb2_grpc.McpStub(self.channel)

        logger.info("Connected to mcp-server via gRPC", address=mcp_server_addr)

    async def list_tools(self, category: str = None):
        """List available MCP tools"""
        logger.info("Listing tools from mcp-server", category=category)

        # request = mcp_pb2.ListToolsRequest(category=category)
        # response = await self.stub.ListTools(request)
        # return response.tools

        return []

    async def call_tool(self, tool_id: str, parameters: dict, user_id: str, session_id: str):
        """Call a specific MCP tool"""
        logger.info("Calling tool via mcp-server", tool_id=tool_id, user_id=user_id)

        # request = mcp_pb2.CallToolRequest(
        #     tool_id=tool_id,
        #     parameters=parameters,
        #     user_id=user_id,
        #     session_id=session_id
        # )
        # response = await self.stub.CallTool(request)
        # return response

        return {"success": False, "error": "Not implemented"}

    async def get_tool_schema(self, tool_id: str):
        """Get schema for a specific tool"""
        logger.info("Getting tool schema from mcp-server", tool_id=tool_id)

        # request = mcp_pb2.ToolSchemaRequest(tool_id=tool_id)
        # response = await self.stub.GetToolSchema(request)
        # return response.json_schema

        return "{}"

    async def close(self):
        """Close the gRPC connection"""
        if self.channel:
            await self.channel.close()
            logger.info("Closed mcp-server gRPC connection")


# Global client instance
_mcp_client: McpServerClient | None = None


async def get_mcp_client() -> McpServerClient:
    """Get or initialize the global MCP client"""
    global _mcp_client

    if _mcp_client is None:
        _mcp_client = McpServerClient()
        await _mcp_client.connect()

    return _mcp_client


async def close_mcp_client():
    """Close the global MCP client"""
    global _mcp_client

    if _mcp_client:
        await _mcp_client.close()
        _mcp_client = None
