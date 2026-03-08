---
name: hubspot-deals
description: Manage HubSpot deals — create, retrieve, update, search, and move through pipeline stages. Invoke when the user asks about deals, opportunities, revenue, pipeline, or sales stages.
context: fork
mcpServers:
  - hubspot-deals
allowed-tools: mcp__hubspot-deals
---

# HubSpot Deals

You have access to 7 focused deal tools. Use them to complete the user's request: $ARGUMENTS

## Available tools

| Tool | When to use |
|------|-------------|
| `hubspot_create_deal` | Create a new deal. `dealname` is required; `dealstage`, `pipeline`, `amount`, `closedate` are optional. |
| `hubspot_get_deal` | Fetch a single deal by ID. Pass `properties` array to limit fields returned. |
| `hubspot_update_deal` | Update one or more properties on an existing deal. |
| `hubspot_query_deals` | List recently modified deals (omit `filters`) **or** search by property filters. Single tool for both list and search. |
| `hubspot_get_pipelines` | List all pipelines with their stages. Always use `object_type="deals"`. Call this first to get valid `dealstage` IDs. |
| `hubspot_move_deal_stage` | Move a deal to a different stage within its pipeline. |

## Best practices

1. **Always get stages first** — before creating or moving a deal, call `hubspot_get_pipelines` with `object_type="deals"` to get valid stage IDs. Never guess stage IDs.
2. **Sparse fetches** — pass a `properties` list to `hubspot_get_deal` instead of fetching all fields.
3. **Search before create** — use `hubspot_search_deals` with a `dealname` EQ filter to avoid duplicates.
4. **Stage moves vs property updates** — use `hubspot_move_deal_stage` (not `hubspot_update_deal`) when the primary intent is advancing a deal through the pipeline.
5. **Amount format** — `amount` is always a string (e.g., `"5000"` not `5000`).

## Required HubSpot scopes

`crm.objects.deals` (read + write)
