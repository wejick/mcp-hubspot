"""
Contacts-only MCP server for HubSpot.
Exposes 5 tools (vs 34 in full server) for ~85% token reduction on tool definitions.
"""
import asyncio
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from .faiss_manager import FaissManager
from .handlers.contact_handler import ContactHandler
from .hubspot_client import HubSpotClient, ApiException
from .server import initialize_embedding_model, initialize_faiss_manager, initialize_hubspot_client

logger = logging.getLogger("mcp_hubspot_contacts")
load_dotenv()


def create_contacts_server(
    contact_handler: ContactHandler,
) -> Server:
    server = Server("hubspot-contacts")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="hubspot_create_contact",
                description="Create a HubSpot contact (duplicate-safe)",
                inputSchema=contact_handler.get_create_contact_schema(),
            ),
            types.Tool(
                name="hubspot_get_contact",
                description="Get contact by ID",
                inputSchema=contact_handler.get_contact_schema(),
            ),
            types.Tool(
                name="hubspot_update_contact",
                description="Update contact properties",
                inputSchema=contact_handler.get_update_contact_schema(),
            ),
            types.Tool(
                name="hubspot_query_contacts",
                description="List recently active contacts or search by filters. Omit filters to list recent.",
                inputSchema=contact_handler.get_query_contacts_schema(),
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        try:
            if name == "hubspot_create_contact":
                return contact_handler.create_contact(arguments)
            elif name == "hubspot_get_contact":
                return contact_handler.get_contact(arguments)
            elif name == "hubspot_update_contact":
                return contact_handler.update_contact(arguments)
            elif name == "hubspot_query_contacts":
                return contact_handler.query_contacts(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
        except ApiException as e:
            return [types.TextContent(type="text", text=f"HubSpot API error: {str(e)}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def main(access_token: Optional[str] = None):
    embedding_model = initialize_embedding_model()
    faiss_manager = initialize_faiss_manager(embedding_model)
    hubspot_client = initialize_hubspot_client(access_token)

    contact_handler = ContactHandler(hubspot_client, faiss_manager, embedding_model)
    server = create_contacts_server(contact_handler)

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("HubSpot Contacts MCP server running")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="hubspot-contacts",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_main():
    import argparse

    parser = argparse.ArgumentParser(description="HubSpot Contacts MCP Server")
    parser.add_argument("--access-token", help="HubSpot API access token")
    args = parser.parse_args()
    asyncio.run(main(access_token=args.access_token))


if __name__ == "__main__":
    run_main()
