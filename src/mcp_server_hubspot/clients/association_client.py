"""
Client for HubSpot association-related operations.
"""
import json
import logging
import requests
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException

from ..core.error_handler import handle_hubspot_errors

logger = logging.getLogger('mcp_hubspot_client.association')

# Supported object types for association API
VALID_OBJECT_TYPES = ["contacts", "companies", "deals", "tickets"]


class AssociationClient:
    """Client for HubSpot association-related operations."""

    def __init__(self, hubspot_client: HubSpot, access_token: str):
        """Initialize with HubSpot client instance.

        Args:
            hubspot_client: Initialized HubSpot client
            access_token: HubSpot API access token
        """
        self.client = hubspot_client
        self.access_token = access_token
        self._headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }

    @handle_hubspot_errors
    def create_association(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
        association_type: Optional[str] = None
    ) -> str:
        """Create an association between two HubSpot objects.

        Args:
            from_object_type: Type of the source object (e.g. 'contacts', 'companies')
            from_object_id: ID of the source object
            to_object_type: Type of the target object
            to_object_id: ID of the target object
            association_type: Optional association type label (e.g. 'contact_to_company')

        Returns:
            JSON string with the created association result
        """
        url = (
            f"https://api.hubapi.com/crm/v4/objects/{from_object_type}/"
            f"{from_object_id}/associations/{to_object_type}/{to_object_id}"
        )

        # Build association type spec - use default association type if not specified
        if association_type:
            body = [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": association_type}]
        else:
            # Use default association type (category=HUBSPOT_DEFINED, typeId=1 means generic association)
            body = [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1}]

        response = requests.put(url, headers=self._headers, json=body, timeout=30)
        response.raise_for_status()

        return json.dumps({
            "success": True,
            "from_object_type": from_object_type,
            "from_object_id": from_object_id,
            "to_object_type": to_object_type,
            "to_object_id": to_object_id,
            "result": response.json() if response.text else {}
        })

    @handle_hubspot_errors
    def get_associations(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str
    ) -> str:
        """Get all associations of a specific type for a given object.

        Args:
            from_object_type: Type of the source object
            from_object_id: ID of the source object
            to_object_type: Type of associated objects to retrieve

        Returns:
            JSON string with associated object IDs and types
        """
        url = (
            f"https://api.hubapi.com/crm/v4/objects/{from_object_type}/"
            f"{from_object_id}/associations/{to_object_type}"
        )

        response = requests.get(url, headers=self._headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        return json.dumps({
            "from_object_type": from_object_type,
            "from_object_id": from_object_id,
            "to_object_type": to_object_type,
            "results": data.get("results", []),
            "total": len(data.get("results", []))
        })

    @handle_hubspot_errors
    def delete_association(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str
    ) -> str:
        """Delete an association between two HubSpot objects.

        Args:
            from_object_type: Type of the source object
            from_object_id: ID of the source object
            to_object_type: Type of the target object
            to_object_id: ID of the target object

        Returns:
            JSON string confirming deletion
        """
        url = (
            f"https://api.hubapi.com/crm/v4/objects/{from_object_type}/"
            f"{from_object_id}/associations/{to_object_type}/{to_object_id}"
        )

        response = requests.delete(url, headers=self._headers, timeout=30)
        response.raise_for_status()

        return json.dumps({
            "success": True,
            "from_object_type": from_object_type,
            "from_object_id": from_object_id,
            "to_object_type": to_object_type,
            "to_object_id": to_object_id
        })
