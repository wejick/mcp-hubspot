"""
Client for HubSpot engagement operations (notes, meetings, calls, tasks).
Uses CRM Objects API v3.
"""
import json
import logging
import requests
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException

from ..core.formatters import convert_datetime_fields
from ..core.error_handler import handle_hubspot_errors

logger = logging.getLogger('mcp_hubspot_client.engagement')

# HubSpot default association type IDs (HUBSPOT_DEFINED category)
ASSOCIATION_TYPE_IDS = {
    "note": {
        "contacts": 202,
        "companies": 190,
        "deals": 214,
        "tickets": 219,
    },
    "meeting": {
        "contacts": 200,
        "companies": 188,
        "deals": 212,
        "tickets": 217,
    },
    "call": {
        "contacts": 194,
        "companies": 182,
        "deals": 206,
        "tickets": 211,
    },
    "task": {
        "contacts": 204,
        "companies": 192,
        "deals": 216,
        "tickets": 221,
    },
}

BASE_URL = "https://api.hubapi.com/crm/v3/objects"


class EngagementClient:
    """Client for HubSpot engagement operations."""

    def __init__(self, hubspot_client: HubSpot, access_token: str):
        self.client = hubspot_client
        self.access_token = access_token
        self._headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }

    def _build_associations(
        self,
        engagement_type: str,
        associations: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Build the associations array for an engagement creation request.

        Args:
            engagement_type: Type of engagement (note, meeting, call, task)
            associations: List of dicts with 'object_type' and 'object_id'

        Returns:
            Formatted associations list for the API request
        """
        result = []
        type_map = ASSOCIATION_TYPE_IDS.get(engagement_type, {})
        for assoc in associations:
            obj_type = assoc.get("object_type", "").lower()
            obj_id = assoc.get("object_id", "")
            type_id = type_map.get(obj_type)
            if obj_id and type_id:
                result.append({
                    "to": {"id": obj_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}]
                })
        return result

    def _create_engagement(
        self,
        engagement_type: str,
        properties: Dict[str, Any],
        associations: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Create an engagement object via CRM v3 API.

        Args:
            engagement_type: 'notes', 'meetings', 'calls', or 'tasks'
            properties: Engagement properties
            associations: Optional list of {object_type, object_id} dicts

        Returns:
            JSON string with created engagement data
        """
        url = f"{BASE_URL}/{engagement_type}"
        body: Dict[str, Any] = {"properties": properties}

        if associations:
            # engagement_type is plural (notes/meetings/calls/tasks), strip 's' for type map
            singular = engagement_type.rstrip("s")
            assoc_list = self._build_associations(singular, associations)
            if assoc_list:
                body["associations"] = assoc_list

        response = requests.post(url, headers=self._headers, json=body, timeout=30)
        response.raise_for_status()

        data = response.json()
        converted = convert_datetime_fields(data)
        return json.dumps(converted)

    @handle_hubspot_errors
    def create_note(
        self,
        body: str,
        associations: Optional[List[Dict[str, str]]] = None,
        timestamp: Optional[str] = None
    ) -> str:
        """Create a note and optionally associate it with deals/contacts/companies/tickets.

        Args:
            body: Note content
            associations: List of {object_type, object_id} to associate with
            timestamp: Optional ISO 8601 timestamp (defaults to now)

        Returns:
            JSON string with created note data
        """
        properties: Dict[str, Any] = {"hs_note_body": body}
        if timestamp:
            properties["hs_timestamp"] = timestamp

        return self._create_engagement("notes", properties, associations)

    @handle_hubspot_errors
    def create_meeting(
        self,
        title: str,
        start_time: str,
        end_time: str,
        body: Optional[str] = None,
        outcome: Optional[str] = None,
        associations: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Create a meeting engagement.

        Args:
            title: Meeting title
            start_time: Meeting start time (ISO 8601 millisecond timestamp or datetime string)
            end_time: Meeting end time (ISO 8601 millisecond timestamp or datetime string)
            body: Meeting description/notes
            outcome: Meeting outcome (SCHEDULED, COMPLETED, RESCHEDULED, NO_SHOW, CANCELLED)
            associations: List of {object_type, object_id} to associate with

        Returns:
            JSON string with created meeting data
        """
        properties: Dict[str, Any] = {
            "hs_meeting_title": title,
            "hs_meeting_start_time": start_time,
            "hs_meeting_end_time": end_time,
        }
        if body:
            properties["hs_meeting_body"] = body
        if outcome:
            properties["hs_meeting_outcome"] = outcome

        return self._create_engagement("meetings", properties, associations)

    @handle_hubspot_errors
    def create_call(
        self,
        body: str,
        duration_ms: Optional[int] = None,
        disposition: Optional[str] = None,
        status: Optional[str] = None,
        associations: Optional[List[Dict[str, str]]] = None,
        timestamp: Optional[str] = None
    ) -> str:
        """Create a call engagement.

        Args:
            body: Call notes/description
            duration_ms: Call duration in milliseconds
            disposition: Call outcome disposition ID
            status: Call status (COMPLETED, IN_PROGRESS, MISSED, etc.)
            associations: List of {object_type, object_id} to associate with
            timestamp: Optional ISO 8601 timestamp for when the call occurred

        Returns:
            JSON string with created call data
        """
        properties: Dict[str, Any] = {"hs_call_body": body}
        if duration_ms is not None:
            properties["hs_call_duration"] = str(duration_ms)
        if disposition:
            properties["hs_call_disposition"] = disposition
        if status:
            properties["hs_call_status"] = status
        if timestamp:
            properties["hs_timestamp"] = timestamp

        return self._create_engagement("calls", properties, associations)

    @handle_hubspot_errors
    def create_task(
        self,
        subject: str,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        associations: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Create a task engagement.

        Args:
            subject: Task title/subject
            body: Task notes/description
            due_date: Task due date (ISO 8601)
            priority: Task priority (LOW, MEDIUM, HIGH)
            status: Task status (NOT_STARTED, IN_PROGRESS, COMPLETED, DEFERRED, WAITING)
            associations: List of {object_type, object_id} to associate with

        Returns:
            JSON string with created task data
        """
        properties: Dict[str, Any] = {
            "hs_task_subject": subject,
            "hs_task_status": status or "NOT_STARTED"
        }
        if body:
            properties["hs_task_body"] = body
        if due_date:
            properties["hs_task_due_date"] = due_date
        if priority:
            properties["hs_task_priority"] = priority

        return self._create_engagement("tasks", properties, associations)
