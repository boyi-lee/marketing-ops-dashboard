-- Commerce OS P1: PostgreSQL baseline; deploy ONLY to isolated staging DB.
-- No Shopify token or customer PII is stored in these tables.
BEGIN;

CREATE SCHEMA IF NOT EXISTS commerce;

CREATE TABLE IF NOT EXISTS commerce.stores (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commerce.sync_runs (
    id UUID PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    source TEXT NOT NULL CHECK (source IN ('shopify','procurement','finance')),
    state TEXT NOT NULL CHECK (state IN ('running','completed','failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    records_processed INTEGER NOT NULL DEFAULT 0 CHECK (records_processed >= 0)
);
CREATE INDEX IF NOT EXISTS sync_runs_store_started_idx ON commerce.sync_runs (store_id,started_at DESC);

CREATE TABLE IF NOT EXISTS commerce.sync_checkpoints (
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    resource TEXT NOT NULL,
    high_watermark TIMESTAMPTZ,
    cursor TEXT,
    last_successful_run UUID REFERENCES commerce.sync_runs(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id,resource)
);
CREATE TABLE IF NOT EXISTS commerce.products (
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    product_gid TEXT NOT NULL,
    title TEXT NOT NULL,
    vendor TEXT,
    product_type TEXT,
    source_updated_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id,product_gid)
);
CREATE TABLE IF NOT EXISTS commerce.variants (
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    variant_gid TEXT NOT NULL,
    product_gid TEXT NOT NULL,
    sku TEXT,
    price NUMERIC(18,2) NOT NULL CHECK (price >= 0),
    inventory_quantity INTEGER,
    source_updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (store_id,variant_gid),
    FOREIGN KEY (store_id,product_gid) REFERENCES commerce.products(store_id,product_gid)
);
CREATE INDEX IF NOT EXISTS variants_store_sku_idx ON commerce.variants(store_id,sku);

CREATE TABLE IF NOT EXISTS commerce.raw_snapshots (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES commerce.sync_runs(id),
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    kind TEXT NOT NULL,
    resource_gid TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE(store_id,kind,resource_gid,payload_hash)
);
CREATE INDEX IF NOT EXISTS raw_store_kind_idx ON commerce.raw_snapshots(store_id,kind,resource_gid);

CREATE TABLE IF NOT EXISTS commerce.inbound_lines (
    id UUID PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    source_document_id TEXT NOT NULL,
    external_sku TEXT NOT NULL,
    expected_qty INTEGER NOT NULL CHECK (expected_qty >= 0),
    status TEXT NOT NULL CHECK (status IN ('tentative','confirmed','cancelled','received')),
    expected_available_at TIMESTAMPTZ,
    source_checked_at TIMESTAMPTZ NOT NULL,
    source_hash CHAR(64) NOT NULL,
    UNIQUE(store_id,source_document_id,external_sku)
);

CREATE TABLE IF NOT EXISTS commerce.cost_records (
    id UUID PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    variant_gid TEXT,
    source_document_id TEXT NOT NULL,
    unit_cost NUMERIC(18,4) NOT NULL CHECK (unit_cost >= 0),
    currency CHAR(3) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    source_hash CHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS cost_store_variant_effective_idx ON commerce.cost_records(store_id,variant_gid,effective_at DESC);

CREATE TABLE IF NOT EXISTS commerce.plans (
    id UUID PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES commerce.stores(id),
    name TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL CHECK (period_end >= period_start),
    state TEXT NOT NULL CHECK (state IN ('draft','in_review','approved','archived')),
    source_snapshot_id UUID REFERENCES commerce.raw_snapshots(id),
    rule_version TEXT NOT NULL,
    draft JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commerce.audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id TEXT REFERENCES commerce.stores(id),
    actor_id TEXT,
    action TEXT NOT NULL,
    resource_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- No DB login or table grants supplied here: provisioning must allocate scoped read roles.
-- Implement RLS or database roles and test isolation before connecting real merchant data.
COMMIT;
