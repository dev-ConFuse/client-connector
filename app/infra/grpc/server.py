"""
Client Connector gRPC Server

Implements the ClientConnector gRPC service defined in proto/client.proto
"""

import asyncio
import os
from concurrent import futures

import grpc
import structlog

logger = structlog.get_logger()


class ClientConnectorServicer:  # (client_pb2_grpc.ClientConnectorServicer):
    """
    Implementation of ClientConnector gRPC service.

    To generate proto code, run:
    python -m grpc_tools.protoc -I./proto --python_out=./proto --grpc_python_out=./proto proto/client.proto
    """

    async def CreateSession(self, request, context):
        """Create a new MCP session."""
        logger.info(
            "gRPC CreateSession called",
            client_id=request.client_id,
            client_type=request.client_type,
        )
        # TODO: Implement session creation
        pass

    async def GetSession(self, request, context):
        """Get session details."""
        logger.info("gRPC GetSession called", session_id=request.session_id)
        # TODO: Implement
        pass

    async def CloseSession(self, request, context):
        """Close a session."""
        logger.info("gRPC CloseSession called", session_id=request.session_id)
        # TODO: Implement
        pass

    async def ListActiveSessions(self, request, context):
        """List active sessions."""
        logger.info("gRPC ListActiveSessions called")
        # TODO: Implement
        pass


async def serve_grpc():
    """Start the gRPC server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add servicer
    # client_pb2_grpc.add_ClientConnectorServicer_to_server(ClientConnectorServicer(), server)

    # Configure server (env-only — see .cline/rules/env-policy.md)
    grpc_port = int(os.environ["GRPC_PORT"])
    server.add_insecure_port(f"[::]:{grpc_port}")

    logger.info(f"Starting client-connector gRPC server on port {grpc_port}")
    await server.start()
    logger.info("gRPC server started successfully")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server")
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve_grpc())
