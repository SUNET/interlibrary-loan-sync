-- ============================================================================
-- 3. Seed data
-- ============================================================================
INSERT INTO
    tenants (id, folio_tenant_key, name)
VALUES (
        '4d04e6d1-27d1-439e-8aa6-8992dbd7c623',
        'sft2',
        'Sunet Folio Test 2'
);

INSERT INTO providers (
    id,
    tenant_id,
    adapter_key,
    account_key,
    display_name,
    local_library_code,
    base_url,
    secret_ref,
    enabled,
    writes_enabled,
    mapping_version
)
VALUES (
        '8959a4c6-3dbd-4f67-9d95-6aa3ca6414b2',
        '4d04e6d1-27d1-439e-8aa6-8992dbd7c623',
        'libris',
        'test-main',
        'Libris (Sunet Folio Test 2)',
        'Sft2',
        'https://iller.libris.kb.se/librisfjarrlan/api',
        'env://ILL_LIBRIS_API_KEY',
        true,
        true,
        'libris-v1'
);
