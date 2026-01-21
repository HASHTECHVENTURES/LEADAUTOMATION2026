-- Enhanced Supabase Database Schema with Optimizations
-- Run this SQL in your Supabase SQL Editor to improve performance
-- This adds advanced indexes, full-text search, and optimizations

-- ============================================
-- 1. COMPOSITE INDEXES (for multi-column queries)
-- ============================================

-- For Level 1: Common query pattern (project_name + selected_for_level2)
CREATE INDEX IF NOT EXISTS idx_level1_project_selected 
ON level1_companies(project_name, selected_for_level2) 
WHERE selected_for_level2 = true;

-- For Level 1: Project + date sorting (faster project list queries)
CREATE INDEX IF NOT EXISTS idx_level1_project_date 
ON level1_companies(project_name, search_date DESC);

-- For Level 2: Batch + project queries
CREATE INDEX IF NOT EXISTS idx_level2_batch_project 
ON level2_contacts(batch_name, project_name);

-- For Level 2: Company + contact type (common filter)
CREATE INDEX IF NOT EXISTS idx_level2_company_type 
ON level2_contacts(company_name, contact_type);

-- For Level 2: Email lookup (faster duplicate detection)
CREATE INDEX IF NOT EXISTS idx_level2_email 
ON level2_contacts(email) 
WHERE email IS NOT NULL AND email != '';

-- ============================================
-- 2. FULL-TEXT SEARCH INDEXES
-- ============================================

-- Enable full-text search for company names (Level 1)
CREATE INDEX IF NOT EXISTS idx_level1_company_name_fts 
ON level1_companies USING gin(to_tsvector('english', company_name));

-- Enable full-text search for contact names (Level 2)
CREATE INDEX IF NOT EXISTS idx_level2_contact_name_fts 
ON level2_contacts USING gin(to_tsvector('english', contact_name));

-- Enable full-text search for company names (Level 2)
CREATE INDEX IF NOT EXISTS idx_level2_company_name_fts 
ON level2_contacts USING gin(to_tsvector('english', company_name));

-- ============================================
-- 3. UNIQUE CONSTRAINTS (prevent duplicates)
-- ============================================

-- Prevent duplicate emails in contacts (optional - uncomment if needed)
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_level2_email_unique 
-- ON level2_contacts(email) 
-- WHERE email IS NOT NULL AND email != '';

-- ============================================
-- 4. MATERIALIZED VIEWS (for faster analytics)
-- ============================================

-- Project statistics view (refreshes on demand)
CREATE MATERIALIZED VIEW IF NOT EXISTS project_stats AS
SELECT 
    project_name,
    COUNT(*) as total_companies,
    COUNT(CASE WHEN selected_for_level2 = true THEN 1 END) as selected_companies,
    MAX(search_date) as last_search_date,
    MIN(search_date) as first_search_date,
    COUNT(DISTINCT industry) as industries_count,
    COUNT(DISTINCT pin_code) as pin_codes_count
FROM level1_companies
GROUP BY project_name;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_stats_name 
ON project_stats(project_name);

-- Batch statistics view
CREATE MATERIALIZED VIEW IF NOT EXISTS batch_stats AS
SELECT 
    batch_name,
    project_name,
    COUNT(*) as total_contacts,
    COUNT(CASE WHEN email IS NOT NULL AND email != '' THEN 1 END) as contacts_with_email,
    COUNT(DISTINCT company_name) as unique_companies,
    COUNT(DISTINCT contact_type) as contact_types_count,
    MAX(created_at) as last_updated
FROM level2_contacts
GROUP BY batch_name, project_name;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_batch_stats_batch 
ON batch_stats(batch_name, project_name);

-- ============================================
-- 5. FUNCTIONS FOR COMMON OPERATIONS
-- ============================================

-- Function to refresh materialized views
CREATE OR REPLACE FUNCTION refresh_project_stats()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY project_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY batch_stats;
END;
$$ LANGUAGE plpgsql;

-- Function to get project summary (faster than querying all companies)
CREATE OR REPLACE FUNCTION get_project_summary(p_project_name TEXT)
RETURNS TABLE (
    project_name TEXT,
    total_companies BIGINT,
    selected_companies BIGINT,
    last_search_date TIMESTAMP,
    industries TEXT[],
    pin_codes TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.project_name,
        p.total_companies,
        p.selected_companies,
        p.last_search_date,
        ARRAY_AGG(DISTINCT l1.industry) FILTER (WHERE l1.industry IS NOT NULL) as industries,
        ARRAY_AGG(DISTINCT l1.pin_code) FILTER (WHERE l1.pin_code IS NOT NULL) as pin_codes
    FROM project_stats p
    LEFT JOIN level1_companies l1 ON l1.project_name = p.project_name
    WHERE p.project_name = p_project_name
    GROUP BY p.project_name, p.total_companies, p.selected_companies, p.last_search_date;
END;
$$ LANGUAGE plpgsql;

-- Function to search companies by name (full-text search)
CREATE OR REPLACE FUNCTION search_companies(
    p_project_name TEXT DEFAULT NULL,
    p_search_term TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT 50
)
RETURNS TABLE (
    id BIGINT,
    project_name TEXT,
    company_name TEXT,
    website TEXT,
    phone TEXT,
    address TEXT,
    industry TEXT,
    pin_code TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        l1.id,
        l1.project_name,
        l1.company_name,
        l1.website,
        l1.phone,
        l1.address,
        l1.industry,
        l1.pin_code
    FROM level1_companies l1
    WHERE 
        (p_project_name IS NULL OR l1.project_name = p_project_name)
        AND (
            p_search_term IS NULL 
            OR to_tsvector('english', l1.company_name) @@ plainto_tsquery('english', p_search_term)
            OR l1.company_name ILIKE '%' || p_search_term || '%'
        )
    ORDER BY 
        CASE 
            WHEN p_search_term IS NOT NULL 
            THEN ts_rank(to_tsvector('english', l1.company_name), plainto_tsquery('english', p_search_term))
            ELSE 0
        END DESC,
        l1.search_date DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 6. AUTOMATIC CLEANUP (optional)
-- ============================================

-- Function to clean old progress tracking records (older than 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_progress()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM progress_tracking
    WHERE status = 'completed' 
    AND updated_at < NOW() - INTERVAL '7 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 7. PERFORMANCE MONITORING
-- ============================================

-- View to see index usage (helps identify unused indexes)
CREATE OR REPLACE VIEW index_usage_stats AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- ============================================
-- 8. INITIAL DATA REFRESH
-- ============================================

-- Refresh materialized views initially
REFRESH MATERIALIZED VIEW project_stats;
REFRESH MATERIALIZED VIEW batch_stats;

-- ============================================
-- NOTES:
-- ============================================
-- 1. Materialized views need to be refreshed periodically
--    Run: SELECT refresh_project_stats();
--    Or set up a cron job in Supabase to refresh daily
--
-- 2. Full-text search queries:
--    SELECT * FROM search_companies('project_name', 'search term', 50);
--
-- 3. To monitor index usage:
--    SELECT * FROM index_usage_stats;
--
-- 4. To clean old progress records:
--    SELECT cleanup_old_progress();
--
-- 5. Composite indexes are most effective when queries filter
--    by the leftmost columns in the index
-- ============================================


