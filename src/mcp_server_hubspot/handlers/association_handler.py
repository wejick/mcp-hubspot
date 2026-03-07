"""
Handler for HubSpot association operations.
"""
from typing import Any, Dict, List, Optional
import json

import mcp.types as types

from .base_handler import BaseHandler

OBJECT_TYPE_ENUM = ["contacts", "companies", "deals", "tickets"]


class AssociationHandler(BaseHandler):
    """Handler for HubSpot association tools."""

    def __init__(self, hubspot_client, faiss_manager, embedding_model):
        super().__init__(hubspot_client, faiss_manager, embedding_model, "association_handler")

    def get_create_association_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of the source object"
                },
                "from_object_id": {"type": "string", "description": "ID of the source object"},
                "to_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of the target object"
                },
                "to_object_id": {"type": "string", "description": "ID of the target object"},
                "association_type": {
                    "type": "string",
                    "description": "Numeric association type ID as a string (optional). Omit to use the default generic association. Use hubspot_get_associations to discover existing type IDs."
                }
            },
            "required": ["from_object_type", "from_object_id", "to_object_type", "to_object_id"]
        }

    def get_associations_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of the source object"
                },
                "from_object_id": {"type": "string", "description": "ID of the source object"},
                "to_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of associated objects to retrieve"
                }
            },
            "required": ["from_object_type", "from_object_id", "to_object_type"]
        }

    def get_delete_association_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of the source object"
                },
                "from_object_id": {"type": "string", "description": "ID of the source object"},
                "to_object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Type of the target object"
                },
                "to_object_id": {"type": "string", "description": "ID of the target object"}
            },
            "required": ["from_object_type", "from_object_id", "to_object_type", "to_object_id"]
        }

    def create_association(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(
            arguments, ["from_object_type", "from_object_id", "to_object_type", "to_object_id"]
        )

        results = self.hubspot.associations.create_association(
            from_object_type=arguments["from_object_type"],
            from_object_id=arguments["from_object_id"],
            to_object_type=arguments["to_object_type"],
            to_object_id=arguments["to_object_id"],
            association_type=arguments.get("association_type")
        )

        return self.create_text_response(results)

    def get_associations(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(
            arguments, ["from_object_type", "from_object_id", "to_object_type"]
        )

        results = self.hubspot.associations.get_associations(
            from_object_type=arguments["from_object_type"],
            from_object_id=arguments["from_object_id"],
            to_object_type=arguments["to_object_type"]
        )

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                data.get("results", []),
                "association",
                {
                    "from_object_type": arguments["from_object_type"],
                    "from_object_id": arguments["from_object_id"],
                    "to_object_type": arguments["to_object_type"]
                }
            )
        except Exception as e:
            self.logger.error(f"Error storing associations in FAISS: {str(e)}")

        return self.create_text_response(results)

    def delete_association(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(
            arguments, ["from_object_type", "from_object_id", "to_object_type", "to_object_id"]
        )

        results = self.hubspot.associations.delete_association(
            from_object_type=arguments["from_object_type"],
            from_object_id=arguments["from_object_id"],
            to_object_type=arguments["to_object_type"],
            to_object_id=arguments["to_object_id"]
        )

        return self.create_text_response(results)
