"""
Client for HubSpot pipeline operations.
Supports deal and ticket pipelines.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException

from ..core.formatters import convert_datetime_fields
from ..core.error_handler import handle_hubspot_errors

logger = logging.getLogger('mcp_hubspot_client.pipeline')

VALID_OBJECT_TYPES = ["deals", "tickets"]


class PipelineClient:
    """Client for HubSpot pipeline operations."""

    def __init__(self, hubspot_client: HubSpot, access_token: str):
        self.client = hubspot_client
        self.access_token = access_token

    @handle_hubspot_errors
    def get_pipelines(self, object_type: str) -> str:
        """Get all pipelines for a given object type.

        Args:
            object_type: 'deals' or 'tickets'

        Returns:
            JSON string with pipeline list including stages
        """
        response = self.client.crm.pipelines.pipelines_api.get_all(
            object_type=object_type
        )
        pipelines = [p.to_dict() for p in response.results]
        converted = convert_datetime_fields(pipelines)
        return json.dumps({
            "object_type": object_type,
            "results": converted,
            "total": len(converted)
        })

    @handle_hubspot_errors
    def get_pipeline(self, object_type: str, pipeline_id: str) -> str:
        """Get a specific pipeline with its stages.

        Args:
            object_type: 'deals' or 'tickets'
            pipeline_id: Pipeline ID

        Returns:
            JSON string with pipeline details and stages
        """
        pipeline = self.client.crm.pipelines.pipelines_api.get_by_id(
            object_type=object_type,
            pipeline_id=pipeline_id
        )
        pipeline_dict = pipeline.to_dict()

        # Also fetch stages
        stages_response = self.client.crm.pipelines.pipeline_stages_api.get_all(
            object_type=object_type,
            pipeline_id=pipeline_id
        )
        pipeline_dict["stages"] = [s.to_dict() for s in stages_response.results]

        converted = convert_datetime_fields(pipeline_dict)
        return json.dumps(converted)

    @handle_hubspot_errors
    def create_pipeline(
        self,
        object_type: str,
        label: str,
        stages: List[Dict[str, Any]]
    ) -> str:
        """Create a new pipeline with stages.

        Args:
            object_type: 'deals' or 'tickets'
            label: Pipeline display name
            stages: List of stage dicts with 'label' and optional 'probability' (for deals)

        Returns:
            JSON string with created pipeline data
        """
        stage_objects = []
        for i, stage in enumerate(stages):
            stage_input = {
                "label": stage["label"],
                "displayOrder": stage.get("display_order", i),
                "metadata": {}
            }
            if "probability" in stage:
                stage_input["metadata"]["probability"] = str(stage["probability"])
            if "ticket_state" in stage:
                stage_input["metadata"]["ticketState"] = stage["ticket_state"]
            stage_objects.append(stage_input)

        pipeline_input = {
            "label": label,
            "displayOrder": 0,
            "stages": stage_objects
        }

        response = self.client.crm.pipelines.pipelines_api.create(
            object_type=object_type,
            pipeline_input=pipeline_input
        )
        pipeline_dict = response.to_dict()
        converted = convert_datetime_fields(pipeline_dict)
        return json.dumps(converted)

    @handle_hubspot_errors
    def get_pipeline_stages(self, object_type: str, pipeline_id: str) -> str:
        """Get all stages for a specific pipeline.

        Args:
            object_type: 'deals' or 'tickets'
            pipeline_id: Pipeline ID

        Returns:
            JSON string with stage list
        """
        response = self.client.crm.pipelines.pipeline_stages_api.get_all(
            object_type=object_type,
            pipeline_id=pipeline_id
        )
        stages = [s.to_dict() for s in response.results]
        converted = convert_datetime_fields(stages)
        return json.dumps({
            "object_type": object_type,
            "pipeline_id": pipeline_id,
            "results": converted,
            "total": len(converted)
        })
