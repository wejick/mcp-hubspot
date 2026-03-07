"""
Handler for deal-related HubSpot operations.
"""
from typing import Any, Dict, List, Optional
import json

import mcp.types as types

from .base_handler import BaseHandler


class DealHandler(BaseHandler):
    """Handler for deal-related HubSpot tools."""

    def __init__(self, hubspot_client, faiss_manager, embedding_model):
        super().__init__(hubspot_client, faiss_manager, embedding_model, "deal_handler")

    def get_create_deal_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dealname": {"type": "string", "description": "Name of the deal"},
                "amount": {"type": "string", "description": "Deal amount (as string)"},
                "dealstage": {"type": "string", "description": "Deal stage ID"},
                "pipeline": {"type": "string", "description": "Pipeline ID (default: 'default')"},
                "closedate": {"type": "string", "description": "Expected close date (ISO 8601)"},
                "hubspot_owner_id": {"type": "string", "description": "HubSpot owner ID"},
                "properties": {"type": "object", "description": "Additional deal properties"}
            },
            "required": ["dealname"]
        }

    def get_deal_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "HubSpot deal ID"},
                "properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of properties to retrieve"
                }
            },
            "required": ["deal_id"]
        }

    def get_update_deal_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "HubSpot deal ID to update"},
                "properties": {
                    "type": "object",
                    "description": "Object containing the properties to update"
                }
            },
            "required": ["deal_id", "properties"]
        }

    def get_deals_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of deals to return (default: 10)"}
            }
        }

    def get_search_deals_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "description": "List of filter conditions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "propertyName": {"type": "string", "description": "Property to filter on"},
                            "operator": {
                                "type": "string",
                                "enum": ["EQ", "NEQ", "LT", "LTE", "GT", "GTE", "CONTAINS_TOKEN", "HAS_PROPERTY"],
                                "description": "Filter operator"
                            },
                            "value": {"type": "string", "description": "Filter value"}
                        },
                        "required": ["propertyName", "operator"]
                    }
                },
                "properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of properties to retrieve"
                },
                "limit": {"type": "integer", "description": "Maximum number of results to return (default: 10)"},
                "sort_property": {"type": "string", "description": "Property to sort by (default: hs_lastmodifieddate)"}
            },
            "required": ["filters"]
        }

    def create_deal(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["dealname"])

        properties = {"dealname": arguments["dealname"]}
        for field in ["amount", "dealstage", "pipeline", "closedate", "hubspot_owner_id"]:
            if field in arguments:
                properties[field] = arguments[field]
        if "properties" in arguments:
            properties.update(arguments["properties"])

        results = self.hubspot.deals.create(properties)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely([data], "deal", {"action": "created"})
        except Exception as e:
            self.logger.error(f"Error storing deal in FAISS: {str(e)}")

        return self.create_text_response(results)

    def get_deal(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["deal_id"])

        deal_id = arguments["deal_id"]
        properties = arguments.get("properties")

        results = self.hubspot.deals.get_by_id(deal_id, properties)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely([data], "deal", {"deal_id": deal_id})
        except Exception as e:
            self.logger.error(f"Error storing deal in FAISS: {str(e)}")

        return self.create_text_response(results)

    def update_deal(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["deal_id", "properties"])

        deal_id = arguments["deal_id"]
        properties = arguments["properties"]

        results = self.hubspot.deals.update(deal_id, properties)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely([data], "deal", {"deal_id": deal_id, "updated": True})
        except Exception as e:
            self.logger.error(f"Error storing deal in FAISS: {str(e)}")

        return self.create_text_response(results)

    def get_deals(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        limit = self.get_argument_with_default(arguments, "limit", 10)
        limit = int(limit) if limit is not None else 10

        results = self.hubspot.deals.get_recent(limit)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(data.get("results", []), "deal", {"limit": limit})
        except Exception as e:
            self.logger.error(f"Error storing deals in FAISS: {str(e)}")

        return self.create_text_response(results)

    def search_deals(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["filters"])

        filters = arguments["filters"]
        properties = arguments.get("properties")
        limit = int(self.get_argument_with_default(arguments, "limit", 10) or 10)
        sort_property = self.get_argument_with_default(arguments, "sort_property", "hs_lastmodifieddate")

        results = self.hubspot.deals.search(filters, properties, limit, sort_property)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(data.get("results", []), "deal", {"filters": filters})
        except Exception as e:
            self.logger.error(f"Error storing deal search results in FAISS: {str(e)}")

        return self.create_text_response(results)
