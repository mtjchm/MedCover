-- Create the test database alongside the dev database.
-- This script runs only on first container creation via /docker-entrypoint-initdb.d/
-- The dev DB is already created by POSTGRES_DB env var.
CREATE DATABASE medcover_test OWNER medcover;
