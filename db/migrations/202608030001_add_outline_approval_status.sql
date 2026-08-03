-- Migration: Add outline_pending_approval to job_status enum
-- This status is used to pause the pipeline after outlining,
-- requiring explicit user approval before drafting proceeds.

ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'outline_pending_approval' AFTER 'outlining';
