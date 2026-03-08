---
name: hubspot-contacts
description: Manage HubSpot contacts — create, retrieve, update, and search. Invoke when the user asks about contacts, leads, people, or CRM person records.
context: fork
mcpServers:
  - hubspot-contacts
allowed-tools: mcp__hubspot-contacts
---

# HubSpot Contacts

You have access to 5 focused contact tools. Use them to complete the user's request: $ARGUMENTS

## Available tools

| Tool | When to use |
|------|-------------|
| `hubspot_create_contact` | Create a new person record. Checks duplicates by name automatically. |
| `hubspot_get_contact` | Fetch a single contact by ID. Pass `properties` array to limit fields returned. |
| `hubspot_update_contact` | Update one or more properties on an existing contact. |
| `hubspot_query_contacts` | List recently active contacts (omit `filters`) **or** search by property filters. Single tool for both list and search. |

## Best practices

1. **Duplicate prevention** — always use `hubspot_search_contacts` with name/email filters before calling `hubspot_create_contact`.
2. **Sparse fetches** — pass a `properties` list to `hubspot_get_contact` instead of fetching all fields; this reduces token usage on the response.
3. **Search first** — for find-or-create workflows, search first, then create only if `total == 0`.
4. **Batch reads** — if you need multiple contacts, call `hubspot_search_contacts` with an `EQ` filter list rather than looping `hubspot_get_contact`.

## Required HubSpot scopes

`crm.objects.contacts` (read + write)
