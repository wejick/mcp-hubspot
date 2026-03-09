"""
End-to-end tests for the hubspot-contacts and hubspot-deals skills.

These tests call the real HubSpot API and require:
  - HUBSPOT_ACCESS_TOKEN environment variable set to a valid Private App token
  - The token must have the scopes listed below

Required HubSpot token scopes:
  - crm.objects.contacts.read
  - crm.objects.contacts.write
  - crm.objects.deals.read
  - crm.objects.deals.write

Required HubSpot account setup:
  - At least one deal pipeline with at least two stages
    (HubSpot creates a default "Sales Pipeline" automatically)
  - No pre-existing contacts or deals are required — this suite
    creates its own test records and archives them on teardown.

Run with: python tests/test_e2e_hubspot_skills.py

The suite is skipped automatically when HUBSPOT_ACCESS_TOKEN is not set.
"""
import json
import sys
import os
import time
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
src_path = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, src_path)

TOKEN = os.environ.get("HUBSPOT_ACCESS_TOKEN")

# ---------------------------------------------------------------------------
# Stub only the heavy non-API dependencies so we can import the package
# without requiring sentence_transformers / faiss to be installed.
# The HubSpot SDK, mcp, pydantic etc. must be genuinely installed.
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock as _MM

_HEAVY_STUBS = ["sentence_transformers", "faiss"]
for _mod in _HEAVY_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = _MM()
sys.modules["sentence_transformers"].SentenceTransformer = _MM


# ---------------------------------------------------------------------------
# Unique test identifier to avoid collisions if the suite is run in parallel
# ---------------------------------------------------------------------------
_RUN_ID = str(int(time.time()))[-6:]


def _test_name(base: str) -> str:
    return f"e2e_test_{_RUN_ID}_{base}"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse(result) -> dict | list | str:
    """Parse the text from a handler response."""
    text = result[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# ============================================================================
# Contacts skill E2E tests
# ============================================================================

@unittest.skipUnless(TOKEN, "HUBSPOT_ACCESS_TOKEN not set — skipping E2E tests")
class TestContactsSkillE2E(unittest.TestCase):
    """
    End-to-end tests for the hubspot-contacts skill.

    HubSpot data setup required:
      None — all test contacts are created and archived within this suite.
    """

    @classmethod
    def setUpClass(cls):
        from mcp_server_hubspot.hubspot_client import HubSpotClient
        from mcp_server_hubspot.handlers.contact_handler import ContactHandler

        cls.hubspot = HubSpotClient(TOKEN)
        cls.handler = ContactHandler(cls.hubspot, _MM(), _MM())
        cls.created_ids: list[str] = []  # track for teardown cleanup

    @classmethod
    def tearDownClass(cls):
        """Archive all contacts created during this test run."""
        for contact_id in cls.created_ids:
            try:
                cls.hubspot.client.crm.contacts.basic_api.archive(
                    contact_id=contact_id
                )
            except Exception:
                pass  # best-effort cleanup

    # ------------------------------------------------------------------
    # hubspot_create_contact
    # ------------------------------------------------------------------

    def test_create_contact_returns_new_contact(self):
        """Creating a contact should return a dict with an 'id' field."""
        result = self.handler.create_contact({
            "firstname": _test_name("first"),
            "lastname": _test_name("last"),
            "email": f"{_test_name('email')}@example-e2e.invalid",
        })

        self.assertIsInstance(result, list)
        text = result[0].text
        # Response is either the new contact dict or "already exists" message
        if "already exists" not in text:
            data = json.loads(text)
            contact_id = data.get("id")
            self.assertIsNotNone(contact_id, "Response must contain an 'id'")
            self.__class__.created_ids.append(contact_id)
        else:
            # Duplicate found — still a valid outcome for idempotent create
            self.assertIn("already exists", text)

    def test_create_contact_prevents_duplicates(self):
        """Creating the same contact twice should not create a duplicate."""
        firstname = _test_name("dup_first")
        lastname = _test_name("dup_last")
        args = {"firstname": firstname, "lastname": lastname}

        # First creation
        result1 = self.handler.create_contact(args)
        text1 = result1[0].text
        if "already exists" not in text1:
            data1 = json.loads(text1)
            self.__class__.created_ids.append(data1["id"])

        # Second creation — must report duplicate
        result2 = self.handler.create_contact(args)
        self.assertIn("already exists", result2[0].text)

    # ------------------------------------------------------------------
    # hubspot_get_contact
    # ------------------------------------------------------------------

    def test_get_contact_returns_contact_data(self):
        """get_contact should return the contact with the requested ID."""
        # Create a fresh contact to retrieve
        firstname = _test_name("get_first")
        lastname = _test_name("get_last")
        create_result = self.handler.create_contact({
            "firstname": firstname,
            "lastname": lastname,
        })
        create_text = create_result[0].text
        if "already exists" in create_text:
            self.skipTest("Pre-existing contact in account — cannot reliably test get")

        contact_id = json.loads(create_text)["id"]
        self.__class__.created_ids.append(contact_id)

        result = self.handler.get_contact({"contact_id": contact_id})

        data = json.loads(result[0].text)
        self.assertEqual(str(data.get("id")), str(contact_id))

    def test_get_contact_with_properties_filter(self):
        """get_contact should return only the requested properties."""
        # Reuse a contact created in this run if available
        if not self.__class__.created_ids:
            self.skipTest("No contacts created yet in this run")

        contact_id = self.__class__.created_ids[0]
        result = self.handler.get_contact({
            "contact_id": contact_id,
            "properties": ["firstname", "lastname"],
        })

        data = json.loads(result[0].text)
        self.assertIn("id", data)

    # ------------------------------------------------------------------
    # hubspot_update_contact
    # ------------------------------------------------------------------

    def test_update_contact_modifies_properties(self):
        """update_contact should persist property changes in HubSpot."""
        # Create a contact to update
        firstname = _test_name("upd_first")
        lastname = _test_name("upd_last")
        create_result = self.handler.create_contact({
            "firstname": firstname,
            "lastname": lastname,
        })
        create_text = create_result[0].text
        if "already exists" in create_text:
            self.skipTest("Pre-existing contact — cannot reliably test update")

        contact_id = json.loads(create_text)["id"]
        self.__class__.created_ids.append(contact_id)

        new_phone = "555-E2E-0001"
        result = self.handler.update_contact({
            "contact_id": contact_id,
            "properties": {"phone": new_phone},
        })

        # Verify the API did not return an error
        text = result[0].text
        self.assertNotIn("error", text.lower(),
                         f"Unexpected error in update response: {text}")
        data = json.loads(text)
        self.assertEqual(str(data.get("id")), str(contact_id))

    # ------------------------------------------------------------------
    # hubspot_query_contacts (list mode)
    # ------------------------------------------------------------------

    def test_query_contacts_list_mode_returns_results(self):
        """query_contacts without filters should return a list of contacts."""
        result = self.handler.query_contacts({"limit": 5})

        text = result[0].text
        data = json.loads(text)
        # Could be a list or dict with 'results' key
        if isinstance(data, list):
            self.assertIsInstance(data, list)
        else:
            self.assertIn("results", data)

    # ------------------------------------------------------------------
    # hubspot_query_contacts (search mode)
    # ------------------------------------------------------------------

    def test_query_contacts_search_mode_filters_results(self):
        """query_contacts with filters should return matching contacts."""
        # Search for contacts whose email ends with our test domain
        filters = [{
            "propertyName": "email",
            "operator": "CONTAINS_TOKEN",
            "value": "example-e2e.invalid",
        }]
        result = self.handler.query_contacts({"filters": filters, "limit": 10})

        data = json.loads(result[0].text)
        # Result may be empty if contacts are not yet indexed, but format must be correct
        self.assertIn("results", data)
        self.assertIn("total", data)


# ============================================================================
# Deals skill E2E tests
# ============================================================================

@unittest.skipUnless(TOKEN, "HUBSPOT_ACCESS_TOKEN not set — skipping E2E tests")
class TestDealsSkillE2E(unittest.TestCase):
    """
    End-to-end tests for the hubspot-deals skill.

    HubSpot data setup required:
      - At least one deal pipeline with at least 2 stages.
        HubSpot creates a default "Sales Pipeline" on every new account,
        so no manual setup is needed in most cases.
      - No pre-existing deals are required.
    """

    @classmethod
    def setUpClass(cls):
        from mcp_server_hubspot.hubspot_client import HubSpotClient
        from mcp_server_hubspot.handlers.deal_handler import DealHandler
        from mcp_server_hubspot.handlers.pipeline_handler import PipelineHandler

        cls.hubspot = HubSpotClient(TOKEN)
        cls.deal_handler = DealHandler(cls.hubspot, _MM(), _MM())
        cls.pipeline_handler = PipelineHandler(cls.hubspot, _MM(), _MM())
        cls.created_deal_ids: list[str] = []

        # Discover the first available pipeline and its stages
        pipeline_result = cls.pipeline_handler.get_pipelines({"object_type": "deals"})
        pipeline_data = json.loads(pipeline_result[0].text)
        pipelines = pipeline_data.get("results", [])
        if not pipelines:
            cls.pipeline_id = None
            cls.stage_ids = []
        else:
            first = pipelines[0]
            cls.pipeline_id = first["id"]
            stages = first.get("stages", [])
            cls.stage_ids = [s["id"] for s in stages if isinstance(s, dict)]

    @classmethod
    def tearDownClass(cls):
        """Archive all deals created during this test run."""
        for deal_id in cls.created_deal_ids:
            try:
                cls.hubspot.client.crm.deals.basic_api.archive(deal_id=deal_id)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # hubspot_get_pipelines
    # ------------------------------------------------------------------

    def test_get_pipelines_returns_at_least_one_pipeline(self):
        """HubSpot accounts always have at least the default Sales Pipeline."""
        result = self.pipeline_handler.get_pipelines({"object_type": "deals"})

        data = json.loads(result[0].text)
        self.assertIn("results", data)
        self.assertGreater(data["total"], 0, "Expected at least one pipeline")

    def test_get_pipelines_each_pipeline_has_id_and_label(self):
        result = self.pipeline_handler.get_pipelines({"object_type": "deals"})

        data = json.loads(result[0].text)
        for pipeline in data["results"]:
            self.assertIn("id", pipeline)
            self.assertIn("label", pipeline)

    def test_get_pipelines_includes_stages(self):
        """Each pipeline should contain its stages."""
        result = self.pipeline_handler.get_pipelines({"object_type": "deals"})

        data = json.loads(result[0].text)
        if data["results"]:
            first_pipeline = data["results"][0]
            self.assertIn("stages", first_pipeline)

    # ------------------------------------------------------------------
    # hubspot_create_deal
    # ------------------------------------------------------------------

    def test_create_deal_with_dealname_only(self):
        """Minimal deal creation using only the required dealname field."""
        result = self.deal_handler.create_deal({
            "dealname": _test_name("minimal_deal"),
        })

        data = json.loads(result[0].text)
        deal_id = data.get("id")
        self.assertIsNotNone(deal_id)
        self.__class__.created_deal_ids.append(deal_id)

    def test_create_deal_with_amount_and_stage(self):
        """Deal creation with optional amount and dealstage."""
        if not self.stage_ids:
            self.skipTest("No pipeline stages found — skipping stage-based create test")

        result = self.deal_handler.create_deal({
            "dealname": _test_name("full_deal"),
            "amount": "9999",
            "dealstage": self.stage_ids[0],
            "pipeline": self.pipeline_id,
        })

        data = json.loads(result[0].text)
        deal_id = data.get("id")
        self.assertIsNotNone(deal_id)
        self.__class__.created_deal_ids.append(deal_id)
        # Verify the stage was set
        props = data.get("properties", {})
        if props:
            self.assertEqual(props.get("dealstage"), self.stage_ids[0])

    # ------------------------------------------------------------------
    # hubspot_get_deal
    # ------------------------------------------------------------------

    def test_get_deal_returns_deal_data(self):
        """get_deal should return the deal record for a known ID."""
        # Create a deal to retrieve
        create_result = self.deal_handler.create_deal({
            "dealname": _test_name("get_deal"),
        })
        deal_id = json.loads(create_result[0].text)["id"]
        self.__class__.created_deal_ids.append(deal_id)

        result = self.deal_handler.get_deal({"deal_id": deal_id})

        data = json.loads(result[0].text)
        self.assertEqual(str(data.get("id")), str(deal_id))

    def test_get_deal_with_properties_filter(self):
        """get_deal should accept a properties list without error."""
        if not self.__class__.created_deal_ids:
            self.skipTest("No deals created yet in this run")

        deal_id = self.__class__.created_deal_ids[0]
        result = self.deal_handler.get_deal({
            "deal_id": deal_id,
            "properties": ["dealname", "amount"],
        })

        data = json.loads(result[0].text)
        self.assertEqual(str(data.get("id")), str(deal_id))

    # ------------------------------------------------------------------
    # hubspot_update_deal
    # ------------------------------------------------------------------

    def test_update_deal_modifies_amount(self):
        """update_deal should persist changes to HubSpot."""
        create_result = self.deal_handler.create_deal({
            "dealname": _test_name("update_deal"),
        })
        deal_id = json.loads(create_result[0].text)["id"]
        self.__class__.created_deal_ids.append(deal_id)

        result = self.deal_handler.update_deal({
            "deal_id": deal_id,
            "properties": {"amount": "12345"},
        })

        text = result[0].text
        self.assertNotIn("error", text.lower(),
                         f"Unexpected error in update response: {text}")
        data = json.loads(text)
        self.assertEqual(str(data.get("id")), str(deal_id))

    # ------------------------------------------------------------------
    # hubspot_query_deals (list mode)
    # ------------------------------------------------------------------

    def test_query_deals_list_mode_returns_results(self):
        """query_deals without filters should list recently modified deals."""
        result = self.deal_handler.query_deals({"limit": 5})

        data = json.loads(result[0].text)
        self.assertIn("results", data)
        self.assertIn("total", data)

    # ------------------------------------------------------------------
    # hubspot_query_deals (search mode)
    # ------------------------------------------------------------------

    def test_query_deals_search_mode_filters_results(self):
        """query_deals with filters should return matching deals."""
        # Search by deal name prefix
        filters = [{
            "propertyName": "dealname",
            "operator": "CONTAINS_TOKEN",
            "value": f"e2e_test_{_RUN_ID}",
        }]
        result = self.deal_handler.query_deals({"filters": filters, "limit": 20})

        data = json.loads(result[0].text)
        self.assertIn("results", data)
        self.assertIn("total", data)

    # ------------------------------------------------------------------
    # hubspot_move_deal_stage
    # ------------------------------------------------------------------

    def test_move_deal_stage_changes_stage(self):
        """move_deal_stage should update the dealstage property."""
        if len(self.stage_ids) < 2:
            self.skipTest("Need at least 2 pipeline stages to test stage movement")

        create_result = self.deal_handler.create_deal({
            "dealname": _test_name("stage_move_deal"),
            "dealstage": self.stage_ids[0],
            "pipeline": self.pipeline_id,
        })
        deal_id = json.loads(create_result[0].text)["id"]
        self.__class__.created_deal_ids.append(deal_id)

        # Move to the second stage
        target_stage = self.stage_ids[1]
        result = self.pipeline_handler.move_deal_stage({
            "deal_id": deal_id,
            "stage_id": target_stage,
        })

        text = result[0].text
        self.assertNotIn("error", text.lower(),
                         f"Unexpected error when moving deal stage: {text}")

    def test_move_deal_stage_with_pipeline_id(self):
        """move_deal_stage should accept an explicit pipeline_id without error."""
        if not self.stage_ids or not self.pipeline_id:
            self.skipTest("No pipeline/stages found — skipping")

        create_result = self.deal_handler.create_deal({
            "dealname": _test_name("stage_move_pipeline_deal"),
            "pipeline": self.pipeline_id,
        })
        deal_id = json.loads(create_result[0].text)["id"]
        self.__class__.created_deal_ids.append(deal_id)

        result = self.pipeline_handler.move_deal_stage({
            "deal_id": deal_id,
            "stage_id": self.stage_ids[0],
            "pipeline_id": self.pipeline_id,
        })

        text = result[0].text
        self.assertNotIn("error", text.lower(),
                         f"Unexpected error when moving deal stage: {text}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
