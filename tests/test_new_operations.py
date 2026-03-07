"""
Unit tests for new HubSpot MCP operations:
- Deal CRUD
- Ticket CRUD (create, update, get by ID)
- Contact/Company search
- Associations
- Engagements (notes, meetings, calls, tasks)
- Pipelines

Uses unittest.mock to avoid requiring a real HubSpot token.
Run with: python tests/test_new_operations.py
"""
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

src_path = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, src_path)

# Stub out heavy/unavailable dependencies before any package imports
from unittest.mock import MagicMock as _MagicMock

class _ApiException(Exception):
    def __init__(self, status=500, reason="error", *args, **kwargs):
        super().__init__(reason)
        self.status = status
        self.reason = reason

# Stub all unavailable modules before any package imports
_STUB_MODULES = [
    "dotenv", "sentence_transformers", "faiss",
    "mcp", "mcp.server", "mcp.server.stdio", "mcp.server.models",
    "mcp.server.lowlevel", "mcp.types", "pydantic",
    "hubspot", "hubspot.crm", "hubspot.crm.contacts",
    "hubspot.crm.contacts.exceptions",
    "hubspot.crm.companies",
    "hubspot.crm.deals",
    "hubspot.crm.tickets",
    "hubspot.crm.pipelines",
    "hubspot.crm.objects",
    "hubspot.crm.objects.emails",
    "hubspot.crm.properties",
    "hubspot.discovery",
    "numpy",
    "requests",
]
for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = _MagicMock()

# Wire up essential attributes so relative imports work
sys.modules["sentence_transformers"].SentenceTransformer = _MagicMock
sys.modules["hubspot.crm.contacts.exceptions"].ApiException = _ApiException

# SDK classes used in clients
for _ns, _classes in [
    ("hubspot.crm.deals", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
    ("hubspot.crm.tickets", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
    ("hubspot.crm.contacts", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
    ("hubspot.crm.companies", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
    ("hubspot.crm.objects.emails", ["BatchReadInputSimplePublicObjectId", "SimplePublicObjectId"]),
]:
    for _cls in _classes:
        setattr(sys.modules[_ns], _cls, _MagicMock)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hs_object(properties: dict, id: str = "123") -> MagicMock:
    """Return a mock HubSpot SDK object with .to_dict()."""
    obj = MagicMock()
    obj.id = id
    obj.to_dict.return_value = {"id": id, "properties": properties}
    return obj


def _make_search_response(items, total=None):
    resp = MagicMock()
    resp.results = items
    resp.total = total if total is not None else len(items)
    resp.paging = None
    return resp


# ---------------------------------------------------------------------------
# Deal client tests
# ---------------------------------------------------------------------------

class TestDealClient(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.deal_client import DealClient
        self.mock_hs = MagicMock()
        self.client = DealClient(self.mock_hs, "fake-token")

    def test_get_recent_returns_json_with_results(self):
        deal = _make_hs_object({"dealname": "Big Deal", "amount": "10000"})
        self.mock_hs.crm.deals.search_api.do_search.return_value = _make_search_response([deal])

        result = self.client.get_recent(limit=5)
        data = json.loads(result)

        self.assertIn("results", data)
        self.assertIn("total", data)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], "123")

    def test_get_by_id_returns_json(self):
        deal = _make_hs_object({"dealname": "Test", "dealstage": "appointmentscheduled"})
        self.mock_hs.crm.deals.basic_api.get_by_id.return_value = deal

        result = self.client.get_by_id("456")
        data = json.loads(result)

        self.assertEqual(data["id"], "123")
        self.mock_hs.crm.deals.basic_api.get_by_id.assert_called_once_with(
            deal_id="456", properties=unittest.mock.ANY, archived=False
        )

    def test_create_returns_json(self):
        deal = _make_hs_object({"dealname": "New Deal"}, id="789")
        self.mock_hs.crm.deals.basic_api.create.return_value = deal

        result = self.client.create({"dealname": "New Deal", "dealstage": "closedwon"})
        data = json.loads(result)

        self.assertEqual(data["id"], "789")
        self.mock_hs.crm.deals.basic_api.create.assert_called_once()

    def test_update_returns_json(self):
        deal = _make_hs_object({"dealstage": "closedwon"}, id="456")
        self.mock_hs.crm.deals.basic_api.update.return_value = deal

        result = self.client.update("456", {"dealstage": "closedwon"})
        data = json.loads(result)

        self.assertEqual(data["id"], "456")
        self.mock_hs.crm.deals.basic_api.update.assert_called_once()

    def test_search_passes_filters(self):
        self.mock_hs.crm.deals.search_api.do_search.return_value = _make_search_response([])

        filters = [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]
        result = self.client.search(filters)
        data = json.loads(result)

        self.assertEqual(data["results"], [])
        self.assertEqual(data["total"], 0)
        call_args = self.mock_hs.crm.deals.search_api.do_search.call_args
        search_req = call_args[1]["public_object_search_request"]
        self.assertEqual(search_req.filter_groups[0]["filters"], filters)

    def test_get_recent_handles_api_error(self):
        from hubspot.crm.contacts.exceptions import ApiException
        self.mock_hs.crm.deals.search_api.do_search.side_effect = ApiException(status=500, reason="error")

        result = self.client.get_recent()
        data = json.loads(result)
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# Ticket client new method tests
# ---------------------------------------------------------------------------

class TestTicketClientNewMethods(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.ticket_client import TicketClient
        self.mock_hs = MagicMock()
        self.client = TicketClient(self.mock_hs, "fake-token")

    def test_get_by_id_returns_json(self):
        ticket = _make_hs_object({"subject": "Issue #1"}, id="101")
        self.mock_hs.crm.tickets.basic_api.get_by_id.return_value = ticket

        result = self.client.get_by_id("101")
        data = json.loads(result)
        self.assertEqual(data["id"], "101")

    def test_create_returns_json(self):
        ticket = _make_hs_object({"subject": "New Issue"}, id="202")
        self.mock_hs.crm.tickets.basic_api.create.return_value = ticket

        result = self.client.create({"subject": "New Issue", "hs_pipeline_stage": "1"})
        data = json.loads(result)
        self.assertEqual(data["id"], "202")
        self.mock_hs.crm.tickets.basic_api.create.assert_called_once()

    def test_update_returns_json(self):
        ticket = _make_hs_object({"hs_pipeline_stage": "4"}, id="303")
        self.mock_hs.crm.tickets.basic_api.update.return_value = ticket

        result = self.client.update("303", {"hs_pipeline_stage": "4"})
        data = json.loads(result)
        self.assertEqual(data["id"], "303")

    def test_get_by_id_uses_custom_properties(self):
        ticket = _make_hs_object({}, id="1")
        self.mock_hs.crm.tickets.basic_api.get_by_id.return_value = ticket

        self.client.get_by_id("1", properties=["subject", "content"])
        self.mock_hs.crm.tickets.basic_api.get_by_id.assert_called_once_with(
            ticket_id="1", properties=["subject", "content"], archived=False
        )


# ---------------------------------------------------------------------------
# Contact client search tests
# ---------------------------------------------------------------------------

class TestContactClientSearch(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.contact_client import ContactClient
        self.mock_hs = MagicMock()
        self.client = ContactClient(self.mock_hs, "fake-token")

    def test_search_returns_results(self):
        contact = _make_hs_object({"email": "test@example.com"}, id="C1")
        self.mock_hs.crm.contacts.search_api.do_search.return_value = _make_search_response([contact], total=1)

        filters = [{"propertyName": "email", "operator": "EQ", "value": "test@example.com"}]
        result = self.client.search(filters)
        data = json.loads(result)

        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["results"]), 1)

    def test_search_passes_correct_filter_groups(self):
        self.mock_hs.crm.contacts.search_api.do_search.return_value = _make_search_response([])

        filters = [{"propertyName": "company", "operator": "EQ", "value": "Acme"}]
        self.client.search(filters, limit=5, sort_property="email")

        call_args = self.mock_hs.crm.contacts.search_api.do_search.call_args
        req = call_args[1]["public_object_search_request"]
        self.assertEqual(req.filter_groups[0]["filters"], filters)
        self.assertEqual(req.limit, 5)

    def test_search_uses_custom_properties(self):
        self.mock_hs.crm.contacts.search_api.do_search.return_value = _make_search_response([])

        self.client.search([{"propertyName": "email", "operator": "HAS_PROPERTY"}],
                           properties=["email", "phone"])
        call_args = self.mock_hs.crm.contacts.search_api.do_search.call_args
        req = call_args[1]["public_object_search_request"]
        self.assertEqual(req.properties, ["email", "phone"])


# ---------------------------------------------------------------------------
# Company client search tests
# ---------------------------------------------------------------------------

class TestCompanyClientSearch(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.company_client import CompanyClient
        self.mock_hs = MagicMock()
        self.client = CompanyClient(self.mock_hs, "fake-token")

    def test_search_returns_results(self):
        company = _make_hs_object({"name": "Acme Corp"}, id="CO1")
        self.mock_hs.crm.companies.search_api.do_search.return_value = _make_search_response([company], total=1)

        result = self.client.search([{"propertyName": "name", "operator": "EQ", "value": "Acme Corp"}])
        data = json.loads(result)

        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["results"]), 1)

    def test_search_empty_results(self):
        self.mock_hs.crm.companies.search_api.do_search.return_value = _make_search_response([], total=0)

        result = self.client.search([{"propertyName": "name", "operator": "EQ", "value": "Nobody"}])
        data = json.loads(result)

        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])


# ---------------------------------------------------------------------------
# Association client tests
# ---------------------------------------------------------------------------

class TestAssociationClient(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.association_client import AssociationClient
        self.mock_hs = MagicMock()
        self.client = AssociationClient(self.mock_hs, "fake-token")

    @patch("mcp_server_hubspot.clients.association_client.requests.put")
    def test_create_association_success(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.text = '{"results": []}'
        mock_resp.json.return_value = {"results": []}
        mock_put.return_value = mock_resp

        result = self.client.create_association("contacts", "C1", "companies", "CO1")
        data = json.loads(result)

        self.assertTrue(data["success"])
        self.assertEqual(data["from_object_type"], "contacts")
        self.assertEqual(data["to_object_type"], "companies")
        mock_put.assert_called_once()
        # Verify timeout was passed
        call_kwargs = mock_put.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 30)

    @patch("mcp_server_hubspot.clients.association_client.requests.put")
    def test_create_association_default_type_id(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.text = "{}"
        mock_resp.json.return_value = {}
        mock_put.return_value = mock_resp

        self.client.create_association("deals", "D1", "contacts", "C1")

        body = mock_put.call_args[1]["json"]
        self.assertEqual(body[0]["associationTypeId"], 1)
        self.assertEqual(body[0]["associationCategory"], "HUBSPOT_DEFINED")

    @patch("mcp_server_hubspot.clients.association_client.requests.get")
    def test_get_associations_returns_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [{"toObjectId": "456", "associationTypes": []}]}
        mock_get.return_value = mock_resp

        result = self.client.get_associations("contacts", "C1", "companies")
        data = json.loads(result)

        self.assertEqual(data["total"], 1)
        self.assertEqual(data["from_object_id"], "C1")
        self.assertEqual(data["to_object_type"], "companies")
        # Verify timeout was passed
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 30)

    @patch("mcp_server_hubspot.clients.association_client.requests.delete")
    def test_delete_association_success(self, mock_delete):
        mock_resp = MagicMock()
        mock_delete.return_value = mock_resp

        result = self.client.delete_association("contacts", "C1", "companies", "CO1")
        data = json.loads(result)

        self.assertTrue(data["success"])
        # Verify timeout was passed
        call_kwargs = mock_delete.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 30)

    @patch("mcp_server_hubspot.clients.association_client.requests.get")
    def test_get_associations_handles_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        result = self.client.get_associations("deals", "D1", "contacts")
        data = json.loads(result)

        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])


# ---------------------------------------------------------------------------
# Engagement client tests
# ---------------------------------------------------------------------------

class TestEngagementClient(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.engagement_client import EngagementClient
        self.mock_hs = MagicMock()
        self.client = EngagementClient(self.mock_hs, "fake-token")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_note_no_associations(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "N1", "properties": {"hs_note_body": "Test note"}}
        mock_post.return_value = mock_resp

        result = self.client.create_note("Test note")
        data = json.loads(result)

        self.assertEqual(data["id"], "N1")
        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_note_body"], "Test note")
        self.assertNotIn("associations", body)

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_note_with_associations(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "N2", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_note(
            "Deal note",
            associations=[{"object_type": "deals", "object_id": "D1"}]
        )

        body = mock_post.call_args[1]["json"]
        self.assertIn("associations", body)
        self.assertEqual(len(body["associations"]), 1)
        self.assertEqual(body["associations"][0]["to"]["id"], "D1")
        # Note-to-deal type ID is 214
        self.assertEqual(body["associations"][0]["types"][0]["associationTypeId"], 214)

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_meeting_required_fields(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "M1", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_meeting("Sync call", "2025-01-01T10:00:00Z", "2025-01-01T11:00:00Z")

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_meeting_title"], "Sync call")
        self.assertEqual(body["properties"]["hs_meeting_start_time"], "2025-01-01T10:00:00Z")
        self.assertEqual(body["properties"]["hs_meeting_end_time"], "2025-01-01T11:00:00Z")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_meeting_with_outcome(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "M2", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_meeting(
            "Demo", "2025-01-01T10:00:00Z", "2025-01-01T11:00:00Z",
            body="Product demo", outcome="COMPLETED"
        )

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_meeting_body"], "Product demo")
        self.assertEqual(body["properties"]["hs_meeting_outcome"], "COMPLETED")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_call(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "CA1", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_call("Spoke with client", duration_ms=120000, status="COMPLETED")

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_call_body"], "Spoke with client")
        self.assertEqual(body["properties"]["hs_call_duration"], "120000")
        self.assertEqual(body["properties"]["hs_call_status"], "COMPLETED")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_task(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "T1", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_task("Follow up", body="Send proposal", due_date="2025-02-01", priority="HIGH")

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_task_subject"], "Follow up")
        self.assertEqual(body["properties"]["hs_task_body"], "Send proposal")
        self.assertEqual(body["properties"]["hs_task_due_date"], "2025-02-01")
        self.assertEqual(body["properties"]["hs_task_priority"], "HIGH")
        self.assertEqual(body["properties"]["hs_task_status"], "NOT_STARTED")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_task_default_status(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "T2", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_task("Quick task")

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["properties"]["hs_task_status"], "NOT_STARTED")

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_create_note_unknown_association_type_silently_ignored(self, mock_post):
        """Associations with unknown object_type are silently dropped."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "N3", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_note(
            "Test",
            associations=[{"object_type": "unknown_type", "object_id": "X1"}]
        )

        body = mock_post.call_args[1]["json"]
        # Unknown type has no type_id so association is not added
        self.assertNotIn("associations", body)

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_requests_timeout_is_set(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "N4", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_note("Timeout test")

        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 30)

    @patch("mcp_server_hubspot.clients.engagement_client.requests.post")
    def test_meeting_association_type_id(self, mock_post):
        """Meeting-to-contact association should use type ID 200."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "M3", "properties": {}}
        mock_post.return_value = mock_resp

        self.client.create_meeting(
            "Call", "2025-01-01T10:00:00Z", "2025-01-01T11:00:00Z",
            associations=[{"object_type": "contacts", "object_id": "C1"}]
        )

        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["associations"][0]["types"][0]["associationTypeId"], 200)


# ---------------------------------------------------------------------------
# Pipeline client tests
# ---------------------------------------------------------------------------

class TestPipelineClient(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.clients.pipeline_client import PipelineClient
        self.mock_hs = MagicMock()
        self.client = PipelineClient(self.mock_hs, "fake-token")

    def _make_pipeline(self, id="P1", label="Default"):
        p = MagicMock()
        p.to_dict.return_value = {"id": id, "label": label, "stages": []}
        return p

    def _make_stage(self, id="S1", label="New"):
        s = MagicMock()
        s.to_dict.return_value = {"id": id, "label": label}
        return s

    def test_get_pipelines(self):
        pipeline = self._make_pipeline()
        resp = MagicMock()
        resp.results = [pipeline]
        self.mock_hs.crm.pipelines.pipelines_api.get_all.return_value = resp

        result = self.client.get_pipelines("deals")
        data = json.loads(result)

        self.assertEqual(data["object_type"], "deals")
        self.assertEqual(data["total"], 1)
        self.mock_hs.crm.pipelines.pipelines_api.get_all.assert_called_once_with(object_type="deals")

    def test_get_pipeline_includes_stages(self):
        pipeline = self._make_pipeline("P2", "Sales")
        self.mock_hs.crm.pipelines.pipelines_api.get_by_id.return_value = pipeline

        stage = self._make_stage("S1", "Qualified")
        stages_resp = MagicMock()
        stages_resp.results = [stage]
        self.mock_hs.crm.pipelines.pipeline_stages_api.get_all.return_value = stages_resp

        result = self.client.get_pipeline("deals", "P2")
        data = json.loads(result)

        self.assertIn("stages", data)
        self.assertEqual(len(data["stages"]), 1)

    def test_create_pipeline_builds_stage_objects(self):
        pipeline = self._make_pipeline("P3", "New Pipeline")
        self.mock_hs.crm.pipelines.pipelines_api.create.return_value = pipeline

        stages = [
            {"label": "Prospecting", "probability": 0.1},
            {"label": "Closed Won", "probability": 1.0}
        ]
        result = self.client.create_pipeline("deals", "New Pipeline", stages)
        data = json.loads(result)

        self.assertEqual(data["id"], "P3")
        call_kwargs = self.mock_hs.crm.pipelines.pipelines_api.create.call_args[1]
        pipeline_input = call_kwargs["pipeline_input"]
        self.assertEqual(len(pipeline_input["stages"]), 2)
        self.assertEqual(pipeline_input["stages"][0]["label"], "Prospecting")
        self.assertEqual(pipeline_input["stages"][0]["metadata"]["probability"], "0.1")

    def test_get_pipeline_stages(self):
        stage = self._make_stage("S2", "Demo")
        resp = MagicMock()
        resp.results = [stage]
        self.mock_hs.crm.pipelines.pipeline_stages_api.get_all.return_value = resp

        result = self.client.get_pipeline_stages("deals", "P1")
        data = json.loads(result)

        self.assertEqual(data["pipeline_id"], "P1")
        self.assertEqual(data["total"], 1)

    def test_get_pipelines_handles_error(self):
        from hubspot.crm.contacts.exceptions import ApiException
        self.mock_hs.crm.pipelines.pipelines_api.get_all.side_effect = ApiException(status=403, reason="Forbidden")

        result = self.client.get_pipelines("deals")
        data = json.loads(result)
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# Deal handler tests
# ---------------------------------------------------------------------------

class TestDealHandler(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        self.mock_hubspot = MagicMock()
        self.mock_faiss = MagicMock()
        self.mock_model = MagicMock()
        self.handler = DealHandler(self.mock_hubspot, self.mock_faiss, self.mock_model)

    def test_create_deal_requires_dealname(self):
        with self.assertRaises(ValueError):
            self.handler.create_deal({})

    def test_create_deal_calls_client(self):
        self.mock_hubspot.deals.create.return_value = json.dumps({"id": "D1", "properties": {}})
        self.handler.create_deal({"dealname": "Big Deal", "amount": "5000"})
        self.mock_hubspot.deals.create.assert_called_once()
        call_props = self.mock_hubspot.deals.create.call_args[0][0]
        self.assertEqual(call_props["dealname"], "Big Deal")
        self.assertEqual(call_props["amount"], "5000")

    def test_get_deal_requires_deal_id(self):
        with self.assertRaises(ValueError):
            self.handler.get_deal({})

    def test_update_deal_requires_both_args(self):
        with self.assertRaises(ValueError):
            self.handler.update_deal({"deal_id": "D1"})

    def test_get_deals_uses_default_limit(self):
        self.mock_hubspot.deals.get_recent.return_value = json.dumps({"results": [], "total": 0})
        self.handler.get_deals(None)
        self.mock_hubspot.deals.get_recent.assert_called_once_with(10)

    def test_search_deals_requires_filters(self):
        with self.assertRaises(ValueError):
            self.handler.search_deals({})

    def test_create_deal_passes_optional_fields(self):
        self.mock_hubspot.deals.create.return_value = json.dumps({"id": "D2", "properties": {}})
        self.handler.create_deal({
            "dealname": "Test",
            "dealstage": "closedwon",
            "closedate": "2025-12-31",
            "properties": {"custom_field": "value"}
        })
        call_props = self.mock_hubspot.deals.create.call_args[0][0]
        self.assertEqual(call_props["dealstage"], "closedwon")
        self.assertEqual(call_props["closedate"], "2025-12-31")
        self.assertEqual(call_props["custom_field"], "value")


# ---------------------------------------------------------------------------
# Pipeline handler tests
# ---------------------------------------------------------------------------

class TestPipelineHandler(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.pipeline_handler import PipelineHandler
        self.mock_hubspot = MagicMock()
        self.mock_faiss = MagicMock()
        self.mock_model = MagicMock()
        self.handler = PipelineHandler(self.mock_hubspot, self.mock_faiss, self.mock_model)

    def test_get_pipelines_requires_object_type(self):
        with self.assertRaises(ValueError):
            self.handler.get_pipelines({})

    def test_get_pipeline_requires_both_args(self):
        with self.assertRaises(ValueError):
            self.handler.get_pipeline({"object_type": "deals"})

    def test_move_deal_stage_requires_deal_id_and_stage(self):
        with self.assertRaises(ValueError):
            self.handler.move_deal_stage({"deal_id": "D1"})

    def test_move_deal_stage_updates_dealstage(self):
        self.mock_hubspot.deals.update.return_value = json.dumps({"id": "D1", "properties": {}})
        self.handler.move_deal_stage({"deal_id": "D1", "stage_id": "closedwon"})
        self.mock_hubspot.deals.update.assert_called_once_with("D1", {"dealstage": "closedwon"})

    def test_move_deal_stage_with_pipeline_change(self):
        self.mock_hubspot.deals.update.return_value = json.dumps({"id": "D1", "properties": {}})
        self.handler.move_deal_stage({"deal_id": "D1", "stage_id": "S2", "pipeline_id": "P2"})
        self.mock_hubspot.deals.update.assert_called_once_with(
            "D1", {"dealstage": "S2", "pipeline": "P2"}
        )

    def test_create_pipeline_stores_in_faiss(self):
        self.mock_hubspot.pipelines.create_pipeline.return_value = json.dumps({"id": "P1", "label": "Test"})
        self.handler.create_pipeline({
            "object_type": "deals",
            "label": "Test Pipeline",
            "stages": [{"label": "Stage 1"}]
        })
        self.mock_hubspot.pipelines.create_pipeline.assert_called_once()
        # FAISS storage should be attempted
        self.mock_faiss.save_today_index.assert_called()


# ---------------------------------------------------------------------------
# Engagement handler tests
# ---------------------------------------------------------------------------

class TestEngagementHandler(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.engagement_handler import EngagementHandler
        self.mock_hubspot = MagicMock()
        self.mock_faiss = MagicMock()
        self.mock_model = MagicMock()
        self.handler = EngagementHandler(self.mock_hubspot, self.mock_faiss, self.mock_model)

    def test_create_note_requires_body(self):
        with self.assertRaises(ValueError):
            self.handler.create_note({})

    def test_create_meeting_requires_title_and_times(self):
        with self.assertRaises(ValueError):
            self.handler.create_meeting({"title": "Meeting"})

    def test_create_call_requires_body(self):
        with self.assertRaises(ValueError):
            self.handler.create_call({})

    def test_create_task_requires_subject(self):
        with self.assertRaises(ValueError):
            self.handler.create_task({})

    def test_create_note_passes_associations(self):
        self.mock_hubspot.engagements.create_note.return_value = json.dumps({"id": "N1", "properties": {}})
        associations = [{"object_type": "deals", "object_id": "D1"}]
        self.handler.create_note({"body": "Test", "associations": associations})
        self.mock_hubspot.engagements.create_note.assert_called_once_with(
            body="Test", associations=associations, timestamp=None
        )

    def test_create_call_converts_duration_to_int(self):
        self.mock_hubspot.engagements.create_call.return_value = json.dumps({"id": "CA1", "properties": {}})
        self.handler.create_call({"body": "Call notes", "duration_ms": "90000"})
        call_kwargs = self.mock_hubspot.engagements.create_call.call_args[1]
        self.assertEqual(call_kwargs["duration_ms"], 90000)  # converted from string to int


# ---------------------------------------------------------------------------
# Association handler tests
# ---------------------------------------------------------------------------

class TestAssociationHandler(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.association_handler import AssociationHandler
        self.mock_hubspot = MagicMock()
        self.mock_faiss = MagicMock()
        self.mock_model = MagicMock()
        self.handler = AssociationHandler(self.mock_hubspot, self.mock_faiss, self.mock_model)

    def test_create_association_requires_all_fields(self):
        with self.assertRaises(ValueError):
            self.handler.create_association({"from_object_type": "contacts", "from_object_id": "C1"})

    def test_get_associations_requires_three_fields(self):
        with self.assertRaises(ValueError):
            self.handler.get_associations({"from_object_type": "contacts"})

    def test_delete_association_requires_all_fields(self):
        with self.assertRaises(ValueError):
            self.handler.delete_association({"from_object_type": "contacts", "from_object_id": "C1"})

    def test_create_association_calls_client(self):
        self.mock_hubspot.associations.create_association.return_value = json.dumps({"success": True})
        self.handler.create_association({
            "from_object_type": "contacts",
            "from_object_id": "C1",
            "to_object_type": "companies",
            "to_object_id": "CO1"
        })
        self.mock_hubspot.associations.create_association.assert_called_once_with(
            from_object_type="contacts",
            from_object_id="C1",
            to_object_type="companies",
            to_object_id="CO1",
            association_type=None
        )

    def test_get_associations_stores_in_faiss(self):
        self.mock_hubspot.associations.get_associations.return_value = json.dumps({
            "results": [{"toObjectId": "CO1"}], "total": 1,
            "from_object_type": "contacts", "from_object_id": "C1", "to_object_type": "companies"
        })
        self.handler.get_associations({
            "from_object_type": "contacts",
            "from_object_id": "C1",
            "to_object_type": "companies"
        })
        self.mock_faiss.save_today_index.assert_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
