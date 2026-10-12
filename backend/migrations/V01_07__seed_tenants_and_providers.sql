-- BTH
INSERT INTO tenants (id, folio_tenant_key, name)
VALUES (
        '4d04e6d1-27d1-439e-8aa6-8992dbd7c623',
        'bth',
        'Blekinge Tekniska Högskola'
)
ON CONFLICT (folio_tenant_key) DO UPDATE
SET name = EXCLUDED.name;

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
        'bth-libris-1',
        'Libris (Blekinge Tekniska Högskola)',
        'Bthg',
        'https://iller.libris.kb.se/librisfjarrlan/api',
        'env://BTH_LIBRIS_PASSWORD',
        true,
        true,
        'libris-v1'
)
ON CONFLICT (tenant_id, adapter_key, account_key) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    local_library_code = EXCLUDED.local_library_code,
    base_url = EXCLUDED.base_url,
    secret_ref = EXCLUDED.secret_ref,
    enabled = EXCLUDED.enabled,
    writes_enabled = EXCLUDED.writes_enabled,
    mapping_version = EXCLUDED.mapping_version;

-- HH
INSERT INTO tenants (id, folio_tenant_key, name)
VALUES (
        'cf964861-af0a-434a-a7ab-8ecd774e37de',
        'hh',
        'Halmstad University'
)
ON CONFLICT (folio_tenant_key) DO UPDATE
SET name = EXCLUDED.name;

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
        'cb615c1b-834b-4f4d-8d78-e7d2f54885d6',
        'cf964861-af0a-434a-a7ab-8ecd774e37de',
        'libris',
        'hh-libris-1',
        'Libris (Halmstad University)',
        'Hal',
        'https://iller.libris.kb.se/librisfjarrlan/api',
        'env://HH_LIBRIS_PASSWORD',
        true,
        true,
        'libris-v1'
)
ON CONFLICT (tenant_id, adapter_key, account_key) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    local_library_code = EXCLUDED.local_library_code,
    base_url = EXCLUDED.base_url,
    secret_ref = EXCLUDED.secret_ref,
    enabled = EXCLUDED.enabled,
    writes_enabled = EXCLUDED.writes_enabled,
    mapping_version = EXCLUDED.mapping_version;

-- MDU
INSERT INTO tenants (id, folio_tenant_key, name)
VALUES (
        'b18e767f-fe17-408d-acc1-c19ff0a5e5cd',
        'mdu',
        'Mälardalens Universitet'
)
ON CONFLICT (folio_tenant_key) DO UPDATE
SET name = EXCLUDED.name;

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
        'e8a8aa11-0353-424b-8600-c8574830b0bf',
        'b18e767f-fe17-408d-acc1-c19ff0a5e5cd',
        'libris',
        'mdu-libris-1',
        'Libris (Mälardalens Universitet)',
        'Mde',
        'https://iller.libris.kb.se/librisfjarrlan/api',
        'env://MDU_LIBRIS_PASSWORD',
        true,
        true,
        'libris-v1'
)
ON CONFLICT (tenant_id, adapter_key, account_key) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    local_library_code = EXCLUDED.local_library_code,
    base_url = EXCLUDED.base_url,
    secret_ref = EXCLUDED.secret_ref,
    enabled = EXCLUDED.enabled,
    writes_enabled = EXCLUDED.writes_enabled,
    mapping_version = EXCLUDED.mapping_version;
