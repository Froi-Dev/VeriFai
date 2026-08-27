-- Run this as the database owner after replacing the role names and password.
-- The API role receives DML only; it cannot alter or drop application tables.
CREATE ROLE verifai_app LOGIN PASSWORD 'REPLACE_WITH_SECRET_FROM_YOUR_SECRET_MANAGER';
REVOKE ALL ON DATABASE "verifaiDb" FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE "verifaiDb" TO verifai_app;
GRANT USAGE ON SCHEMA public TO verifai_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO verifai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO verifai_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO verifai_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO verifai_app;
