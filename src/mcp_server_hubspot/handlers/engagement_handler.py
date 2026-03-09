"""
Handler for HubSpot engagement operations (notes, meetings, calls, tasks).
"""
from typing import Any, Dict, List, Optional
import json

import mcp.types as types

from .base_handler import BaseHandler

OBJECT_TYPE_ENUM = ["contacts", "companies", "deals", "tickets"]

_ASSOCIATION_SCHEMA = {
    "type": "array",
    "description": "Objects to associate this engagement with",
    "items": {
        "type": "object",
        "properties": {
            "object_type": {
                "type": "string",
                "enum": OBJECT_TYPE_ENUM,
                "description": "Type of object to associate with"
            },
            "object_id": {"type": "string", "description": "ID of the object"}
        },
        "required": ["object_type", "object_id"]
    }
}


class EngagementHandler(BaseHandler):
    """Handler for HubSpot engagement tools."""

    def __init__(self, hubspot_client, faiss_manager, embedding_model):
        super().__init__(hubspot_client, faiss_manager, embedding_model, "engagement_handler")

    # --- Schemas ---

    def get_create_note_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "Note content"},
                "timestamp": {"type": "string", "description": "When the note was created (ISO 8601, defaults to now)"},
                "associations": _ASSOCIATION_SCHEMA
            },
            "required": ["body"]
        }

    def get_create_meeting_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Meeting title"},
                "start_time": {"type": "string", "description": "Meeting start time (ISO 8601)"},
                "end_time": {"type": "string", "description": "Meeting end time (ISO 8601)"},
                "body": {"type": "string", "description": "Meeting description or agenda"},
                "outcome": {
                    "type": "string",
                    "enum": ["SCHEDULED", "COMPLETED", "RESCHEDULED", "NO_SHOW", "CANCELLED"],
                    "description": "Meeting outcome"
                },
                "associations": _ASSOCIATION_SCHEMA
            },
            "required": ["title", "start_time", "end_time"]
        }

    def get_create_call_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "Call notes or description"},
                "duration_ms": {"type": "integer", "description": "Call duration in milliseconds"},
                "status": {
                    "type": "string",
                    "enum": ["COMPLETED", "MISSED", "CANCELLED", "IN_PROGRESS"],
                    "description": "Call status"
                },
                "timestamp": {"type": "string", "description": "When the call occurred (ISO 8601)"},
                "associations": _ASSOCIATION_SCHEMA
            },
            "required": ["body"]
        }

    def get_create_task_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Task subject/title"},
                "body": {"type": "string", "description": "Task description or notes"},
                "due_date": {"type": "string", "description": "Task due date (ISO 8601)"},
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH"],
                    "description": "Task priority"
                },
                "status": {
                    "type": "string",
                    "enum": ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "DEFERRED", "WAITING"],
                    "description": "Task status (default: NOT_STARTED)"
                },
                "associations": _ASSOCIATION_SCHEMA
            },
            "required": ["subject"]
        }

    # --- Actions ---

    def create_note(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["body"])

        results = self.hubspot.engagements.create_note(
            body=arguments["body"],
            associations=arguments.get("associations"),
            timestamp=arguments.get("timestamp")
        )

        try:
            data = json.loads(results)
            self.store_safely([data], "note", {"associations": arguments.get("associations", [])})
        except Exception as e:
            self.logger.error(f"Error storing note in FAISS: {str(e)}")

        return self.create_text_response(results)

    def create_meeting(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["title", "start_time", "end_time"])

        results = self.hubspot.engagements.create_meeting(
            title=arguments["title"],
            start_time=arguments["start_time"],
            end_time=arguments["end_time"],
            body=arguments.get("body"),
            outcome=arguments.get("outcome"),
            associations=arguments.get("associations")
        )

        try:
            data = json.loads(results)
            self.store_safely([data], "meeting", {"associations": arguments.get("associations", [])})
        except Exception as e:
            self.logger.error(f"Error storing meeting in FAISS: {str(e)}")

        return self.create_text_response(results)

    def create_call(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["body"])

        duration_ms = arguments.get("duration_ms")
        if duration_ms is not None:
            duration_ms = int(duration_ms)

        results = self.hubspot.engagements.create_call(
            body=arguments["body"],
            duration_ms=duration_ms,
            disposition=arguments.get("disposition"),
            status=arguments.get("status"),
            associations=arguments.get("associations"),
            timestamp=arguments.get("timestamp")
        )

        try:
            data = json.loads(results)
            self.store_safely([data], "call", {"associations": arguments.get("associations", [])})
        except Exception as e:
            self.logger.error(f"Error storing call in FAISS: {str(e)}")

        return self.create_text_response(results)

    def create_task(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["subject"])

        results = self.hubspot.engagements.create_task(
            subject=arguments["subject"],
            body=arguments.get("body"),
            due_date=arguments.get("due_date"),
            priority=arguments.get("priority"),
            status=arguments.get("status"),
            associations=arguments.get("associations")
        )

        try:
            data = json.loads(results)
            self.store_safely([data], "task", {"associations": arguments.get("associations", [])})
        except Exception as e:
            self.logger.error(f"Error storing task in FAISS: {str(e)}")

        return self.create_text_response(results)
