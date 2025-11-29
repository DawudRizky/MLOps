-- PostgreSQL Initialization Script for MLflow
-- Creates necessary extensions and tables

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;

-- Create schema for future use (e.g., API database)
CREATE SCHEMA IF NOT EXISTS api;
GRANT ALL PRIVILEGES ON SCHEMA api TO mlflow;

-- Set search path
ALTER DATABASE mlflow SET search_path TO public, api;

-- Done
SELECT 'PostgreSQL initialized successfully for MLflow' AS status;
