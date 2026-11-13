-- Run once per database cluster as a superuser (or in Supabase's SQL editor as postgres).
-- Replace the passwords with values from your secrets manager; never commit real ones.
--
-- eco_owner : owns the schema and runs Alembic migrations.
-- eco_app   : the role the API connects as. Not the owner, no BYPASSRLS, so row-level security applies.

CREATE ROLE eco_owner LOGIN PASSWORD :'owner_password' NOSUPERUSER NOCREATEROLE;
CREATE ROLE eco_app   LOGIN PASSWORD :'app_password'   NOSUPERUSER NOCREATEROLE NOBYPASSRLS;

CREATE DATABASE eco OWNER eco_owner;
\connect eco
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO eco_owner;
GRANT CONNECT ON DATABASE eco TO eco_app;
-- pgvector (AI retrieval) must be created by a superuser; migration 0003 checks for it.
-- On Supabase, enable the "vector" extension in the dashboard instead.
CREATE EXTENSION IF NOT EXISTS vector;
