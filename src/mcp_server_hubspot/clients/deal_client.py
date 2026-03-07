"""
Client for HubSpot deal-related operations.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.deals import PublicObjectSearchRequest, SimplePublicObjectInputForCreate, SimplePublicObjectInput
from hubspot.crm.contacts.exceptions import ApiException

from ..core.formatters import convert_datetime_fields
from ..core.error_handler import handle_hubspot_errors

logger = logging.getLogger('mcp_hubspot_client.deal')

DEFAULT_DEAL_PROPERTIES = [
    "dealname", "amount", "dealstage", "pipeline", "closedate",
    "hubspot_owner_id", "createdate", "hs_lastmodifieddate",
    "deal_currency_code", "description"
]


class DealClient:
    """Client for HubSpot deal-related operations."""

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
        """Get most recently modified deals from HubSpot.

        Args:
            limit: Maximum number of deals to return (default: 10)

        Returns:
            JSON string with deal data
        """
        search_request = PublicObjectSearchRequest(
            sorts=[{
                "propertyName": "hs_lastmodifieddate",
                "direction": "DESCENDING"
            }],
            limit=limit,
            properties=DEFAULT_DEAL_PROPERTIES
        )
        search_response = self.client.crm.deals.search_api.do_search(
            public_object_search_request=search_request
        )

        deals_dict = [deal.to_dict() for deal in search_response.results]
        converted = convert_datetime_fields(deals_dict)
        return json.dumps({
            "results": converted,
            "total": search_response.total
        })

    @handle_hubspot_errors
    def get_by_id(self, deal_id: str, properties: Optional[List[str]] = None) -> str:
        """Get a specific deal by ID from HubSpot.

        Args:
            deal_id: HubSpot deal ID
            properties: Optional list of properties to retrieve. If None, returns defaults.

        Returns:
            JSON string with deal data
        """
        deal = self.client.crm.deals.basic_api.get_by_id(
            deal_id=deal_id,
            properties=properties or DEFAULT_DEAL_PROPERTIES,
            archived=False
        )

        deal_dict = deal.to_dict()
        converted = convert_datetime_fields(deal_dict)
        return json.dumps(converted)

    @handle_hubspot_errors
    def create(self, properties: Dict[str, Any]) -> str:
        """Create a new deal in HubSpot.

        Args:
            properties: Deal properties (dealname, amount, dealstage, pipeline, etc.)

        Returns:
            JSON string with created deal data
        """
        simple_public_object_input = SimplePublicObjectInputForCreate(
            properties=properties
        )
        api_response = self.client.crm.deals.basic_api.create(
            simple_public_object_input_for_create=simple_public_object_input
        )
        deal_dict = api_response.to_dict()
        converted = convert_datetime_fields(deal_dict)
        return json.dumps(converted)

    @handle_hubspot_errors
    def update(self, deal_id: str, properties: Dict[str, Any]) -> str:
        """Update an existing deal in HubSpot.

        Args:
            deal_id: HubSpot deal ID
            properties: Dictionary of properties to update

        Returns:
            JSON string with updated deal data
        """
        simple_public_object_input = SimplePublicObjectInput(
            properties=properties
        )
        api_response = self.client.crm.deals.basic_api.update(
            deal_id=deal_id,
            simple_public_object_input=simple_public_object_input
        )
        deal_dict = api_response.to_dict()
        converted = convert_datetime_fields(deal_dict)
        return json.dumps(converted)

    @handle_hubspot_errors
    def search(
        self,
        filters: List[Dict[str, Any]],
        properties: Optional[List[str]] = None,
        limit: int = 10,
        sort_property: str = "hs_lastmodifieddate"
    ) -> str:
        """Search deals with custom filters.

        Args:
            filters: List of filter dicts with propertyName, operator, value
            properties: Optional list of properties to retrieve
            limit: Maximum number of results to return
            sort_property: Property to sort by (default: hs_lastmodifieddate)

        Returns:
            JSON string with search results
        """
        search_request = PublicObjectSearchRequest(
            filter_groups=[{"filters": filters}],
            sorts=[{"propertyName": sort_property, "direction": "DESCENDING"}],
            limit=limit,
            properties=properties or DEFAULT_DEAL_PROPERTIES
        )
        search_response = self.client.crm.deals.search_api.do_search(
            public_object_search_request=search_request
        )

        deals_dict = [deal.to_dict() for deal in search_response.results]
        converted = convert_datetime_fields(deals_dict)
        return json.dumps({
            "results": converted,
            "total": search_response.total
        })
