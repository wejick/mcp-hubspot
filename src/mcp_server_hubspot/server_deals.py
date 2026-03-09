"""
Deals-only MCP server for HubSpot.
Exposes 7 tools (vs 34 in full server) for ~80% token reduction on tool definitions.
Includes pipeline tools required to look up valid deal stages.
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

from .handlers.deal_handler import DealHandler
from .handlers.pipeline_handler import PipelineHandler
from .hubspot_client import HubSpotClient, ApiException
from .server import initialize_embedding_model, initialize_sqlite_manager, initialize_hubspot_client

logger = logging.getLogger("mcp_hubspot_deals")
load_dotenv()


def create_deals_server(
    deal_handler: DealHandler,
    pipeline_handler: PipelineHandler,
) -> Server:
    server = Server("hubspot-deals")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="hubspot_create_deal",
                description="Create a HubSpot deal",
                inputSchema=deal_handler.get_create_deal_schema(),
            ),
            types.Tool(
                name="hubspot_get_deal",
                description="Get deal by ID",
                inputSchema=deal_handler.get_deal_schema(),
            ),
            types.Tool(
                name="hubspot_update_deal",
                description="Update deal properties",
                inputSchema=deal_handler.get_update_deal_schema(),
            ),
            types.Tool(
                name="hubspot_query_deals",
                description="List recently modified deals or search by filters. Omit filters to list recent.",
                inputSchema=deal_handler.get_query_deals_schema(),
            ),
            types.Tool(
                name="hubspot_get_pipelines",
                description="List pipelines and their stages (use object_type='deals')",
                inputSchema=pipeline_handler.get_pipelines_schema(),
            ),
            types.Tool(
                name="hubspot_move_deal_stage",
                description="Move a deal to a different pipeline stage",
                inputSchema=pipeline_handler.get_move_deal_stage_schema(),
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        try:
            if name == "hubspot_create_deal":
                return deal_handler.create_deal(arguments)
            elif name == "hubspot_get_deal":
                return deal_handler.get_deal(arguments)
            elif name == "hubspot_update_deal":
                return deal_handler.update_deal(arguments)
            elif name == "hubspot_query_deals":
                return deal_handler.query_deals(arguments)
            elif name == "hubspot_get_pipelines":
                return pipeline_handler.get_pipelines(arguments)
            elif name == "hubspot_move_deal_stage":
                return pipeline_handler.move_deal_stage(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
        except ApiException as e:
            return [types.TextContent(type="text", text=f"HubSpot API error: {str(e)}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def main(access_token: Optional[str] = None):
    embedding_model = initialize_embedding_model()
    sqlite_manager = initialize_sqlite_manager(embedding_model)
    hubspot_client = initialize_hubspot_client(access_token)

    deal_handler = DealHandler(hubspot_client, sqlite_manager, embedding_model)
    pipeline_handler = PipelineHandler(hubspot_client, sqlite_manager, embedding_model)
    server = create_deals_server(deal_handler, pipeline_handler)

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("HubSpot Deals MCP server running")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="hubspot-deals",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_main():
    import argparse

    parser = argparse.ArgumentParser(description="HubSpot Deals MCP Server")
    parser.add_argument("--access-token", help="HubSpot API access token")
    args = parser.parse_args()
    asyncio.run(main(access_token=args.access_token))


if __name__ == "__main__":
    run_main()
