-- ============================================================================
-- 3. Seed data
-- ============================================================================
INSERT INTO
    tenants (id, folio_tenant_key, name)
VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'hal',
        'Halmstad'
    );

INSERT INTO
    providers (
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
VALUES
    (
        '22222222-2222-4222-8222-222222222222',
        '11111111-1111-4111-8111-111111111111',
        'libris',
        -- Part 3 uses the simulator.
        'hal-main',
        'Libris (Halmstad)',
        'Hal',
        'https://iller.libris.kb.se/librisfjarrlan/api',
        'env://ILL_LIBRIS_API_KEY',
        true,
        false,
        -- Writes stay disabled until the provider-write implementation is enabled.
        'libris-v1'
    );
INSERT INTO
    providers (
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
VALUES
    (
        '22222222-2222-4222-8222-222222222221',
        '11111111-1111-4111-8111-111111111111',
        'fake',
        -- Part 3 uses the simulator.
        'hal-main',
        'Fake-Libris (Halmstad)',
        'Hal',
        'http://localhost:9000/librisfjarrlan/api',
        'env://ILL_FAKE_API_KEY',
        true,
        false,
        -- Writes stay disabled until the provider-write implementation is enabled.
        'fake-v1'
    );