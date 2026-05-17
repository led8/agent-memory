# Graph Linker — Semantic Neighborhood Linking

## Overview

The GraphLinker (`src/neo4j_agent_memory/graph/linker.py`) creates `RELATES_TO`
edges between semantically similar nodes across all memory layers. It transforms
isolated vector-store nodes into a connected knowledge graph with meaningful
clusters.

## How It Works

1. A new node is created with an embedding (e.g., `add_fact()`)
2. GraphLinker queries all relevant vector indexes to find the top-N most similar existing nodes
3. For each neighbor above the similarity threshold, a `RELATES_TO` edge is created
4. Edges carry metadata: `similarity`, `link_method=embedding_similarity`, `linked_at`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ MemoryClient.connect()                                  │
│   → GraphLinker(client, LinkerConfig)                   │
│   → long_term.set_linker(linker)                        │
│   → short_term.set_linker(linker)                       │
│   → reasoning.set_linker(linker)                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ On write (add_fact, add_preference, add_message, ...)   │
│   → linker.link_to_neighborhood(node_id, label, embed)  │
│     → query vector indexes (cross-layer)                │
│     → filter: self-exclusion, threshold, max cap        │
│     → CREATE (source)-[:RELATES_TO {similarity}]->(tgt) │
└─────────────────────────────────────────────────────────┘
```

## Configuration

`LinkerConfig` fields (all optional, sensible defaults):

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `True` | Enable/disable linking globally |
| `max_neighbors` | `5` | Maximum edges per node per write |
| `min_similarity` | `0.75` | Minimum cosine similarity threshold |
| `cross_label` | `True` | Search across all node types |
| `exclude_labels` | `[]` | Labels to skip during search |

## Vector Index Registry

| Label | Index Name |
|-------|-----------|
| Fact | `fact_embedding_idx` |
| Preference | `preference_embedding_idx` |
| Message | `message_embedding_idx` |
| ReasoningTrace | `task_embedding_idx` |

## CLI Commands

```bash
# Backfill orphan nodes (no existing RELATES_TO edges)
neo4j-agent-memory memory link-neighbors --backfill

# Restrict to a single label
neo4j-agent-memory memory link-neighbors --backfill --label Fact

# Override thresholds
neo4j-agent-memory memory link-neighbors --backfill --min-similarity 0.7 --max-neighbors 3

# Full pass (all nodes, not just orphans)
neo4j-agent-memory memory link-neighbors --label Fact --batch-size 100
```

## Edge Schema

```cypher
(source)-[:RELATES_TO {
  similarity: 0.87,
  link_method: "embedding_similarity",
  linked_at: datetime()
}]->(target)
```

Edges are bidirectional in semantics but stored as directed. The `MERGE` pattern
avoids duplicates when both nodes would link to each other.

## Design Decisions

- **Embedding-based, not tag-based**: Avoids the noise of shared-keyword linking (the voidm migration created 330 noisy edges from generic tags like "cli")
- **Cross-layer by default**: A Message can link to a Fact, a Trace to a Preference — this creates richer graph topology
- **Max degree cap**: Prevents hub explosion where popular nodes collect hundreds of edges
- **Conservative defaults**: 0.75 threshold avoids false positives; tunable per deployment
- **Graph-level service**: Lives in `graph/` not `memory/` — usable by any layer
