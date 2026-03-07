"""
MCP server module for HubSpot integration.
Provides tools for interacting with HubSpot API through an MCP server interface.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
import json
from dotenv import load_dotenv

from mcp.server.models import InitializationOptions
from mcp.server.lowlevel import NotificationOptions
import mcp.types as types
from mcp.server import Server
import mcp.server.stdio
from pydantic import AnyUrl

from sentence_transformers import SentenceTransformer

from .hubspot_client import HubSpotClient, ApiException
from .faiss_manager import FaissManager
from .utils import store_in_faiss, search_in_faiss
from .handlers.company_handler import CompanyHandler
from .handlers.contact_handler import ContactHandler
from .handlers.conversation_handler import ConversationHandler
from .handlers.ticket_handler import TicketHandler
from .handlers.search_handler import SearchHandler
from .handlers.property_handler import PropertyHandler
from .handlers.deal_handler import DealHandler
from .handlers.association_handler import AssociationHandler
from .handlers.engagement_handler import EngagementHandler
from .handlers.pipeline_handler import PipelineHandler

logger = logging.getLogger('mcp_hubspot_server')

load_dotenv()

async def main(access_token: Optional[str] = None):
    """Run the HubSpot MCP server."""
    logger.info("Server starting")
    
    # Initialize dependencies
    embedding_model = initialize_embedding_model()
    faiss_manager = initialize_faiss_manager(embedding_model)
    hubspot_client = initialize_hubspot_client(access_token)
    
    # Initialize handlers with dependencies
    company_handler = CompanyHandler(hubspot_client, faiss_manager, embedding_model)
    contact_handler = ContactHandler(hubspot_client, faiss_manager, embedding_model)
    conversation_handler = ConversationHandler(hubspot_client, faiss_manager, embedding_model)
    ticket_handler = TicketHandler(hubspot_client, faiss_manager, embedding_model)
    search_handler = SearchHandler(faiss_manager, embedding_model)
    property_handler = PropertyHandler(hubspot_client, faiss_manager, embedding_model)
    deal_handler = DealHandler(hubspot_client, faiss_manager, embedding_model)
    association_handler = AssociationHandler(hubspot_client, faiss_manager, embedding_model)
    engagement_handler = EngagementHandler(hubspot_client, faiss_manager, embedding_model)
    pipeline_handler = PipelineHandler(hubspot_client, faiss_manager, embedding_model)

    # Create server
    server = create_server_with_handlers(
        company_handler,
        contact_handler,
        conversation_handler,
        ticket_handler,
        search_handler,
        property_handler,
        deal_handler,
        association_handler,
        engagement_handler,
        pipeline_handler
    )
    
    # Based on MCP implementation, use stdio_server as a context manager that yields streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        # Log server start
        logger.info("Server running with stdio transport")
        
        # Create initialization options with capabilities
        initialization_options = InitializationOptions(
            server_name="hubspot-manager",
            server_version="0.2.0",
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={}
            )
        )
        
        # Run the server with the provided streams and options
        await server.run(read_stream, write_stream, initialization_options)

def initialize_embedding_model() -> SentenceTransformer:
    """Initialize and return the embedding model."""
    logger.info("Loading embeddings model")
    
    local_model_path = '/app/models/all-MiniLM-L6-v2'
    if os.path.exists(local_model_path):
        logger.info(f"Using local model from {local_model_path}")
        embedding_model = SentenceTransformer(local_model_path)
    else:
        logger.info("Local model not found, downloading from HuggingFace")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    
    embedding_dim = embedding_model.get_sentence_embedding_dimension()
    logger.info(f"Embeddings model loaded with dimension: {embedding_dim}")
    
    return embedding_model

def initialize_faiss_manager(embedding_model: SentenceTransformer) -> FaissManager:
    """Initialize and return the FAISS manager."""
    storage_dir = os.getenv("HUBSPOT_STORAGE_DIR_LOCAL", "/storage")
    logger.info(f"Using storage directory: {storage_dir}")
    
    embedding_dim = embedding_model.get_sentence_embedding_dimension()
    faiss_manager = FaissManager(
        storage_dir=storage_dir,
        embedding_dimension=embedding_dim
    )
    logger.info(f"FAISS manager initialized with dimension {embedding_dim}")
    
    return faiss_manager

def initialize_hubspot_client(access_token: Optional[str]) -> HubSpotClient:
    """Initialize and return the HubSpot client."""
    return HubSpotClient(access_token)

def create_server_with_handlers(
    company_handler: CompanyHandler,
    contact_handler: ContactHandler,
    conversation_handler: ConversationHandler,
    ticket_handler: TicketHandler,
    search_handler: SearchHandler,
    property_handler: PropertyHandler,
    deal_handler: DealHandler,
    association_handler: AssociationHandler,
    engagement_handler: EngagementHandler,
    pipeline_handler: PipelineHandler
) -> Server:
    """Create and configure the MCP server with all handlers."""
    server = Server("hubspot-manager")

    # Register resource handlers
    register_resource_handlers(server)

    # Register tool definitions
    register_tool_definitions(server,
                             company_handler,
                             contact_handler,
                             conversation_handler,
                             ticket_handler,
                             search_handler,
                             property_handler,
                             deal_handler,
                             association_handler,
                             engagement_handler,
                             pipeline_handler)

    # Register tool call handler
    register_tool_call_handler(server,
                              company_handler,
                              contact_handler,
                              conversation_handler,
                              ticket_handler,
                              search_handler,
                              property_handler,
                              deal_handler,
                              association_handler,
                              engagement_handler,
                              pipeline_handler)

    return server

def register_resource_handlers(server: Server) -> None:
    """Register resource-related handlers with the server.
    
    Args:
        server: MCP server instance
    """
    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        return []

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        if uri.scheme != "hubspot":
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")
        path = str(uri).replace("hubspot://", "")
        return ""

def register_tool_definitions(
    server: Server,
    company_handler: CompanyHandler,
    contact_handler: ContactHandler,
    conversation_handler: ConversationHandler,
    ticket_handler: TicketHandler,
    search_handler: SearchHandler,
    property_handler: PropertyHandler,
    deal_handler: DealHandler,
    association_handler: AssociationHandler,
    engagement_handler: EngagementHandler,
    pipeline_handler: PipelineHandler
) -> None:
    """Register tool definitions with the server.

    Args:
        server: MCP server instance
        company_handler: Handler for company operations
        contact_handler: Handler for contact operations
        conversation_handler: Handler for conversation operations
        ticket_handler: Handler for ticket operations
        search_handler: Handler for search operations
        property_handler: Handler for property operations
        deal_handler: Handler for deal operations
        association_handler: Handler for association operations
        engagement_handler: Handler for engagement operations
        pipeline_handler: Handler for pipeline operations
    """
    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        return [
            # Company tools
            types.Tool(
                name="hubspot_create_company",
                description="Create a new company in HubSpot",
                inputSchema=company_handler.get_create_company_schema(),
            ),
            types.Tool(
                name="hubspot_get_company_activity",
                description="Get activity history for a specific company",
                inputSchema=company_handler.get_company_activity_schema(),
            ),
            types.Tool(
                name="hubspot_get_active_companies",
                description="Get most recently active companies from HubSpot",
                inputSchema=company_handler.get_active_companies_schema(),
            ),
            types.Tool(
                name="hubspot_get_company",
                description="Get a specific company by ID from HubSpot",
                inputSchema=company_handler.get_company_schema(),
            ),
            types.Tool(
                name="hubspot_update_company",
                description="Update an existing company record in HubSpot",
                inputSchema=company_handler.get_update_company_schema(),
            ),

            # Contact tools
            types.Tool(
                name="hubspot_create_contact",
                description="Create a new contact in HubSpot",
                inputSchema=contact_handler.get_create_contact_schema(),
            ),
            types.Tool(
                name="hubspot_get_active_contacts",
                description="Get most recently active contacts from HubSpot",
                inputSchema=contact_handler.get_active_contacts_schema(),
            ),
            types.Tool(
                name="hubspot_get_contact",
                description="Get a specific contact by ID from HubSpot",
                inputSchema=contact_handler.get_contact_schema(),
            ),
            types.Tool(
                name="hubspot_update_contact",
                description="Update an existing contact record in HubSpot",
                inputSchema=contact_handler.get_update_contact_schema(),
            ),

            # Conversation tools
            types.Tool(
                name="hubspot_get_recent_conversations",
                description="Get recent conversation threads from HubSpot with their messages",
                inputSchema=conversation_handler.get_recent_conversations_schema(),
            ),
            
            # Ticket tools
            types.Tool(
                name="hubspot_get_tickets",
                description="Get tickets from HubSpot based on configurable selection criteria",
                inputSchema=ticket_handler.get_tickets_schema(),
            ),
            types.Tool(
                name="hubspot_get_ticket_conversation_threads",
                description="Get conversation threads associated with a specific ticket",
                inputSchema=ticket_handler.get_ticket_conversation_threads_schema(),
            ),
            
            # Search tools
            types.Tool(
                name="hubspot_search_data",
                description="Semantic similarity search over locally cached HubSpot data (contacts, companies, deals, tickets, etc.). Use this to find records by meaning rather than exact field values. Does NOT query the live HubSpot API.",
                inputSchema=search_handler.get_search_data_schema(),
            ),
            types.Tool(
                name="hubspot_search_contacts",
                description="Search contacts in HubSpot with custom filters",
                inputSchema=contact_handler.get_search_contacts_schema(),
            ),
            types.Tool(
                name="hubspot_search_companies",
                description="Search companies in HubSpot with custom filters",
                inputSchema=company_handler.get_search_companies_schema(),
            ),

            # Ticket CRUD tools
            types.Tool(
                name="hubspot_create_ticket",
                description="Create a new ticket in HubSpot",
                inputSchema=ticket_handler.get_create_ticket_schema(),
            ),
            types.Tool(
                name="hubspot_update_ticket",
                description="Update an existing ticket in HubSpot",
                inputSchema=ticket_handler.get_update_ticket_schema(),
            ),
            types.Tool(
                name="hubspot_get_ticket",
                description="Get a specific ticket by ID from HubSpot",
                inputSchema=ticket_handler.get_ticket_schema(),
            ),

            # Deal tools
            types.Tool(
                name="hubspot_create_deal",
                description="Create a new deal in HubSpot",
                inputSchema=deal_handler.get_create_deal_schema(),
            ),
            types.Tool(
                name="hubspot_get_deal",
                description="Get a specific deal by ID from HubSpot",
                inputSchema=deal_handler.get_deal_schema(),
            ),
            types.Tool(
                name="hubspot_update_deal",
                description="Update an existing deal in HubSpot",
                inputSchema=deal_handler.get_update_deal_schema(),
            ),
            types.Tool(
                name="hubspot_get_deals",
                description="Get most recently modified deals from HubSpot",
                inputSchema=deal_handler.get_deals_schema(),
            ),
            types.Tool(
                name="hubspot_search_deals",
                description="Search deals in HubSpot with custom filters",
                inputSchema=deal_handler.get_search_deals_schema(),
            ),

            # Association tools
            types.Tool(
                name="hubspot_create_association",
                description="Create an association between two HubSpot objects (e.g. contact to company)",
                inputSchema=association_handler.get_create_association_schema(),
            ),
            types.Tool(
                name="hubspot_get_associations",
                description="Get all associations of a specific type for a given HubSpot object",
                inputSchema=association_handler.get_associations_schema(),
            ),
            types.Tool(
                name="hubspot_delete_association",
                description="Delete an association between two HubSpot objects",
                inputSchema=association_handler.get_delete_association_schema(),
            ),

            # Engagement tools
            types.Tool(
                name="hubspot_create_note",
                description="Create a note and associate it with deals, contacts, companies, or tickets",
                inputSchema=engagement_handler.get_create_note_schema(),
            ),
            types.Tool(
                name="hubspot_create_meeting",
                description="Schedule a meeting and associate it with deals, contacts, companies, or tickets",
                inputSchema=engagement_handler.get_create_meeting_schema(),
            ),
            types.Tool(
                name="hubspot_create_call",
                description="Log a call and associate it with deals, contacts, companies, or tickets",
                inputSchema=engagement_handler.get_create_call_schema(),
            ),
            types.Tool(
                name="hubspot_create_task",
                description="Create a task and associate it with deals, contacts, companies, or tickets",
                inputSchema=engagement_handler.get_create_task_schema(),
            ),

            # Pipeline tools
            types.Tool(
                name="hubspot_get_pipelines",
                description="Get all pipelines for deals or tickets",
                inputSchema=pipeline_handler.get_pipelines_schema(),
            ),
            types.Tool(
                name="hubspot_get_pipeline",
                description="Get a specific pipeline with its stages",
                inputSchema=pipeline_handler.get_pipeline_schema(),
            ),
            types.Tool(
                name="hubspot_create_pipeline",
                description="Create a new pipeline with stages for deals or tickets",
                inputSchema=pipeline_handler.get_create_pipeline_schema(),
            ),
            types.Tool(
                name="hubspot_get_pipeline_stages",
                description="Get the ordered list of stages for a specific pipeline. Use this when you only need stage IDs and labels, without the full pipeline metadata returned by hubspot_get_pipeline.",
                inputSchema=pipeline_handler.get_pipeline_stages_schema(),
            ),
            types.Tool(
                name="hubspot_move_deal_stage",
                description="Move a deal to a different pipeline stage",
                inputSchema=pipeline_handler.get_move_deal_stage_schema(),
            ),

            # Property tools
            types.Tool(
                name="hubspot_get_property",
                description="Get details of a specific HubSpot property definition",
                inputSchema=property_handler.get_property_schema(),
            ),
            types.Tool(
                name="hubspot_update_property",
                description="Update a HubSpot property definition (e.g., add dropdown options)",
                inputSchema=property_handler.get_update_property_schema(),
            ),
            types.Tool(
                name="hubspot_create_property",
                description="Create a new custom property in HubSpot",
                inputSchema=property_handler.get_create_property_schema(),
            ),
        ]

def register_tool_call_handler(
    server: Server,
    company_handler: CompanyHandler,
    contact_handler: ContactHandler,
    conversation_handler: ConversationHandler,
    ticket_handler: TicketHandler,
    search_handler: SearchHandler,
    property_handler: PropertyHandler,
    deal_handler: DealHandler,
    association_handler: AssociationHandler,
    engagement_handler: EngagementHandler,
    pipeline_handler: PipelineHandler
) -> None:
    """Register tool call handler with the server.

    Args:
        server: MCP server instance
        company_handler: Handler for company operations
        contact_handler: Handler for contact operations
        conversation_handler: Handler for conversation operations
        ticket_handler: Handler for ticket operations
        search_handler: Handler for search operations
        property_handler: Handler for property operations
        deal_handler: Handler for deal operations
        association_handler: Handler for association operations
        engagement_handler: Handler for engagement operations
        pipeline_handler: Handler for pipeline operations
    """
    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool execution requests"""
        try:
            # Route to appropriate handler based on tool name
            if name == "hubspot_create_company":
                return company_handler.create_company(arguments)
            elif name == "hubspot_get_company_activity":
                return company_handler.get_company_activity(arguments)
            elif name == "hubspot_get_active_companies":
                return company_handler.get_active_companies(arguments)
            elif name == "hubspot_get_company":
                return company_handler.get_company(arguments)
            elif name == "hubspot_update_company":
                return company_handler.update_company(arguments)
            elif name == "hubspot_create_contact":
                return contact_handler.create_contact(arguments)
            elif name == "hubspot_get_active_contacts":
                return contact_handler.get_active_contacts(arguments)
            elif name == "hubspot_get_contact":
                return contact_handler.get_contact(arguments)
            elif name == "hubspot_update_contact":
                return contact_handler.update_contact(arguments)
            elif name == "hubspot_get_recent_conversations":
                return conversation_handler.get_recent_conversations(arguments)
            elif name == "hubspot_get_tickets":
                return ticket_handler.get_tickets(arguments)
            elif name == "hubspot_get_ticket_conversation_threads":
                return ticket_handler.get_ticket_conversation_threads(arguments)
            elif name == "hubspot_search_data":
                return search_handler.search_data(arguments)
            elif name == "hubspot_get_property":
                return property_handler.get_property(arguments)
            elif name == "hubspot_update_property":
                return property_handler.update_property(arguments)
            elif name == "hubspot_create_property":
                return property_handler.create_property(arguments)
            # Search tools
            elif name == "hubspot_search_contacts":
                return contact_handler.search_contacts(arguments)
            elif name == "hubspot_search_companies":
                return company_handler.search_companies(arguments)
            # Ticket CRUD
            elif name == "hubspot_create_ticket":
                return ticket_handler.create_ticket(arguments)
            elif name == "hubspot_update_ticket":
                return ticket_handler.update_ticket(arguments)
            elif name == "hubspot_get_ticket":
                return ticket_handler.get_ticket(arguments)
            # Deal tools
            elif name == "hubspot_create_deal":
                return deal_handler.create_deal(arguments)
            elif name == "hubspot_get_deal":
                return deal_handler.get_deal(arguments)
            elif name == "hubspot_update_deal":
                return deal_handler.update_deal(arguments)
            elif name == "hubspot_get_deals":
                return deal_handler.get_deals(arguments)
            elif name == "hubspot_search_deals":
                return deal_handler.search_deals(arguments)
            # Association tools
            elif name == "hubspot_create_association":
                return association_handler.create_association(arguments)
            elif name == "hubspot_get_associations":
                return association_handler.get_associations(arguments)
            elif name == "hubspot_delete_association":
                return association_handler.delete_association(arguments)
            # Engagement tools
            elif name == "hubspot_create_note":
                return engagement_handler.create_note(arguments)
            elif name == "hubspot_create_meeting":
                return engagement_handler.create_meeting(arguments)
            elif name == "hubspot_create_call":
                return engagement_handler.create_call(arguments)
            elif name == "hubspot_create_task":
                return engagement_handler.create_task(arguments)
            # Pipeline tools
            elif name == "hubspot_get_pipelines":
                return pipeline_handler.get_pipelines(arguments)
            elif name == "hubspot_get_pipeline":
                return pipeline_handler.get_pipeline(arguments)
            elif name == "hubspot_create_pipeline":
                return pipeline_handler.create_pipeline(arguments)
            elif name == "hubspot_get_pipeline_stages":
                return pipeline_handler.get_pipeline_stages(arguments)
            elif name == "hubspot_move_deal_stage":
                return pipeline_handler.move_deal_stage(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
        except ApiException as e:
            return [types.TextContent(type="text", text=f"HubSpot API error: {str(e)}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

if __name__ == "__main__":
    import asyncio
    import argparse
    
    parser = argparse.ArgumentParser(description="HubSpot MCP Server")
    parser.add_argument("--access-token", help="HubSpot API access token")
    
    args = parser.parse_args()
    
    # Load environment variables from .env file if it exists
    load_dotenv()
    
    asyncio.run(main(args.access_token))
