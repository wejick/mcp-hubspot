"""
Unit tests for the hubspot-deals skill tools.

Covers all six tools exposed by server_deals.py:
  - hubspot_create_deal      → DealHandler.create_deal()
  - hubspot_get_deal         → DealHandler.get_deal()
  - hubspot_update_deal      → DealHandler.update_deal()
  - hubspot_query_deals      → DealHandler.query_deals()
  - hubspot_get_pipelines    → PipelineHandler.get_pipelines()
  - hubspot_move_deal_stage  → PipelineHandler.move_deal_stage()

Run with: python tests/test_hubspot_deals_skill.py
No HUBSPOT_ACCESS_TOKEN required — all API calls are mocked.
"""
import json
import sys
import os
import unittest
from unittest.mock import MagicMock

src_path = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, src_path)

# ---------------------------------------------------------------------------
# Stub heavy / unavailable dependencies before any package imports
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock as _MM


class _ApiException(Exception):
    def __init__(self, status=500, reason="error", *args, **kwargs):
        super().__init__(reason)
        self.status = status
        self.reason = reason


class _TextContent:
    """Lightweight stand-in for mcp.types.TextContent."""
    def __init__(self, type, text):
        self.type = type
        self.text = text


_STUB_MODULES = [
    "dotenv", "sentence_transformers", "faiss",
    "mcp", "mcp.server", "mcp.server.stdio", "mcp.server.models",
    "mcp.server.lowlevel", "mcp.types", "pydantic",
    "hubspot", "hubspot.crm", "hubspot.crm.contacts",
    "hubspot.crm.contacts.exceptions",
    "hubspot.crm.companies", "hubspot.crm.deals",
    "hubspot.crm.tickets", "hubspot.crm.pipelines",
    "hubspot.crm.objects", "hubspot.crm.objects.emails",
    "hubspot.crm.properties", "hubspot.discovery",
    "numpy", "requests",
]
for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = _MM()

sys.modules["sentence_transformers"].SentenceTransformer = _MM
sys.modules["hubspot.crm.contacts.exceptions"].ApiException = _ApiException
sys.modules["mcp.types"].TextContent = _TextContent
# CRUCIAL: link mcp.types on the parent mock so that
# "import mcp.types as types" → IMPORT_FROM types → types.TextContent = _TextContent
sys.modules["mcp"].types = sys.modules["mcp.types"]

for _ns, _classes in [
    ("hubspot.crm.deals", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
    ("hubspot.crm.contacts", ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]),
]:
    for _cls in _classes:
        setattr(sys.modules[_ns], _cls, _MM)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_deal_json(id="10", **props) -> str:
    base = {"dealname": "Test Deal", "amount": "5000", "dealstage": "appointmentscheduled"}
    base.update(props)
    return json.dumps({"id": id, "properties": base})


def _make_deals_list_json(n=2) -> str:
    results = [{"id": str(i), "properties": {"dealname": f"Deal {i}"}} for i in range(n)]
    return json.dumps({"results": results, "total": n})


def _make_search_json(n=2) -> str:
    results = [{"id": str(i), "properties": {"dealname": f"Deal {i}"}} for i in range(n)]
    return json.dumps({"results": results, "total": n})


def _make_pipelines_json() -> str:
    return json.dumps({
        "object_type": "deals",
        "results": [
            {
                "id": "default",
                "label": "Sales Pipeline",
                "stages": [
                    {"id": "appointmentscheduled", "label": "Appointment Scheduled"},
                    {"id": "qualifiedtobuy", "label": "Qualified to Buy"},
                    {"id": "closedwon", "label": "Closed Won"},
                ],
            }
        ],
        "total": 1,
    })


# ---------------------------------------------------------------------------
# hubspot_create_deal
# ---------------------------------------------------------------------------

class TestDealHandlerCreateDeal(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        self.mock_hs = _MM()
        self.handler = DealHandler(self.mock_hs, _MM(), _MM())

    def test_creates_deal_with_required_dealname(self):
        """dealname is the only required field; client.deals.create must be called."""
        self.mock_hs.deals.create.return_value = _make_deal_json(dealname="New Deal")

        result = self.handler.create_deal({"dealname": "New Deal"})

        self.mock_hs.deals.create.assert_called_once()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_missing_dealname_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.create_deal({"amount": "1000"})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.create_deal(None)

    def test_optional_fields_included_in_payload(self):
        """amount, dealstage, pipeline, closedate, hubspot_owner_id should be forwarded."""
        self.mock_hs.deals.create.return_value = _make_deal_json()

        self.handler.create_deal({
            "dealname": "Big Deal",
            "amount": "50000",
            "dealstage": "qualifiedtobuy",
            "pipeline": "default",
            "closedate": "2026-12-31",
            "hubspot_owner_id": "owner_001",
        })

        self.mock_hs.deals.create.assert_called_once()
        payload = self.mock_hs.deals.create.call_args[0][0]
        self.assertEqual(payload["amount"], "50000")
        self.assertEqual(payload["dealstage"], "qualifiedtobuy")
        self.assertEqual(payload["pipeline"], "default")
        self.assertEqual(payload["closedate"], "2026-12-31")
        self.assertEqual(payload["hubspot_owner_id"], "owner_001")

    def test_extra_properties_dict_merged_into_payload(self):
        """A 'properties' dict in arguments should be merged into the create payload."""
        self.mock_hs.deals.create.return_value = _make_deal_json()

        self.handler.create_deal({
            "dealname": "Special Deal",
            "properties": {"description": "VIP client", "deal_currency_code": "EUR"},
        })

        payload = self.mock_hs.deals.create.call_args[0][0]
        self.assertEqual(payload["description"], "VIP client")
        self.assertEqual(payload["deal_currency_code"], "EUR")
        self.assertEqual(payload["dealname"], "Special Deal")

    def test_response_is_list_of_text_content(self):
        self.mock_hs.deals.create.return_value = _make_deal_json()

        result = self.handler.create_deal({"dealname": "Test"})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))

    def test_response_text_contains_deal_data(self):
        self.mock_hs.deals.create.return_value = _make_deal_json(id="77", dealname="Rich Deal")

        result = self.handler.create_deal({"dealname": "Rich Deal"})

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "77")


# ---------------------------------------------------------------------------
# hubspot_get_deal
# ---------------------------------------------------------------------------

class TestDealHandlerGetDeal(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        self.mock_hs = _MM()
        self.handler = DealHandler(self.mock_hs, _MM(), _MM())

    def test_returns_deal_by_id(self):
        self.mock_hs.deals.get_by_id.return_value = _make_deal_json(id="99")

        result = self.handler.get_deal({"deal_id": "99"})

        self.mock_hs.deals.get_by_id.assert_called_once_with("99", None)
        self.assertIsInstance(result, list)

    def test_passes_properties_filter(self):
        self.mock_hs.deals.get_by_id.return_value = _make_deal_json(id="99")
        props = ["dealname", "amount"]

        self.handler.get_deal({"deal_id": "99", "properties": props})

        self.mock_hs.deals.get_by_id.assert_called_once_with("99", props)

    def test_missing_deal_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_deal({})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_deal(None)

    def test_response_text_contains_deal_data(self):
        self.mock_hs.deals.get_by_id.return_value = _make_deal_json(id="55", dealname="Found Deal")

        result = self.handler.get_deal({"deal_id": "55"})

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "55")


# ---------------------------------------------------------------------------
# hubspot_update_deal
# ---------------------------------------------------------------------------

class TestDealHandlerUpdateDeal(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        self.mock_hs = _MM()
        self.handler = DealHandler(self.mock_hs, _MM(), _MM())

    def test_updates_deal_with_correct_id_and_properties(self):
        self.mock_hs.deals.update.return_value = _make_deal_json(id="88", amount="20000")

        result = self.handler.update_deal({
            "deal_id": "88",
            "properties": {"amount": "20000"},
        })

        self.mock_hs.deals.update.assert_called_once_with("88", {"amount": "20000"})
        self.assertIsInstance(result, list)

    def test_missing_deal_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_deal({"properties": {"amount": "1000"}})

    def test_missing_properties_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_deal({"deal_id": "88"})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_deal(None)

    def test_response_text_contains_updated_deal(self):
        self.mock_hs.deals.update.return_value = _make_deal_json(id="88", dealstage="closedwon")

        result = self.handler.update_deal({
            "deal_id": "88",
            "properties": {"dealstage": "closedwon"},
        })

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "88")


# ---------------------------------------------------------------------------
# hubspot_query_deals
# ---------------------------------------------------------------------------

class TestDealHandlerQueryDeals(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        self.mock_hs = _MM()
        self.handler = DealHandler(self.mock_hs, _MM(), _MM())

    # -- List mode (no filters) --

    def test_list_mode_when_no_filters(self):
        """Omitting filters triggers deals.get_recent."""
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json()

        self.handler.query_deals({})

        self.mock_hs.deals.get_recent.assert_called_once()
        self.mock_hs.deals.search.assert_not_called()

    def test_list_mode_with_none_arguments(self):
        """None arguments should trigger list mode with default limit."""
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json()

        self.handler.query_deals(None)

        self.mock_hs.deals.get_recent.assert_called_once_with(10)

    def test_list_mode_default_limit_is_10(self):
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json()

        self.handler.query_deals({})

        args, _ = self.mock_hs.deals.get_recent.call_args
        self.assertEqual(args[0], 10)

    def test_list_mode_respects_custom_limit(self):
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json(3)

        self.handler.query_deals({"limit": 3})

        args, _ = self.mock_hs.deals.get_recent.call_args
        self.assertEqual(args[0], 3)

    # -- Search mode (with filters) --

    def test_search_mode_when_filters_present(self):
        """Providing filters triggers deals.search."""
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]

        self.handler.query_deals({"filters": filters})

        self.mock_hs.deals.search.assert_called_once()
        self.mock_hs.deals.get_recent.assert_not_called()

    def test_search_mode_passes_filters_to_client(self):
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "amount", "operator": "GT", "value": "10000"}]

        self.handler.query_deals({"filters": filters})

        args, _ = self.mock_hs.deals.search.call_args
        self.assertEqual(args[0], filters)

    def test_search_mode_passes_limit(self):
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]

        self.handler.query_deals({"filters": filters, "limit": 5})

        args, _ = self.mock_hs.deals.search.call_args
        self.assertEqual(args[2], 5)  # limit is the 3rd positional arg

    def test_search_mode_default_sort_is_hs_lastmodifieddate(self):
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "dealstage", "operator": "HAS_PROPERTY"}]

        self.handler.query_deals({"filters": filters})

        args, _ = self.mock_hs.deals.search.call_args
        self.assertEqual(args[3], "hs_lastmodifieddate")

    def test_search_mode_custom_sort_property(self):
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "dealstage", "operator": "HAS_PROPERTY"}]

        self.handler.query_deals({"filters": filters, "sort_property": "closedate"})

        args, _ = self.mock_hs.deals.search.call_args
        self.assertEqual(args[3], "closedate")

    def test_search_mode_passes_properties(self):
        self.mock_hs.deals.search.return_value = _make_search_json()
        filters = [{"propertyName": "dealstage", "operator": "HAS_PROPERTY"}]
        props = ["dealname", "amount", "dealstage"]

        self.handler.query_deals({"filters": filters, "properties": props})

        args, _ = self.mock_hs.deals.search.call_args
        self.assertEqual(args[1], props)

    # -- Response format --

    def test_returns_list_of_text_content(self):
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json()

        result = self.handler.query_deals({})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))

    def test_response_text_is_valid_json(self):
        self.mock_hs.deals.get_recent.return_value = _make_deals_list_json()

        result = self.handler.query_deals({})

        json.loads(result[0].text)  # should not raise


# ---------------------------------------------------------------------------
# hubspot_get_pipelines
# ---------------------------------------------------------------------------

class TestPipelineHandlerGetPipelines(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.pipeline_handler import PipelineHandler
        self.mock_hs = _MM()
        self.handler = PipelineHandler(self.mock_hs, _MM(), _MM())

    def test_returns_pipelines_for_deals(self):
        self.mock_hs.pipelines.get_pipelines.return_value = _make_pipelines_json()

        result = self.handler.get_pipelines({"object_type": "deals"})

        self.mock_hs.pipelines.get_pipelines.assert_called_once_with("deals")
        self.assertIsInstance(result, list)

    def test_returns_pipelines_for_tickets(self):
        self.mock_hs.pipelines.get_pipelines.return_value = json.dumps({
            "object_type": "tickets",
            "results": [],
            "total": 0,
        })

        self.handler.get_pipelines({"object_type": "tickets"})

        self.mock_hs.pipelines.get_pipelines.assert_called_once_with("tickets")

    def test_missing_object_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_pipelines({})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_pipelines(None)

    def test_response_is_list_of_text_content(self):
        self.mock_hs.pipelines.get_pipelines.return_value = _make_pipelines_json()

        result = self.handler.get_pipelines({"object_type": "deals"})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))

    def test_response_text_contains_pipeline_data(self):
        self.mock_hs.pipelines.get_pipelines.return_value = _make_pipelines_json()

        result = self.handler.get_pipelines({"object_type": "deals"})

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["object_type"], "deals")
        self.assertIn("results", parsed)


# ---------------------------------------------------------------------------
# hubspot_move_deal_stage
# ---------------------------------------------------------------------------

class TestPipelineHandlerMoveDealStage(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.pipeline_handler import PipelineHandler
        self.mock_hs = _MM()
        self.handler = PipelineHandler(self.mock_hs, _MM(), _MM())

    def test_moves_deal_to_new_stage(self):
        """Should call deals.update with dealstage set to the target stage_id."""
        self.mock_hs.deals.update.return_value = _make_deal_json(
            id="44", dealstage="qualifiedtobuy"
        )

        result = self.handler.move_deal_stage({"deal_id": "44", "stage_id": "qualifiedtobuy"})

        self.mock_hs.deals.update.assert_called_once_with(
            "44", {"dealstage": "qualifiedtobuy"}
        )
        self.assertIsInstance(result, list)

    def test_includes_pipeline_when_provided(self):
        """When pipeline_id is given, it must also be included in the update payload."""
        self.mock_hs.deals.update.return_value = _make_deal_json(id="44")

        self.handler.move_deal_stage({
            "deal_id": "44",
            "stage_id": "closedwon",
            "pipeline_id": "pipeline_001",
        })

        self.mock_hs.deals.update.assert_called_once_with(
            "44", {"dealstage": "closedwon", "pipeline": "pipeline_001"}
        )

    def test_missing_deal_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.move_deal_stage({"stage_id": "closedwon"})

    def test_missing_stage_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.move_deal_stage({"deal_id": "44"})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.move_deal_stage(None)

    def test_response_is_list_of_text_content(self):
        self.mock_hs.deals.update.return_value = _make_deal_json(id="44")

        result = self.handler.move_deal_stage({"deal_id": "44", "stage_id": "closedwon"})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))

    def test_response_text_contains_updated_deal(self):
        self.mock_hs.deals.update.return_value = _make_deal_json(id="44", dealstage="closedwon")

        result = self.handler.move_deal_stage({"deal_id": "44", "stage_id": "closedwon"})

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "44")


if __name__ == "__main__":
    unittest.main(verbosity=2)
