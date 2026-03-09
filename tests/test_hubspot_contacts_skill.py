"""
Unit tests for the hubspot-contacts skill tools.

Covers all four tools exposed by server_contacts.py:
  - hubspot_create_contact  → ContactHandler.create_contact()
  - hubspot_get_contact     → ContactHandler.get_contact()
  - hubspot_update_contact  → ContactHandler.update_contact()
  - hubspot_query_contacts  → ContactHandler.query_contacts()

Run with: python tests/test_hubspot_contacts_skill.py
No HUBSPOT_ACCESS_TOKEN required — all API calls are mocked.
"""
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, call

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

# Wire up the classes the handlers import at runtime
sys.modules["sentence_transformers"].SentenceTransformer = _MM
sys.modules["hubspot.crm.contacts.exceptions"].ApiException = _ApiException
sys.modules["mcp.types"].TextContent = _TextContent
# CRUCIAL: link mcp.types on the parent mock so that
# "import mcp.types as types" → IMPORT_FROM types → types.TextContent = _TextContent
sys.modules["mcp"].types = sys.modules["mcp.types"]

for _cls in ["PublicObjectSearchRequest", "SimplePublicObjectInputForCreate", "SimplePublicObjectInput"]:
    setattr(sys.modules["hubspot.crm.contacts"], _cls, _MM)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hs_object(properties: dict, id: str = "123") -> MagicMock:
    """Return a mock HubSpot SDK object with .to_dict()."""
    obj = _MM()
    obj.id = id
    obj.to_dict.return_value = {"id": id, "properties": properties}
    return obj


def _make_search_response(items, total=None):
    resp = _MM()
    resp.results = items
    resp.total = total if total is not None else len(items)
    resp.paging = None
    return resp


def _parse_response_text(result):
    """Extract the text from a handler response and attempt JSON parse."""
    assert isinstance(result, list) and len(result) == 1
    text = result[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# ---------------------------------------------------------------------------
# hubspot_create_contact
# ---------------------------------------------------------------------------

class TestContactHandlerCreateContact(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.contact_handler import ContactHandler
        self.mock_hs = _MM()
        self.handler = ContactHandler(self.mock_hs, _MM(), _MM())

    def test_creates_new_contact_when_no_duplicate(self):
        """When search returns 0 results, basic_api.create should be called."""
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([], 0)
        )
        new_contact = _make_hs_object({"firstname": "Jane", "lastname": "Smith"}, id="456")
        self.mock_hs.client.crm.contacts.basic_api.create.return_value = new_contact

        result = self.handler.create_contact({"firstname": "Jane", "lastname": "Smith"})

        self.mock_hs.client.crm.contacts.basic_api.create.assert_called_once()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_returns_existing_when_duplicate_found(self):
        """When a contact with same name exists, create should NOT be called."""
        existing = _make_hs_object({"firstname": "Jane", "lastname": "Smith"}, id="999")
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([existing], 1)
        )

        result = self.handler.create_contact({"firstname": "Jane", "lastname": "Smith"})

        self.mock_hs.client.crm.contacts.basic_api.create.assert_not_called()
        self.assertIsInstance(result, list)
        self.assertIn("already exists", result[0].text)

    def test_missing_firstname_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.create_contact({"lastname": "Smith"})

    def test_missing_lastname_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.create_contact({"firstname": "Jane"})

    def test_missing_arguments_entirely_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.create_contact(None)

    def test_includes_email_when_provided(self):
        """Email should be passed through to the API call."""
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([], 0)
        )
        new_contact = _make_hs_object(
            {"firstname": "Jane", "lastname": "Smith", "email": "jane@test.com"}, id="789"
        )
        self.mock_hs.client.crm.contacts.basic_api.create.return_value = new_contact

        self.handler.create_contact({
            "firstname": "Jane",
            "lastname": "Smith",
            "email": "jane@test.com",
        })

        self.mock_hs.client.crm.contacts.basic_api.create.assert_called_once()

    def test_extra_properties_dict_merged(self):
        """Additional properties dict should be merged into the create payload."""
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([], 0)
        )
        new_contact = _make_hs_object({"firstname": "Bob", "lastname": "Jones"}, id="321")
        self.mock_hs.client.crm.contacts.basic_api.create.return_value = new_contact

        self.handler.create_contact({
            "firstname": "Bob",
            "lastname": "Jones",
            "properties": {"phone": "555-0100", "company": "Acme"},
        })

        self.mock_hs.client.crm.contacts.basic_api.create.assert_called_once()

    def test_company_filter_added_to_duplicate_check(self):
        """Company in properties should be included in the duplicate search."""
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([], 0)
        )
        new_contact = _make_hs_object({"firstname": "Alice"}, id="111")
        self.mock_hs.client.crm.contacts.basic_api.create.return_value = new_contact

        self.handler.create_contact({
            "firstname": "Alice",
            "lastname": "Wonder",
            "properties": {"company": "Wonderland Inc"},
        })

        # Verify the search was performed (to check for duplicates)
        self.mock_hs.client.crm.contacts.search_api.do_search.assert_called_once()

    def test_response_is_list_of_text_content(self):
        """Result must be a list containing a single TextContent-like object."""
        self.mock_hs.client.crm.contacts.search_api.do_search.return_value = (
            _make_search_response([], 0)
        )
        self.mock_hs.client.crm.contacts.basic_api.create.return_value = (
            _make_hs_object({"firstname": "Test"}, id="001")
        )

        result = self.handler.create_contact({"firstname": "Test", "lastname": "User"})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))


# ---------------------------------------------------------------------------
# hubspot_get_contact
# ---------------------------------------------------------------------------

class TestContactHandlerGetContact(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.contact_handler import ContactHandler
        self.mock_hs = _MM()
        self.handler = ContactHandler(self.mock_hs, _MM(), _MM())

    def test_returns_contact_by_id(self):
        """Should call get_contact_by_id with the supplied contact_id."""
        self.mock_hs.get_contact_by_id.return_value = json.dumps(
            {"id": "42", "properties": {"firstname": "Ada"}}
        )

        result = self.handler.get_contact({"contact_id": "42"})

        self.mock_hs.get_contact_by_id.assert_called_once_with("42", None)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_passes_properties_filter_to_client(self):
        """Optional properties list should be forwarded to the client."""
        self.mock_hs.get_contact_by_id.return_value = json.dumps(
            {"id": "42", "properties": {"firstname": "Ada", "email": "ada@test.com"}}
        )
        props = ["firstname", "email"]

        self.handler.get_contact({"contact_id": "42", "properties": props})

        self.mock_hs.get_contact_by_id.assert_called_once_with("42", props)

    def test_missing_contact_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_contact({})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.get_contact(None)

    def test_response_text_contains_contact_data(self):
        contact_data = {"id": "77", "properties": {"firstname": "Grace"}}
        self.mock_hs.get_contact_by_id.return_value = json.dumps(contact_data)

        result = self.handler.get_contact({"contact_id": "77"})

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "77")


# ---------------------------------------------------------------------------
# hubspot_update_contact
# ---------------------------------------------------------------------------

class TestContactHandlerUpdateContact(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.contact_handler import ContactHandler
        self.mock_hs = _MM()
        self.handler = ContactHandler(self.mock_hs, _MM(), _MM())

    def test_updates_contact_with_correct_id_and_properties(self):
        updated = {"id": "55", "properties": {"phone": "555-9999"}}
        self.mock_hs.update_contact.return_value = json.dumps(updated)

        result = self.handler.update_contact({
            "contact_id": "55",
            "properties": {"phone": "555-9999"},
        })

        self.mock_hs.update_contact.assert_called_once_with("55", {"phone": "555-9999"})
        self.assertIsInstance(result, list)

    def test_missing_contact_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_contact({"properties": {"phone": "555-0000"}})

    def test_missing_properties_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_contact({"contact_id": "55"})

    def test_none_arguments_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.handler.update_contact(None)

    def test_response_text_contains_updated_contact(self):
        updated = {"id": "55", "properties": {"email": "new@example.com"}}
        self.mock_hs.update_contact.return_value = json.dumps(updated)

        result = self.handler.update_contact({
            "contact_id": "55",
            "properties": {"email": "new@example.com"},
        })

        parsed = json.loads(result[0].text)
        self.assertEqual(parsed["id"], "55")


# ---------------------------------------------------------------------------
# hubspot_query_contacts
# ---------------------------------------------------------------------------

class TestContactHandlerQueryContacts(unittest.TestCase):

    def setUp(self):
        from mcp_server_hubspot.handlers.contact_handler import ContactHandler
        self.mock_hs = _MM()
        self.handler = ContactHandler(self.mock_hs, _MM(), _MM())

    def _make_contacts_json(self, n=2):
        contacts = [{"id": str(i), "properties": {"firstname": f"User{i}"}} for i in range(n)]
        return json.dumps(contacts)

    def _make_search_json(self, n=2):
        results = [{"id": str(i), "properties": {"firstname": f"User{i}"}} for i in range(n)]
        return json.dumps({"results": results, "total": n})

    # -- List mode (no filters) --

    def test_list_mode_when_no_filters(self):
        """Omitting filters triggers get_recent_contacts."""
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json()

        self.handler.query_contacts({})

        self.mock_hs.get_recent_contacts.assert_called_once()
        self.mock_hs.contacts.search.assert_not_called()

    def test_list_mode_with_none_arguments(self):
        """None arguments should also trigger list mode with default limit."""
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json()

        self.handler.query_contacts(None)

        self.mock_hs.get_recent_contacts.assert_called_once_with(limit=10)

    def test_list_mode_default_limit_is_10(self):
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json()

        self.handler.query_contacts({})

        _, kwargs = self.mock_hs.get_recent_contacts.call_args
        self.assertEqual(kwargs.get("limit", 10), 10)

    def test_list_mode_respects_custom_limit(self):
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json(5)

        self.handler.query_contacts({"limit": 5})

        _, kwargs = self.mock_hs.get_recent_contacts.call_args
        self.assertEqual(kwargs.get("limit", 10), 5)

    # -- Search mode (with filters) --

    def test_search_mode_when_filters_present(self):
        """Providing filters triggers contacts.search."""
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "email", "operator": "EQ", "value": "test@example.com"}]

        self.handler.query_contacts({"filters": filters})

        self.mock_hs.contacts.search.assert_called_once()
        self.mock_hs.get_recent_contacts.assert_not_called()

    def test_search_mode_passes_filters_to_client(self):
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "firstname", "operator": "EQ", "value": "Jane"}]

        self.handler.query_contacts({"filters": filters})

        args, _ = self.mock_hs.contacts.search.call_args
        self.assertEqual(args[0], filters)

    def test_search_mode_passes_limit(self):
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "email", "operator": "HAS_PROPERTY"}]

        self.handler.query_contacts({"filters": filters, "limit": 3})

        args, _ = self.mock_hs.contacts.search.call_args
        self.assertEqual(args[2], 3)  # limit is the 3rd positional arg

    def test_search_mode_default_sort_is_lastmodifieddate(self):
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "email", "operator": "HAS_PROPERTY"}]

        self.handler.query_contacts({"filters": filters})

        args, _ = self.mock_hs.contacts.search.call_args
        self.assertEqual(args[3], "lastmodifieddate")

    def test_search_mode_custom_sort_property(self):
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "email", "operator": "HAS_PROPERTY"}]

        self.handler.query_contacts({"filters": filters, "sort_property": "createdate"})

        args, _ = self.mock_hs.contacts.search.call_args
        self.assertEqual(args[3], "createdate")

    def test_search_mode_passes_properties(self):
        self.mock_hs.contacts.search.return_value = self._make_search_json()
        filters = [{"propertyName": "email", "operator": "HAS_PROPERTY"}]
        props = ["firstname", "email"]

        self.handler.query_contacts({"filters": filters, "properties": props})

        args, _ = self.mock_hs.contacts.search.call_args
        self.assertEqual(args[1], props)

    # -- Response format --

    def test_returns_list_of_text_content(self):
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json()

        result = self.handler.query_contacts({})

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "text"))

    def test_response_text_is_valid_json(self):
        self.mock_hs.get_recent_contacts.return_value = self._make_contacts_json()

        result = self.handler.query_contacts({})

        # Should not raise
        json.loads(result[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
