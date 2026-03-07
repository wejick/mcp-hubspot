"""
Handler for HubSpot pipeline operations and deal stage transitions.
"""
from typing import Any, Dict, List, Optional
import json

import mcp.types as types

from .base_handler import BaseHandler

OBJECT_TYPE_ENUM = ["deals", "tickets"]


class PipelineHandler(BaseHandler):
    """Handler for HubSpot pipeline and stage tools."""

    def __init__(self, hubspot_client, faiss_manager, embedding_model):
        super().__init__(hubspot_client, faiss_manager, embedding_model, "pipeline_handler")

    # --- Schemas ---

    def get_pipelines_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Object type to get pipelines for"
                }
            },
            "required": ["object_type"]
        }

    def get_pipeline_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Object type ('deals' or 'tickets')"
                },
                "pipeline_id": {"type": "string", "description": "Pipeline ID"}
            },
            "required": ["object_type", "pipeline_id"]
        }

    def get_create_pipeline_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Object type for the new pipeline"
                },
                "label": {"type": "string", "description": "Pipeline display name"},
                "stages": {
                    "type": "array",
                    "description": "Ordered list of pipeline stages",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Stage display name"},
                            "probability": {
                                "type": "number",
                                "description": "Win probability for deal stages (0.0 to 1.0)"
                            },
                            "ticket_state": {
                                "type": "string",
                                "enum": ["OPEN", "CLOSED"],
                                "description": "State for ticket stages"
                            }
                        },
                        "required": ["label"]
                    }
                }
            },
            "required": ["object_type", "label", "stages"]
        }

    def get_pipeline_stages_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": OBJECT_TYPE_ENUM,
                    "description": "Object type ('deals' or 'tickets')"
                },
                "pipeline_id": {"type": "string", "description": "Pipeline ID"}
            },
            "required": ["object_type", "pipeline_id"]
        }

    def get_move_deal_stage_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "HubSpot deal ID"},
                "stage_id": {"type": "string", "description": "Target pipeline stage ID"},
                "pipeline_id": {
                    "type": "string",
                    "description": "Pipeline ID to move to (optional, only needed when changing pipelines)"
                }
            },
            "required": ["deal_id", "stage_id"]
        }

    # --- Actions ---

    def get_pipelines(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["object_type"])

        results = self.hubspot.pipelines.get_pipelines(arguments["object_type"])

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                data.get("results", []), "pipeline",
                {"object_type": arguments["object_type"]}
            )
        except Exception as e:
            self.logger.error(f"Error storing pipelines in FAISS: {str(e)}")

        return self.create_text_response(results)

    def get_pipeline(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["object_type", "pipeline_id"])

        results = self.hubspot.pipelines.get_pipeline(
            arguments["object_type"], arguments["pipeline_id"]
        )

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                [data], "pipeline",
                {"object_type": arguments["object_type"], "pipeline_id": arguments["pipeline_id"]}
            )
        except Exception as e:
            self.logger.error(f"Error storing pipeline in FAISS: {str(e)}")

        return self.create_text_response(results)

    def create_pipeline(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["object_type", "label", "stages"])

        results = self.hubspot.pipelines.create_pipeline(
            object_type=arguments["object_type"],
            label=arguments["label"],
            stages=arguments["stages"]
        )

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                [data], "pipeline",
                {"object_type": arguments["object_type"], "label": arguments["label"]}
            )
        except Exception as e:
            self.logger.error(f"Error storing pipeline in FAISS: {str(e)}")

        return self.create_text_response(results)

    def get_pipeline_stages(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["object_type", "pipeline_id"])

        results = self.hubspot.pipelines.get_pipeline_stages(
            arguments["object_type"], arguments["pipeline_id"]
        )

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                data.get("results", []), "pipeline_stage",
                {"object_type": arguments["object_type"], "pipeline_id": arguments["pipeline_id"]}
            )
        except Exception as e:
            self.logger.error(f"Error storing pipeline stages in FAISS: {str(e)}")

        return self.create_text_response(results)

    def move_deal_stage(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["deal_id", "stage_id"])

        deal_id = arguments["deal_id"]
        properties: Dict[str, str] = {"dealstage": arguments["stage_id"]}
        if "pipeline_id" in arguments:
            properties["pipeline"] = arguments["pipeline_id"]

        results = self.hubspot.deals.update(deal_id, properties)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(
                [data], "deal",
                {"deal_id": deal_id, "stage_id": arguments["stage_id"], "action": "stage_moved"}
            )
        except Exception as e:
            self.logger.error(f"Error storing deal stage move in FAISS: {str(e)}")

        return self.create_text_response(results)
