-- Supabase Database Schema for Business Outreach Automation
-- Run this SQL in your Supabase SQL Editor to create the required tables
-- This version handles existing objects gracefully

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
    company_name TEXT NOT NULL,
    company_address TEXT,
    company_website TEXT,
    company_phone TEXT,
    contact_name TEXT,
    contact_type TEXT,  -- e.g., "Founder", "HR", "Owner", "Employee"
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

-- Create trigger to auto-update updated_at (drop if exists first to avoid errors)
DROP TRIGGER IF EXISTS update_level1_companies_updated_at ON level1_companies;
CREATE TRIGGER update_level1_companies_updated_at 
    BEFORE UPDATE ON level1_companies 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();



