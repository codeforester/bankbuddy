alter table BB_DOCUMENT drop column storage_path;

alter table BB_IMPORT_ATTEMPT drop column source_path;

create table BB_STORAGE_ROOT (
    storage_root_id integer primary key,
    storage_root_code text not null unique,
    root_kind text not null check (
        root_kind in (
            'canonical',
            'view',
            'inbox',
            'failed',
            'duplicates',
            'review',
            'exports'
        )
    ),
    base_path_key text not null default 'app_root' check (
        base_path_key in ('app_root')
    ),
    relative_root text not null unique check (
        length(relative_root) > 0
        and substr(relative_root, 1, 1) <> '/'
        and instr(relative_root, '..') = 0
    ),
    permissions_mode text not null default 'managed-readonly' check (
        permissions_mode in ('managed-readonly', 'managed-writable')
    ),
    active integer not null default 1 check (active in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_STORAGE_ROOT (
    storage_root_code,
    root_kind,
    base_path_key,
    relative_root,
    permissions_mode,
    active
) values
    (
        'FINANCIAL_CANONICAL',
        'canonical',
        'app_root',
        'financial/canonical',
        'managed-readonly',
        1
    ),
    (
        'FINANCIAL_VIEWS',
        'view',
        'app_root',
        'financial/views',
        'managed-readonly',
        1
    ),
    (
        'FINANCIAL_INBOX',
        'inbox',
        'app_root',
        'financial/inbox',
        'managed-writable',
        1
    ),
    (
        'FINANCIAL_FAILED',
        'failed',
        'app_root',
        'financial/failed',
        'managed-readonly',
        1
    ),
    (
        'FINANCIAL_DUPLICATES',
        'duplicates',
        'app_root',
        'financial/duplicates',
        'managed-readonly',
        1
    ),
    (
        'FINANCIAL_REVIEW',
        'review',
        'app_root',
        'financial/review',
        'managed-writable',
        1
    ),
    (
        'FINANCIAL_EXPORTS',
        'exports',
        'app_root',
        'financial/exports',
        'managed-writable',
        1
    );

create table BB_DOCUMENT_OBJECT (
    document_object_id integer primary key,
    document_id integer not null references BB_DOCUMENT(document_id),
    storage_root_id integer not null references BB_STORAGE_ROOT(storage_root_id),
    object_key text not null check (
        length(object_key) > 0
        and substr(object_key, 1, 1) <> '/'
        and instr(object_key, '..') = 0
    ),
    object_role text not null check (
        object_role in (
            'canonical',
            'failed_original',
            'duplicate_original',
            'review_original',
            'extracted_text'
        )
    ),
    content_hash text not null,
    byte_size integer check (byte_size is null or byte_size >= 0),
    media_type text,
    original_file_name text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (storage_root_id, object_key)
);

create table BB_DOCUMENT_VIEW (
    document_view_id integer primary key,
    document_id integer not null references BB_DOCUMENT(document_id),
    document_object_id integer not null
        references BB_DOCUMENT_OBJECT(document_object_id),
    storage_root_id integer not null references BB_STORAGE_ROOT(storage_root_id),
    view_name text not null,
    view_key text not null check (
        length(view_key) > 0
        and substr(view_key, 1, 1) <> '/'
        and instr(view_key, '..') = 0
    ),
    materialization_kind text not null default 'copy' check (
        materialization_kind in ('copy')
    ),
    expected_hash text,
    byte_size integer check (byte_size is null or byte_size >= 0),
    status text not null default 'current' check (
        status in ('current', 'missing', 'modified', 'stale')
    ),
    last_materialized_at text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (storage_root_id, view_key)
);

alter table BB_IMPORT_ATTEMPT
add column document_object_id integer references BB_DOCUMENT_OBJECT(document_object_id);

create index idx_BB_STORAGE_ROOT_kind_active
on BB_STORAGE_ROOT(root_kind, active);

create index idx_BB_DOCUMENT_OBJECT_document_role
on BB_DOCUMENT_OBJECT(document_id, object_role);

create index idx_BB_DOCUMENT_OBJECT_hash
on BB_DOCUMENT_OBJECT(content_hash);

create index idx_BB_DOCUMENT_VIEW_document
on BB_DOCUMENT_VIEW(document_id);

create index idx_BB_DOCUMENT_VIEW_object
on BB_DOCUMENT_VIEW(document_object_id);

create index idx_BB_DOCUMENT_VIEW_status
on BB_DOCUMENT_VIEW(status);

create index idx_BB_IMPORT_ATTEMPT_document_object
on BB_IMPORT_ATTEMPT(document_object_id);
