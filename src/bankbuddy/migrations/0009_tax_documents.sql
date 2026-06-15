create table tax_documents (
    tax_document_id integer primary key,
    file_hash text not null unique,
    original_file_name text not null,
    canonical_file_name text not null,
    source_path text,
    processed_path text not null,
    document_type text not null,
    jurisdiction text not null,
    tax_year integer not null,
    source_entity text,
    person_label text,
    account_ref text,
    imported_at text not null default current_timestamp,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);
