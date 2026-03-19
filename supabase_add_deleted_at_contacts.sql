-- Add soft-delete support for Level 2 contacts.
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor) if you get errors about deleted_at.

ALTER TABLE level2_contacts
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN level2_contacts.deleted_at IS 'Set when contact is soft-deleted; null = visible in list.';
