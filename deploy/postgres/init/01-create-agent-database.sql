-- Creates the extra logical database used by agent-service.
-- The default POSTGRES_DB database is insurance_biz.
SELECT 'CREATE DATABASE insurance_agent OWNER insurance'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'insurance_agent'
)\gexec

GRANT ALL PRIVILEGES ON DATABASE insurance_agent TO insurance;
