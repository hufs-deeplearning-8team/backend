-- Add API key column to existing User table
ALTER TABLE user ADD COLUMN api_key VARCHAR(255) UNIQUE;

-- Generate API keys for existing users
-- This script should be run after the ALTER statement
UPDATE user 
SET api_key = CONCAT('ak_', SUBSTRING(MD5(CONCAT(id, email, UNIX_TIMESTAMP())), 1, 32))
WHERE api_key IS NULL;

-- Add USE_OPENAPI column to existing Image table
ALTER TABLE image ADD COLUMN use_openapi BOOLEAN NOT NULL DEFAULT FALSE;

-- Set all existing images to FALSE (not created via OPENAPI)
UPDATE image 
SET use_openapi = FALSE 
WHERE use_openapi IS NULL;