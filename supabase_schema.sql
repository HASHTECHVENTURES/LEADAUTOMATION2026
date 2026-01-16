-- Supabase Database Schema for Business Outreach Automation
-- Run this SQL in your Supabase SQL Editor to create the required tables

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
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_level1_project_name ON level1_companies(project_name);
CREATE INDEX IF NOT EXISTS idx_level1_selected ON level1_companies(selected_for_level2);
CREATE INDEX IF NOT EXISTS idx_level1_search_date ON level1_companies(search_date DESC);
CREATE INDEX IF NOT EXISTS idx_level1_place_id ON level1_companies(place_id);

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
    title TEXT,  -- Original job title from Apollo.io (e.g., "CEO", "HR Manager", "Software Engineer")
    contact_type TEXT,  -- Categorized type: "Founder/Owner", "HR", "Employee"
    phone_number TEXT,
    linkedin_url TEXT,
    email TEXT,
    pin_code TEXT,
    industry TEXT,
    search_date TIMESTAMP,
    source TEXT,  -- "apollo" or "web_scraping"
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_level2_project_name ON level2_contacts(project_name);
CREATE INDEX IF NOT EXISTS idx_level2_batch_name ON level2_contacts(batch_name);
CREATE INDEX IF NOT EXISTS idx_level2_company_name ON level2_contacts(company_name);
CREATE INDEX IF NOT EXISTS idx_level2_contact_type ON level2_contacts(contact_type);

-- Enable Row Level Security (RLS) - Optional, for security
-- ALTER TABLE level1_companies ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE level2_contacts ENABLE ROW LEVEL SECURITY;

-- Create a function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to auto-update updated_at (drop if exists first)
DROP TRIGGER IF EXISTS update_level1_companies_updated_at ON level1_companies;
CREATE TRIGGER update_level1_companies_updated_at 
    BEFORE UPDATE ON level1_companies 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Optional (Level 2): Company metrics (run safely even if columns already exist)
ALTER TABLE IF EXISTS level1_companies ADD COLUMN IF NOT EXISTS total_employees TEXT;
ALTER TABLE IF EXISTS level1_companies ADD COLUMN IF NOT EXISTS active_members INTEGER;
ALTER TABLE IF EXISTS level1_companies ADD COLUMN IF NOT EXISTS active_members_with_email INTEGER;

-- Migration: Add batch_name to existing level2_contacts table
ALTER TABLE IF EXISTS level2_contacts ADD COLUMN IF NOT EXISTS batch_name TEXT;
-- Set default batch_name for existing rows (if any)
UPDATE level2_contacts SET batch_name = 'Batch_' || project_name WHERE batch_name IS NULL;
-- Now make batch_name NOT NULL (after setting defaults)
-- ALTER TABLE level2_contacts ALTER COLUMN batch_name SET NOT NULL; -- Uncomment after migration

-- Migration: Add company_total_employees to existing level2_contacts table
ALTER TABLE IF EXISTS level2_contacts ADD COLUMN IF NOT EXISTS company_total_employees TEXT;

-- Migration: Add title column to store original job title from Apollo.io
ALTER TABLE IF EXISTS level2_contacts ADD COLUMN IF NOT EXISTS title TEXT;

