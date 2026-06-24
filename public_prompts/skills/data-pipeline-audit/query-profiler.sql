-- =============================================================
-- Data Pipeline Query Profiler for PostgreSQL
-- =============================================================
-- Identifies slow queries, missing indexes, full table scans,
-- and other performance bottlenecks in pipeline databases.
--
-- Requirements: PostgreSQL 12+ with pg_stat_statements enabled
-- Usage: Run each query independently against your target database
-- Permissions: Requires read access to pg_stat_statements and
--              pg_catalog system views
-- =============================================================


-- 1. TOP 20 SLOWEST QUERIES BY TOTAL EXECUTION TIME
-- Shows queries consuming the most cumulative database time.
-- Look for: high total_time with low calls = occasional heavy query
--           high total_time with high calls = frequent bottleneck
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_time_ms,
    round(mean_exec_time::numeric, 2) AS avg_time_ms,
    round(max_exec_time::numeric, 2) AS max_time_ms,
    rows AS total_rows_returned,
    round((shared_blks_hit::numeric /
           NULLIF(shared_blks_hit + shared_blks_read, 0)) * 100, 1
    ) AS cache_hit_pct,
    left(query, 200) AS query_preview
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;


-- 2. QUERIES WITH LOW CACHE HIT RATIO
-- Queries reading heavily from disk rather than shared buffers.
-- Low cache hit ratio (<90%) suggests missing indexes or
-- working set exceeding available memory.
SELECT
    queryid,
    calls,
    shared_blks_read AS disk_reads,
    shared_blks_hit AS cache_hits,
    round((shared_blks_hit::numeric /
           NULLIF(shared_blks_hit + shared_blks_read, 0)) * 100, 1
    ) AS cache_hit_pct,
    round(mean_exec_time::numeric, 2) AS avg_time_ms,
    left(query, 200) AS query_preview
FROM pg_stat_statements
WHERE shared_blks_read > 100
  AND (shared_blks_hit::numeric /
       NULLIF(shared_blks_hit + shared_blks_read, 0)) < 0.90
ORDER BY shared_blks_read DESC
LIMIT 20;


-- 3. TABLES WITH SEQUENTIAL SCANS (POTENTIAL FULL TABLE SCANS)
-- Tables being sequentially scanned frequently likely need indexes.
-- Focus on tables with high seq_scan count and large row counts.
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    n_live_tup AS estimated_rows,
    CASE
        WHEN idx_scan > 0
        THEN round((seq_scan::numeric / (seq_scan + idx_scan)) * 100, 1)
        ELSE 100.0
    END AS seq_scan_pct,
    pg_size_pretty(pg_relation_size(schemaname || '.' || relname)) AS table_size
FROM pg_stat_user_tables
WHERE seq_scan > 50
  AND n_live_tup > 10000
ORDER BY seq_tup_read DESC
LIMIT 20;


-- 4. MISSING INDEX CANDIDATES
-- Tables where sequential scans read many tuples but have few or no indexes.
-- These are strong candidates for index creation.
SELECT
    relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    n_live_tup AS estimated_rows,
    round(seq_tup_read::numeric / NULLIF(seq_scan, 0), 0) AS avg_rows_per_scan,
    pg_size_pretty(pg_relation_size(relid)) AS table_size
FROM pg_stat_user_tables
WHERE seq_scan > 100
  AND seq_tup_read > 100000
  AND (idx_scan IS NULL OR idx_scan < seq_scan * 0.1)
ORDER BY seq_tup_read DESC
LIMIT 15;


-- 5. UNUSED INDEXES (CANDIDATES FOR REMOVAL)
-- Indexes that exist but are rarely or never used waste space and
-- slow down write operations. Review before dropping.
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan AS times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size
FROM pg_stat_user_indexes
WHERE idx_scan < 10
  AND indexrelname NOT LIKE '%_pkey'
  AND indexrelname NOT LIKE '%_unique'
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;


-- 6. TABLE BLOAT ESTIMATION
-- Identifies tables with significant dead tuple bloat that may need
-- VACUUM or maintenance. High dead tuple ratio degrades scan performance.
SELECT
    schemaname,
    relname AS table_name,
    n_live_tup,
    n_dead_tup,
    CASE
        WHEN n_live_tup > 0
        THEN round((n_dead_tup::numeric / n_live_tup) * 100, 1)
        ELSE 0
    END AS dead_pct,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    pg_size_pretty(pg_relation_size(relid)) AS table_size
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC
LIMIT 20;


-- 7. LONG-RUNNING ACTIVE QUERIES
-- Current queries that have been running longer than 5 minutes.
-- May indicate stuck pipeline jobs or missing query timeouts.
SELECT
    pid,
    now() - pg_stat_activity.query_start AS duration,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_preview
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
  AND state != 'idle'
  AND query NOT ILIKE '%pg_stat_activity%'
ORDER BY duration DESC;


-- 8. CONNECTION UTILIZATION
-- Shows current connection usage relative to max_connections.
-- Pipeline jobs that hold connections can starve other workloads.
SELECT
    max_conn,
    used,
    max_conn - used AS available,
    round((used::numeric / max_conn) * 100, 1) AS utilization_pct
FROM
    (SELECT count(*) AS used FROM pg_stat_activity) AS activity,
    (SELECT setting::int AS max_conn FROM pg_settings
     WHERE name = 'max_connections') AS settings;
