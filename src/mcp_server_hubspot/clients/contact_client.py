"""
Client for HubSpot contact-related operations.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.contacts import PublicObjectSearchRequest, SimplePublicObjectInputForCreate
from hubspot.crm.contacts.exceptions import ApiException

from ..core.formatters import convert_datetime_fields
from ..core.error_handler import handle_hubspot_errors

logger = logging.getLogger('mcp_hubspot_client.contact')

class ContactClient:
    """Client for HubSpot contact-related operations."""
    
    def __init__(self, hubspot_client: HubSpot, access_token: str):
        """Initialize with HubSpot client instance.
        
        Args:
            hubspot_client: Initialized HubSpot client
            access_token: HubSpot API access token
        """
        self.client = hubspot_client
        self.access_token = access_token
    
    @handle_hubspot_errors
    def get_recent(self, limit: int = 10) -> str:
        """Get most recently active contacts from HubSpot.

        Args:
            limit: Maximum number of contacts to return (default: 10)

        Returns:
            JSON string with contact data
        """
        search_request = self._create_contact_search_request(limit)
        search_response = self.client.crm.contacts.search_api.do_search(
            public_object_search_request=search_request
        )

        contacts_dict = [contact.to_dict() for contact in search_response.results]
        converted_contacts = convert_datetime_fields(contacts_dict)
        return json.dumps(converted_contacts)

    @handle_hubspot_errors
    def get_by_id(self, contact_id: str, properties: Optional[List[str]] = None) -> str:
        """Get a specific contact by ID from HubSpot.

        Args:
            contact_id: HubSpot contact ID
            properties: Optional list of properties to retrieve. If None, returns all properties.

        Returns:
            JSON string with contact data
        """
        contact = self.client.crm.contacts.basic_api.get_by_id(
            contact_id=contact_id,
            properties=properties,
            archived=False
        )

        contact_dict = contact.to_dict()
        converted_contact = convert_datetime_fields(contact_dict)
        return json.dumps(converted_contact)

    @handle_hubspot_errors
    def update(self, contact_id: str, properties: Dict[str, Any]) -> str:
        """Update a specific contact by ID in HubSpot.

        Args:
            contact_id: HubSpot contact ID
            properties: Dictionary of properties to update

        Returns:
            JSON string with updated contact data
        """
        from hubspot.crm.contacts import SimplePublicObjectInput

        simple_public_object_input = SimplePublicObjectInput(
            properties=properties
        )

        contact = self.client.crm.contacts.basic_api.update(
            contact_id=contact_id,
            simple_public_object_input=simple_public_object_input
        )

        contact_dict = contact.to_dict()
        converted_contact = convert_datetime_fields(contact_dict)
        return json.dumps(converted_contact)

    def _create_contact_search_request(self, limit: int) -> PublicObjectSearchRequest:
        """Create a search request for contacts sorted by last modified date.
        
        Args:
            limit: Maximum number of results to return
            
        Returns:
            Configured search request object
        """
        return PublicObjectSearchRequest(
            sorts=[{
                "propertyName": "lastmodifieddate",
                "direction": "DESCENDING"
            }],
            limit=limit,
            properties=["firstname", "lastname", "email", "phone", "company", 
                       "hs_lastmodifieddate", "lastmodifieddate"]
        )
    
    @handle_hubspot_errors
    def create_contact(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new contact in HubSpot.
        
        Args:
            properties: Contact properties including first name, last name, email, etc.
            
        Returns:
            Dictionary with the created contact or error information
        """
        # Check if contact already exists
        if "firstname" in properties and "lastname" in properties:
            existing_contact = self._find_existing_contact(
                properties["firstname"], 
                properties["lastname"],
                properties.get("company")
            )
            
            if existing_contact:
                return {"already_exists": True, "contact": existing_contact}
        
        # Create contact
        simple_public_object_input = SimplePublicObjectInputForCreate(
            properties=properties
        )
        
        api_response = self.client.crm.contacts.basic_api.create(
            simple_public_object_input_for_create=simple_public_object_input
        )
        
        return api_response.to_dict()
    
    @handle_hubspot_errors
    def search(
        self,
        filters: List[Dict[str, Any]],
        properties: Optional[List[str]] = None,
        limit: int = 10,
        sort_property: str = "lastmodifieddate"
    ) -> str:
        """Search contacts with custom filters.

        Args:
            filters: List of filter dicts with propertyName, operator, value
            properties: Optional list of properties to retrieve
            limit: Maximum number of results to return
            sort_property: Property to sort by

        Returns:
            JSON string with search results
        """
        search_request = PublicObjectSearchRequest(
            filter_groups=[{"filters": filters}],
            sorts=[{"propertyName": sort_property, "direction": "DESCENDING"}],
            limit=limit,
            properties=properties or ["firstname", "lastname", "email", "phone", "company",
                                       "hs_lastmodifieddate", "lastmodifieddate"]
        )
        search_response = self.client.crm.contacts.search_api.do_search(
            public_object_search_request=search_request
        )
        contacts_dict = [contact.to_dict() for contact in search_response.results]
        converted = convert_datetime_fields(contacts_dict)
        return json.dumps({
            "results": converted,
            "total": search_response.total
        })

    def _find_existing_contact(
        self, 
        firstname: str, 
        lastname: str, 
        company: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Search for an existing contact with the same name and company.
        
        Args:
            firstname: Contact's first name
            lastname: Contact's last name
            company: Contact's company (optional)
            
        Returns:
            Existing contact data if found, None otherwise
        """
        filter_group = {
            "filters": [
                {
                    "propertyName": "firstname",
                    "operator": "EQ",
                    "value": firstname
                },
                {
                    "propertyName": "lastname",
                    "operator": "EQ",
                    "value": lastname
                }
            ]
        }
        
        # Add company filter if provided
        if company:
            filter_group["filters"].append({
                "propertyName": "company",
                "operator": "EQ",
                "value": company
            })
        
        search_request = PublicObjectSearchRequest(
            filter_groups=[filter_group]
        )
        
        search_response = self.client.crm.contacts.search_api.do_search(
            public_object_search_request=search_request
        )
        
        if search_response.total > 0:
            return search_response.results[0].to_dict()
            
        return None
