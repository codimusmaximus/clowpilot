# Workspace Design

## Mental model

The workspace is a **graph with a tree overlay**.

- **Path** gives every node a location in a navigable hierarchy (like a filesystem or Obsidian vault)
- **Links** connect nodes to each other, forming a knowledge graph with backlinks
- Every item — file, email, invoice, system connection — is a first-class node

This means you can navigate by path ("open /invoices/INV-001") and traverse by relationship ("show me everything linked to this invoice"). Both views are over the same data.

---

## Node types

| Type | Description | Has data payload? |
|------|-------------|-------------------|
| `folder` | Organises other nodes. Can carry a schema that types its children into a collection. | No |
| `document` | Content you read as a whole. Notes, PDFs, scripts, exports, receipts. | Yes — `content` (text) |
| `record` | Structured fields, queryable. An invoice, email, transaction, contact. | Yes — `fields` (JSON) |
| `system` | External integration. Gmail, Xero, an MCP server. Not data — an access point that can produce or sync records and documents. | No (config in node) |

`kind` is a subtype within each type:

| type | kind examples |
|------|---------------|
| document | markdown, pdf, python, csv, receipt |
| record | invoice, email, transaction, contact, event |
| system | mcp, rest, imap, oauth |
| folder | (plain folder, or named collection e.g. "invoices") |

---

## Schema — three tables

### `nodes`
Everything that exists in the workspace. The tree is a `SELECT` on this table ordered by path.

```sql
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,       -- uuid
    path        TEXT UNIQUE NOT NULL,   -- e.g. /invoices/INV-001
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('folder', 'document', 'record', 'system')),
    kind        TEXT NOT NULL,          -- subtype: markdown, invoice, mcp, ...
    config      TEXT,                   -- JSON: system credentials, collection schema, doc metadata
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
```

### `data`
Payload for nodes that have content. One row per node, only present for `document` and `record` nodes.

```sql
CREATE TABLE data (
    node_id     TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
    content     TEXT,                   -- populated for documents
    fields      TEXT,                   -- JSON, populated for records
    embedding   BLOB,                   -- vector for semantic search
    external_id TEXT,                   -- id in the source system (for synced nodes)
    synced_at   REAL                    -- last pull from external system
);
```

### `links`
Directed edges between nodes. Backlinks are a reverse query on this table.

```sql
CREATE TABLE links (
    id           TEXT PRIMARY KEY,      -- uuid
    from_node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id   TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    relation     TEXT NOT NULL,         -- e.g. vendor, extracted_from, paid_by, references
    created_at   REAL NOT NULL
);

CREATE INDEX links_from ON links(from_node_id);
CREATE INDEX links_to   ON links(to_node_id);
```

---

## Example: accounting automation

```
/systems/xero               system   (kind: rest)
/systems/gmail              system   (kind: imap)

/contacts/acme-corp         record   (kind: contact)   fields: {name, email, vat_id, ...}
/contacts/best-supplier     record   (kind: contact)

/invoices/INV-001           record   (kind: invoice)   fields: {amount, currency, due_date, status, line_items}
/invoices/INV-002           record   (kind: invoice)

/emails/abc123              record   (kind: email)     fields: {from, to, subject, body, date, labels}

/transactions/TXN-789       record   (kind: transaction) fields: {date, amount, account, category}

/notes/q1-review.md         document (kind: markdown)
/reports/reconciliation.py  document (kind: python)
```

Links:
```
INV-001  → acme-corp    (vendor)
INV-001  → abc123       (extracted_from)
INV-001  → TXN-789      (paid_by)
INV-002  → acme-corp    (vendor)
q1-review.md → INV-001  (references)
q1-review.md → INV-002  (references)
```

Backlinks on `acme-corp`: INV-001, INV-002 — all invoices for this vendor, without a join on a separate invoices table.

---

## Agent tools (planned)

**Tree / navigation**
- `list_tree(path)` — existing, extended to all node types
- `get_node(path)` — metadata + data for one node
- `create_node(path, type, kind, fields|content, config)` — unified create
- `update_node(path, ...)` — update fields, content, or config
- `delete_node(path)` — cascades data and links
- `move_node(source, destination)` — existing move_path, renamed

**Graph**
- `link_nodes(from, to, relation)` — create a directed link
- `get_links(path)` — outgoing links from a node
- `get_backlinks(path)` — incoming links to a node
- `unlink_nodes(from, to, relation)` — remove a link

**Search**
- `search(query)` — semantic search across all data embeddings
- `query_records(collection, filters)` — structured filter on record fields

**Systems**
- `connect_system(path, kind, config)` — register an external connection
- `browse_system(path, ...)` — live query without pulling
- `pull_from_system(path, ...)` — fetch items into local nodes, create links to source

---

## Migration path

The current `files` and `folders` tables map cleanly:
- `files` → nodes (type: document) + data (content populated)
- `folders` → nodes (type: folder)

Existing tools (`write_file`, `read_file`, `delete_file`, etc.) can be reimplemented as thin wrappers over `create_node` / `get_node` / `delete_node` during transition.
