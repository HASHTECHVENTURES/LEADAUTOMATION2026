-- ============================================
-- COMPLETE SUPABASE SCHEMA FOR BUSINESS OUTREACH AUTOMATION
-- Production-ready with all features
-- Run this entire file in Supabase SQL Editor
-- ============================================

-- ============================================
-- 1. BASE TABLES
-- ============================================

-- Table: level1_companies
-- Stores company data from Google Places API (Level 1 search results)
CREATE TABLE IF NOT EXISTS level1_companies (
    id BIGSERIAL PRIMARY KEY,
    project_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    website TEXT,
    phone TEXT,
    address TEXT,
    industry TEXT,  -- User's search industry (e.g., "IT")
    place_type TEXT,  -- Google's detected category (e.g., "General Business")
    pin_code TEXT,
    pin_codes_searched TEXT,  -- Comma-separated list of PIN codes searched
    search_date TIMESTAMP,
    place_id TEXT UNIQUE,  -- Google Places ID (unique identifier)
    business_status TEXT,
    selected_for_level2 BOOLEAN DEFAULT FALSE,
    total_employees TEXT,  -- Company total employees from Apollo.io
    active_members INTEGER,  -- Active contacts found
    active_members_with_email INTEGER,  -- Active contacts with email
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Table: level2_contacts
-- Stores enriched contact data from Apollo.io (Level 2 enrichment results)
CREATE TABLE IF NOT EXISTS level2_contacts (
    id BIGSERIAL PRIMARY KEY,
    project_name TEXT NOT NULL,
    batch_name TEXT NOT NULL,  -- User-defined batch name (e.g., "Mumbai IT Batch 1")
    company_name TEXT NOT NULL,
    company_address TEXT,
    company_website TEXT,
    company_phone TEXT,
    company_total_employees TEXT,  -- Total employees in the company (from Apollo org data)
    contact_name TEXT,
    title TEXT,  -- Original job title from Apollo.io (e.g., "CEO", "HR Manager")
    contact_type TEXT,  -- Categorized type: "Founder/Owner", "HR", "Employee"
    phone_number TEXT,  -- Contact's phone number from Apollo.io
    linkedin_url TEXT,
    email TEXT,
    pin_code TEXT,
    industry TEXT,
    search_date TIMESTAMP,
    source TEXT,  -- "apollo" or "web_scraping"
    created_at TIMESTAMP DEFAULT NOW()
);

-- Table: progress_tracking
-- Stores progress information for long-running operations (serverless-friendly)
CREATE TABLE IF NOT EXISTS progress_tracking (
    id BIGSERIAL PRIMARY KEY,
    session_key TEXT NOT NULL UNIQUE,  -- Unique identifier for the operation (e.g., project_name)
    stage TEXT,  -- Current stage: 'searching_places', 'saving', 'processing', etc.
    message TEXT,  -- Human-readable progress message
    current INTEGER DEFAULT 0,  -- Current progress count
    total INTEGER DEFAULT 0,  -- Total items to process
    companies_found INTEGER DEFAULT 0,  -- Number of companies found
    status TEXT DEFAULT 'in_progress',  -- 'in_progress', 'completed', 'error'
    error_message TEXT,  -- Error message if status is 'error'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 2. DATA VALIDATION & CONSTRAINTS
-- ============================================

-- Drop constraints if they exist, then add them (safe to run multiple times)
DO $$ 
BEGIN
    -- Ensure project_name is never empty
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_project_name_not_empty') THEN
        ALTER TABLE level1_companies DROP CONSTRAINT chk_project_name_not_empty;
    END IF;
    ALTER TABLE level1_companies 
    ADD CONSTRAINT chk_project_name_not_empty 
    CHECK (LENGTH(TRIM(project_name)) > 0);
    
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_project_name_not_empty_contacts') THEN
        ALTER TABLE level2_contacts DROP CONSTRAINT chk_project_name_not_empty_contacts;
    END IF;
    ALTER TABLE level2_contacts 
    ADD CONSTRAINT chk_project_name_not_empty_contacts 
    CHECK (LENGTH(TRIM(project_name)) > 0);
    
    -- Ensure company_name is never empty
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_company_name_not_empty') THEN
        ALTER TABLE level1_companies DROP CONSTRAINT chk_company_name_not_empty;
    END IF;
    ALTER TABLE level1_companies 
    ADD CONSTRAINT chk_company_name_not_empty 
    CHECK (LENGTH(TRIM(company_name)) > 0);
    
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_company_name_not_empty_contacts') THEN
        ALTER TABLE level2_contacts DROP CONSTRAINT chk_company_name_not_empty_contacts;
    END IF;
    ALTER TABLE level2_contacts 
    ADD CONSTRAINT chk_company_name_not_empty_contacts 
    CHECK (LENGTH(TRIM(company_name)) > 0);
    
    -- Validate email format (if email is provided)
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_email_format') THEN
        ALTER TABLE level2_contacts DROP CONSTRAINT chk_email_format;
    END IF;
    ALTER TABLE level2_contacts 
    ADD CONSTRAINT chk_email_format 
    CHECK (email IS NULL OR email = '' OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');
    
    -- Limit text field lengths to prevent abuse
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_project_name_length') THEN
        ALTER TABLE level1_companies DROP CONSTRAINT chk_project_name_length;
    END IF;
    ALTER TABLE level1_companies 
    ADD CONSTRAINT chk_project_name_length 
    CHECK (LENGTH(project_name) <= 200);
    
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_batch_name_length') THEN
        ALTER TABLE level2_contacts DROP CONSTRAINT chk_batch_name_length;
    END IF;
    ALTER TABLE level2_contacts 
    ADD CONSTRAINT chk_batch_name_length 
    CHECK (LENGTH(batch_name) <= 200);
END $$;

-- ============================================
-- 3. INDEXES FOR PERFORMANCE
-- ============================================

-- Basic indexes
CREATE INDEX IF NOT EXISTS idx_level1_project_name ON level1_companies(project_name);
CREATE INDEX IF NOT EXISTS idx_level1_selected ON level1_companies(selected_for_level2);
CREATE INDEX IF NOT EXISTS idx_level1_search_date ON level1_companies(search_date DESC);
CREATE INDEX IF NOT EXISTS idx_level1_place_id ON level1_companies(place_id);

CREATE INDEX IF NOT EXISTS idx_level2_project_name ON level2_contacts(project_name);
CREATE INDEX IF NOT EXISTS idx_level2_batch_name ON level2_contacts(batch_name);
CREATE INDEX IF NOT EXISTS idx_level2_company_name ON level2_contacts(company_name);
CREATE INDEX IF NOT EXISTS idx_level2_contact_type ON level2_contacts(contact_type);

CREATE INDEX IF NOT EXISTS idx_progress_session_key ON progress_tracking(session_key);
CREATE INDEX IF NOT EXISTS idx_progress_status ON progress_tracking(status);
CREATE INDEX IF NOT EXISTS idx_progress_updated_at ON progress_tracking(updated_at DESC);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_level1_project_selected 
ON level1_companies(project_name, selected_for_level2) 
WHERE selected_for_level2 = true;

CREATE INDEX IF NOT EXISTS idx_level1_project_date 
ON level1_companies(project_name, search_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_level2_batch_project 
ON level2_contacts(batch_name, project_name);

CREATE INDEX IF NOT EXISTS idx_level2_email 
ON level2_contacts(email) 
WHERE email IS NOT NULL AND email != '';

-- Full-text search indexes
CREATE INDEX IF NOT EXISTS idx_level1_company_name_fts 
ON level1_companies USING gin(to_tsvector('english', COALESCE(company_name, '')));

CREATE INDEX IF NOT EXISTS idx_level2_contact_name_fts 
ON level2_contacts USING gin(to_tsvector('english', COALESCE(contact_name, '')));

CREATE INDEX IF NOT EXISTS idx_level2_company_name_fts 
ON level2_contacts USING gin(to_tsvector('english', COALESCE(company_name, '')));

-- ============================================
-- 4. TRIGGERS & FUNCTIONS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for level1_companies
DROP TRIGGER IF EXISTS update_level1_companies_updated_at ON level1_companies;
CREATE TRIGGER update_level1_companies_updated_at 
    BEFORE UPDATE ON level1_companies 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for progress_tracking
DROP TRIGGER IF EXISTS update_progress_tracking_updated_at ON progress_tracking;
CREATE TRIGGER update_progress_tracking_updated_at 
    BEFORE UPDATE ON progress_tracking 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 5. MATERIALIZED VIEWS (Pre-computed Stats)
-- ============================================

-- Project statistics
DROP MATERIALIZED VIEW IF EXISTS project_stats;
CREATE MATERIALIZED VIEW project_stats AS
SELECT 
    project_name,
    COUNT(*) as total_companies,
    COUNT(CASE WHEN selected_for_level2 = true THEN 1 END) as selected_companies,
    MAX(search_date) as last_search_date,
    MIN(search_date) as first_search_date,
    COUNT(DISTINCT industry) FILTER (WHERE industry IS NOT NULL) as industries_count,
    COUNT(DISTINCT pin_code) FILTER (WHERE pin_code IS NOT NULL) as pin_codes_count,
    MAX(created_at) as last_created,
    MAX(updated_at) as last_updated
FROM level1_companies
GROUP BY project_name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_stats_name ON project_stats(project_name);

-- Batch statistics
DROP MATERIALIZED VIEW IF EXISTS batch_stats;
CREATE MATERIALIZED VIEW batch_stats AS
SELECT 
    batch_name,
    project_name,
    COUNT(*) as total_contacts,
    COUNT(CASE WHEN email IS NOT NULL AND email != '' THEN 1 END) as contacts_with_email,
    COUNT(CASE WHEN phone_number IS NOT NULL AND phone_number != '' THEN 1 END) as contacts_with_phone,
    COUNT(DISTINCT company_name) as unique_companies,
    COUNT(DISTINCT contact_type) FILTER (WHERE contact_type IS NOT NULL) as contact_types_count,
    MAX(created_at) as last_updated
FROM level2_contacts
GROUP BY batch_name, project_name;

CREATE INDEX IF NOT EXISTS idx_batch_stats_batch ON batch_stats(batch_name, project_name);

-- ============================================
-- 6. HELPER FUNCTIONS
-- ============================================

-- Safe project summary
CREATE OR REPLACE FUNCTION get_project_summary_safe(p_project_name TEXT)
RETURNS TABLE (
    project_name TEXT,
    total_companies BIGINT,
    selected_companies BIGINT,
    last_search_date TIMESTAMP,
    industries TEXT[],
    pin_codes TEXT[]
) AS $$
BEGIN
    IF p_project_name IS NULL OR LENGTH(TRIM(p_project_name)) = 0 THEN
        RAISE EXCEPTION 'Project name cannot be empty';
    END IF;
    
    RETURN QUERY
    SELECT 
        p.project_name,
        p.total_companies,
        p.selected_companies,
        p.last_search_date,
        COALESCE(
            ARRAY_AGG(DISTINCT l1.industry) FILTER (WHERE l1.industry IS NOT NULL),
            ARRAY[]::TEXT[]
        ) as industries,
        COALESCE(
            ARRAY_AGG(DISTINCT l1.pin_code) FILTER (WHERE l1.pin_code IS NOT NULL),
            ARRAY[]::TEXT[]
        ) as pin_codes
    FROM project_stats p
    LEFT JOIN level1_companies l1 ON l1.project_name = p.project_name
    WHERE p.project_name = p_project_name
    GROUP BY p.project_name, p.total_companies, p.selected_companies, p.last_search_date
    LIMIT 1;
EXCEPTION
    WHEN OTHERS THEN
        RETURN;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Safe company search
CREATE OR REPLACE FUNCTION search_companies_safe(
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
    IF p_limit > 1000 THEN
        p_limit := 1000;
    END IF;
    
    IF p_limit < 1 THEN
        p_limit := 50;
    END IF;
    
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
            OR LENGTH(p_search_term) = 0
            OR to_tsvector('english', COALESCE(l1.company_name, '')) @@ plainto_tsquery('english', p_search_term)
            OR l1.company_name ILIKE '%' || p_search_term || '%'
        )
    ORDER BY 
        CASE 
            WHEN p_search_term IS NOT NULL AND LENGTH(p_search_term) > 0
            THEN ts_rank(to_tsvector('english', COALESCE(l1.company_name, '')), plainto_tsquery('english', p_search_term))
            ELSE 0
        END DESC,
        l1.search_date DESC NULLS LAST
    LIMIT p_limit;
EXCEPTION
    WHEN OTHERS THEN
        RETURN;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Refresh materialized views
CREATE OR REPLACE FUNCTION refresh_project_stats_safe()
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY project_stats;
        REFRESH MATERIALIZED VIEW CONCURRENTLY batch_stats;
        result := json_build_object('success', true, 'message', 'Views refreshed successfully');
    EXCEPTION
        WHEN OTHERS THEN
            result := json_build_object(
                'success', false, 
                'message', 'Error refreshing views: ' || SQLERRM
            );
    END;
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Health check
CREATE OR REPLACE FUNCTION health_check()
RETURNS JSON AS $$
DECLARE
    result JSON;
    company_count BIGINT;
    contact_count BIGINT;
    project_count BIGINT;
    batch_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO company_count FROM level1_companies;
    SELECT COUNT(*) INTO contact_count FROM level2_contacts;
    SELECT COUNT(DISTINCT project_name) INTO project_count FROM level1_companies;
    SELECT COUNT(DISTINCT batch_name) INTO batch_count FROM level2_contacts;
    
    result := json_build_object(
        'status', 'healthy',
        'timestamp', NOW(),
        'stats', json_build_object(
            'companies', company_count,
            'contacts', contact_count,
            'projects', project_count,
            'batches', batch_count
        ),
        'database', current_database(),
        'version', version()
    );
    
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Cleanup old progress records
CREATE OR REPLACE FUNCTION cleanup_old_progress_safe()
RETURNS JSON AS $$
DECLARE
    deleted_count INTEGER;
    result JSON;
BEGIN
    BEGIN
        DELETE FROM progress_tracking
        WHERE status = 'completed' 
        AND updated_at < NOW() - INTERVAL '7 days';
        
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        
        result := json_build_object(
            'success', true,
            'deleted_count', deleted_count,
            'message', 'Cleanup completed'
        );
    EXCEPTION
        WHEN OTHERS THEN
            result := json_build_object(
                'success', false,
                'message', 'Error during cleanup: ' || SQLERRM
            );
    END;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- 7. MONITORING VIEWS
-- ============================================

-- Index usage statistics
CREATE OR REPLACE VIEW index_usage_stats AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- Table sizes
CREATE OR REPLACE VIEW table_sizes AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as indexes_size,
    n_live_tup as row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================
-- 8. INITIAL SETUP
-- ============================================

-- Refresh materialized views
REFRESH MATERIALIZED VIEW project_stats;
REFRESH MATERIALIZED VIEW batch_stats;

-- ============================================
-- 9. GRANT PERMISSIONS
-- ============================================

-- Grant execute permissions on functions
GRANT EXECUTE ON FUNCTION get_project_summary_safe(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION search_companies_safe(TEXT, TEXT, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION refresh_project_stats_safe() TO authenticated;
GRANT EXECUTE ON FUNCTION health_check() TO authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_progress_safe() TO authenticated;

-- Grant select on views
GRANT SELECT ON index_usage_stats TO authenticated;
GRANT SELECT ON table_sizes TO authenticated;

-- ============================================
-- COMPLETE! ✅
-- ============================================
-- This schema includes:
-- ✅ All base tables (level1_companies, level2_contacts, progress_tracking)
-- ✅ Data validation constraints
-- ✅ Performance indexes (basic, composite, full-text search)
-- ✅ Materialized views for analytics
-- ✅ Helper functions (search, health check, cleanup)
-- ✅ Monitoring views
-- ✅ Security permissions
-- ============================================

