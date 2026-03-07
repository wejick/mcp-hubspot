"""
Handler for company-related HubSpot operations.
"""
from typing import Any, Dict, List, Optional
import json

import mcp.types as types

from ..hubspot_client import HubSpotClient, ApiException
from ..faiss_manager import FaissManager
from .base_handler import BaseHandler

class CompanyHandler(BaseHandler):
    """Handler for company-related HubSpot tools."""
    
    def __init__(self, hubspot_client, faiss_manager, embedding_model):
        """Initialize the company handler.
        
        Args:
            hubspot_client: HubSpot client
            faiss_manager: FAISS vector store manager
            embedding_model: Sentence transformer model
        """
        super().__init__(hubspot_client, faiss_manager, embedding_model, "company_handler")
    
    def get_create_company_schema(self) -> Dict[str, Any]:
        """Get the input schema for creating a company.
        
        Returns:
            Schema definition dictionary
        """
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Company name"},
                "properties": {"type": "object", "description": "Additional company properties"}
            },
            "required": ["name"]
        }
    
    def get_company_activity_schema(self) -> Dict[str, Any]:
        """Get the input schema for company activity.
        
        Returns:
            Schema definition dictionary
        """
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "HubSpot company ID"}
            },
            "required": ["company_id"]
        }
    
    def get_active_companies_schema(self) -> Dict[str, Any]:
        """Get the input schema for active companies.

        Returns:
            Schema definition dictionary
        """
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of companies to return (default: 10)"}
            }
        }

    def get_company_schema(self) -> Dict[str, Any]:
        """Get the input schema for getting a company by ID.

        Returns:
            Schema definition dictionary
        """
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "HubSpot company ID"},
                "properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of properties to retrieve. If omitted, returns all properties."
                }
            },
            "required": ["company_id"]
        }

    def get_search_companies_schema(self) -> Dict[str, Any]:
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
                "sort_property": {"type": "string", "description": "Property to sort by (default: lastmodifieddate)"}
            },
            "required": ["filters"]
        }

    def get_update_company_schema(self) -> Dict[str, Any]:
        """Get the input schema for updating a company by ID.

        Returns:
            Schema definition dictionary
        """
        return {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "HubSpot company ID to update"},
                "properties": {
                    "type": "object",
                    "description": "Object containing the properties to update"
                }
            },
            "required": ["company_id", "properties"]
        }

    def create_company(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        """Create a new company in HubSpot.
        
        Args:
            arguments: Tool arguments containing company information
            
        Returns:
            Text response with result
        """
        self.validate_required_arguments(arguments, ["name"])
        
        try:
            from hubspot.crm.companies import PublicObjectSearchRequest
            
            company_name = arguments["name"]
            
            # Search for existing companies with same name
            search_request = PublicObjectSearchRequest(
                filter_groups=[{
                    "filters": [
                        {
                            "propertyName": "name",
                            "operator": "EQ",
                            "value": company_name
                        }
                    ]
                }]
            )
            
            search_response = self.hubspot.client.crm.companies.search_api.do_search(
                public_object_search_request=search_request
            )
            
            if search_response.total > 0:
                # Company already exists
                return self.create_text_response(
                    f"Company already exists: {search_response.results[0].to_dict()}"
                )
            
            # If no existing company found, proceed with creation
            properties = {
                "name": company_name
            }
            
            # Add any additional properties
            if "properties" in arguments:
                properties.update(arguments["properties"])
            
            # Create company using SimplePublicObjectInputForCreate
            from hubspot.crm.companies import SimplePublicObjectInputForCreate
            
            simple_public_object_input = SimplePublicObjectInputForCreate(
                properties=properties
            )
            
            api_response = self.hubspot.client.crm.companies.basic_api.create(
                simple_public_object_input_for_create=simple_public_object_input
            )
            return self.create_text_response(str(api_response.to_dict()))
                
        except ApiException as e:
            return self.create_text_response(f"HubSpot API error: {str(e)}")
        except Exception as e:
            return self.create_text_response(f"Error: {str(e)}")
    
    def get_company_activity(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        """Get activity history for a specific company.
        
        Args:
            arguments: Tool arguments containing company ID
            
        Returns:
            Text response with company activity data
        """
        self.validate_required_arguments(arguments, ["company_id"])
        
        results = self.hubspot.get_company_activity(arguments["company_id"])
        
        # Store in FAISS for future reference
        try:
            data = json.loads(results)
            metadata_extras = {"company_id": arguments["company_id"]}
            self.store_in_faiss_safely(data, "company_activity", metadata_extras)
        except Exception as e:
            self.logger.error(f"Error parsing company activity data: {str(e)}")
        
        return self.create_text_response(results)
    
    def get_active_companies(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        """Get most recently active companies from HubSpot.

        Args:
            arguments: Tool arguments containing limit parameter

        Returns:
            Text response with company data
        """
        limit = self.get_argument_with_default(arguments, "limit", 10)

        # Ensure limit is an integer
        limit = int(limit) if limit is not None else 10

        results = self.hubspot.get_recent_companies(limit=limit)

        # Store in FAISS for future reference
        try:
            data = json.loads(results)
            metadata_extras = {"limit": limit}
            self.store_in_faiss_safely(data, "company", metadata_extras)
        except Exception as e:
            self.logger.error(f"Error parsing company data: {str(e)}")

        return self.create_text_response(results)

    def get_company(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        """Get a specific company by ID from HubSpot.

        Args:
            arguments: Tool arguments containing company_id and optional properties

        Returns:
            Text response with company data
        """
        self.validate_required_arguments(arguments, ["company_id"])

        company_id = arguments["company_id"]
        properties = arguments.get("properties")

        results = self.hubspot.get_company_by_id(company_id, properties)

        # Store in FAISS for future reference
        try:
            data = json.loads(results)
            metadata_extras = {"company_id": company_id}
            self.store_in_faiss_safely(data, "company", metadata_extras)
        except Exception as e:
            self.logger.error(f"Error parsing company data: {str(e)}")

        return self.create_text_response(results)

    def search_companies(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        self.validate_required_arguments(arguments, ["filters"])

        filters = arguments["filters"]
        properties = arguments.get("properties")
        limit = int(self.get_argument_with_default(arguments, "limit", 10) or 10)
        sort_property = self.get_argument_with_default(arguments, "sort_property", "lastmodifieddate")

        results = self.hubspot.companies.search(filters, properties, limit, sort_property)

        try:
            data = json.loads(results)
            self.store_in_faiss_safely(data.get("results", []), "company", {"filters": filters})
        except Exception as e:
            self.logger.error(f"Error storing company search results in FAISS: {str(e)}")

        return self.create_text_response(results)

    def update_company(self, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        """Update a specific company by ID in HubSpot.

        Args:
            arguments: Tool arguments containing company_id and properties to update

        Returns:
            Text response with updated company data
        """
        self.validate_required_arguments(arguments, ["company_id", "properties"])

        company_id = arguments["company_id"]
        properties = arguments["properties"]

        results = self.hubspot.update_company(company_id, properties)

        # Store in FAISS for future reference
        try:
            data = json.loads(results)
            metadata_extras = {"company_id": company_id, "updated": True}
            self.store_in_faiss_safely(data, "company", metadata_extras)
        except Exception as e:
            self.logger.error(f"Error parsing updated company data: {str(e)}")

        return self.create_text_response(results)
