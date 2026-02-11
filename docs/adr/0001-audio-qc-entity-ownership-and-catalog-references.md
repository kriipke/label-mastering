# ADR 0001: Audio QC Entity Ownership and Catalog References

- **Status:** Accepted
- **Date:** 2026-02-11
- **Decision Makers:** Audio QC + Catalog Integration Team

## Context

Audio QC workflows need strong boundaries between data that Audio QC owns and data that originates in the Catalog service. Without clear ownership, teams can accidentally mutate editorial catalog records from QC pipelines or rely on stale entity references during review and approvals.

This ADR defines:

1. Authoritative (Audio QC-owned) entities versus externally referenced entities.
2. Field-level storage rules (local snapshots vs foreign IDs).
3. Read/write boundaries between Audio QC and Catalog.
4. Sync strategy for keeping external references fresh.
5. Failure behavior when upstream references are missing or soft-deleted.

## Decision

### 1) Entity authority model

#### Audio QC authoritative entities (owned in Audio QC database)

- `qc_job`
  - Represents a queued or running QC operation for one mix upload or batch.
  - Lifecycle (queued/running/succeeded/failed/cancelled) is fully controlled by Audio QC.
- `qc_result`
  - Represents immutable or append-only outputs of QC analysis (loudness, peaks, checks, pass/fail details).
  - Produced and versioned by Audio QC execution logic.
- `mix_upload`
  - Represents uploaded asset metadata (storage key, checksum, detected format, uploader, upload timestamp).
  - Source-of-truth for technical file identity and ingest provenance in QC.

#### Externally referenced entities (owned by Catalog)

- `release`
- `track`
- `artist`

Audio QC stores references and limited read models for these entities but **does not** become their system of record.

---

### 2) Local snapshots vs foreign IDs

Audio QC must always persist stable foreign IDs for catalog entities and may optionally persist denormalized snapshots to support query speed, auditability, and resilience to temporary Catalog outages.

#### Required foreign ID fields

In Audio QC records that reference catalog entities:

- `external_release_id` (nullable only before link-time)
- `external_track_id` (nullable for release-level jobs; required for track-level jobs)
- `external_artist_ids` (0..n array/set, depending on modeling choice)

These IDs are opaque strings from Catalog and must not be repurposed as editable business metadata.

#### Optional local snapshot fields

Use snapshot fields only for display/audit/query convenience, not as authority:

- Release snapshots: `release_title_snapshot`, `release_catalog_number_snapshot`, `release_status_snapshot`
- Track snapshots: `track_title_snapshot`, `track_version_snapshot`, `track_duration_snapshot`
- Artist snapshots: `artist_display_names_snapshot`

Snapshot fields must be treated as **cache-like** and may lag source-of-truth.

#### Version/etag companion fields (required)

To prevent stale references and allow optimistic refresh behavior, Audio QC stores catalog version markers per entity link:

- `release_ref_version` (string/int; Catalog monotonic version if provided)
- `track_ref_version` (string/int)
- `artist_refs_version` (string/int or hash over artists payload)
- `release_ref_etag` (string, optional if Catalog uses HTTP ETag)
- `track_ref_etag` (string)
- `artist_refs_etag` (string or hash)
- `catalog_snapshot_fetched_at` (timestamp of last successful hydration)

If both version and ETag are available, persist both; compare version first for semantic drift checks, ETag for transport cache validation.

---

### 3) Read/write rules

#### Allowed writes by Audio QC

- Create/update/delete only Audio QC-owned entities (`qc_job`, `qc_result`, `mix_upload`, and QC-internal linking tables).
- Persist foreign IDs and snapshot cache fields in QC-owned tables.
- Persist QC-specific workflow state tied to external references (e.g., `catalog_reference_state = valid|missing|soft_deleted|stale`).

#### Forbidden writes by Audio QC

Audio QC **must not** mutate Catalog-owned editorial/business metadata, including but not limited to:

- Release title, release type, catalog number, label attribution
- Track title, mix name, duration authority, explicitness flags
- Artist canonical name/credits/ordering
- Any release/track/artist publish status or rights metadata

Any desired changes must be sent through Catalog APIs/workflows that enforce Catalog ownership and validations.

---

### 4) Synchronization strategy

Use a **hybrid strategy**:

1. **Event-driven refresh (primary):**
   - Consume Catalog domain events for `release`, `track`, `artist` updates/deletes/soft-deletes.
   - For affected QC rows, refresh snapshots and version/etag markers asynchronously.
   - Mark references stale (`catalog_reference_state=stale`) until refresh succeeds.

2. **On-demand lookup (fallback and read repair):**
   - On QC read/execute paths, if snapshot is missing, stale beyond TTL, or version mismatch is detected, fetch current Catalog record synchronously (with timeout budget).
   - Update local snapshot/version/etag on success.

This approach minimizes staleness while keeping QC resilient if event delivery is delayed.

Recommended operational defaults:

- Snapshot TTL for operational reads: 15–60 minutes (environment-configurable)
- Hard max staleness tolerated for final approval decisions: 24 hours
- Conditional GETs with `If-None-Match` or version checks to reduce Catalog load

---

### 5) Failure behavior for missing/soft-deleted upstream records

When Catalog lookup fails or indicates deletion state:

- **Missing record (404 / never existed / detached):**
  - Set `catalog_reference_state=missing`
  - Block creation of new `qc_job` that requires the missing entity.
  - Existing historical `qc_result` remains readable for audit but is flagged with missing reference.

- **Soft-deleted record:**
  - Set `catalog_reference_state=soft_deleted`
  - Disallow new QC submissions tied to the soft-deleted entity.
  - Keep previous QC artifacts immutable and visible to admins/auditors.

- **Catalog unavailable / timeout:**
  - Set `catalog_reference_state=unknown` or retain prior state with `catalog_reference_check_error`.
  - Allow non-final or draft QC operations only when prior reference was recently valid and within TTL.
  - Block final approval transitions when external state cannot be validated.

All blocked actions must return actionable errors that include the entity type, external ID, and failure reason.

## Concrete schema notes

The following conventions are required for all QC tables that reference Catalog entities:

- `external_release_id`
  - Type: `VARCHAR(64)` (or UUID if Catalog guarantees UUID)
  - Nullability: nullable until association, then NOT NULL where release linkage is mandatory
  - Index: BTREE index (frequent filtering/join key)
  - Constraint: foreign-system semantic only (no DB foreign key across services)

- `external_track_id`
  - Type: `VARCHAR(64)` (or UUID)
  - Nullability: nullable for release-level-only jobs; NOT NULL for track-level workflows
  - Index: BTREE index; composite index with `external_release_id` where common

- Version/etag fields
  - `release_ref_version`, `track_ref_version`: `VARCHAR(64)` (portable across int/string versions)
  - `release_ref_etag`, `track_ref_etag`: `VARCHAR(128)`
  - `catalog_snapshot_fetched_at`: `TIMESTAMPTZ NOT NULL DEFAULT now()` when snapshot exists
  - Add check or app invariant: if snapshot columns are present, at least one of version or etag must be present

- Uniqueness/integrity guidance
  - Do **not** enforce uniqueness of external IDs globally unless business rules require one-to-one mapping.
  - Enforce local uniqueness where needed (e.g., one active `qc_job` per `mix_upload` + profile).

## Consequences

### Positive

- Clear ownership boundaries reduce accidental cross-service data corruption.
- Strong traceability with snapshot + version/etag supports audits and stale-data diagnostics.
- Hybrid sync improves resilience and consistency.

### Trade-offs

- Additional storage for snapshot and version metadata.
- More state transitions (`valid/stale/missing/soft_deleted/unknown`) to handle in application logic.
- Requires reliable event subscription and dead-letter handling for Catalog change events.

## Implementation notes

- Introduce an internal `catalog_reference_state` enum in QC domain.
- Add background worker for event-driven rehydration and stale-marker clearing.
- Add guardrails in command handlers so final approval cannot proceed with invalid external references.
- Add observability counters:
  - `catalog_ref_refresh_success_total`
  - `catalog_ref_refresh_failure_total`
  - `qc_actions_blocked_missing_catalog_ref_total`

