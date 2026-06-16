create table BB_CURRENCY (
    currency_code text primary key,
    display_name text not null,
    minor_unit_exponent integer not null check (minor_unit_exponent >= 0),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_CURRENCY (
    currency_code,
    display_name,
    minor_unit_exponent
) values
    ('INR', 'Indian Rupee', 2),
    ('USD', 'US Dollar', 2);

create table BB_JURISDICTION (
    jurisdiction_code text primary key,
    display_name text not null,
    country_code text not null,
    region_code text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_JURISDICTION (
    jurisdiction_code,
    display_name,
    country_code,
    region_code
) values
    ('IN', 'India', 'IN', null),
    ('US', 'United States', 'US', null);

create table BB_DOCUMENT (
    document_id integer primary key,
    file_hash text not null unique,
    original_file_name text not null,
    canonical_file_name text,
    storage_path text,
    source_uri text,
    document_type text,
    jurisdiction_code text references BB_JURISDICTION(jurisdiction_code),
    tax_year integer,
    document_status text not null default 'active' check (
        document_status in ('active', 'duplicate', 'failed', 'archived')
    ),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_IMPORT_ATTEMPT (
    import_attempt_id integer primary key,
    document_id integer references BB_DOCUMENT(document_id),
    source_path text not null,
    import_status text not null check (
        import_status in (
            'planned',
            'success',
            'failed',
            'duplicate',
            'review_needed'
        )
    ),
    started_at text not null default current_timestamp,
    finished_at text,
    error_message text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_PARSER (
    parser_id integer primary key,
    parser_name text not null unique,
    file_type text not null,
    document_family text not null,
    default_document_type text,
    active integer not null default 1 check (active in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_PARSER (
    parser_name,
    file_type,
    document_family,
    default_document_type,
    active
) values
    ('apple_card_pdf', 'pdf', 'bank', 'credit_card_statement', 1),
    ('boa_csv', 'csv', 'bank', 'bank_statement', 1),
    ('boa_pdf', 'pdf', 'bank', 'bank_statement', 1),
    ('hdfc_xls', 'xls', 'bank', 'bank_statement', 1),
    ('icici_xls', 'xls', 'bank', 'bank_statement', 1),
    ('tax_pdf', 'pdf', 'tax', 'tax_document', 1);

create table BB_EXTRACTION_RUN (
    extraction_run_id integer primary key,
    document_id integer not null references BB_DOCUMENT(document_id),
    parser_id integer not null references BB_PARSER(parser_id),
    extraction_status text not null check (
        extraction_status in ('success', 'failed', 'partial')
    ),
    raw_text_stored integer not null default 0 check (raw_text_stored in (0, 1)),
    started_at text not null default current_timestamp,
    finished_at text,
    error_message text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_ENTITY (
    entity_id integer primary key,
    entity_type text not null,
    display_name text,
    status text not null default 'active' check (
        status in ('active', 'inactive', 'candidate', 'merged', 'deleted')
    ),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_ENTITY_ATTRIBUTE_TYPE (
    entity_attribute_type_id integer primary key,
    attribute_code text not null unique,
    display_name text not null,
    value_kind text not null check (
        value_kind in ('text', 'integer', 'decimal', 'date', 'boolean')
    ),
    sensitivity text not null check (
        sensitivity in ('public', 'private', 'sensitive', 'secret')
    ),
    is_system integer not null default 1 check (is_system in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_ENTITY_ATTRIBUTE_TYPE (
    attribute_code,
    display_name,
    value_kind,
    sensitivity,
    is_system
) values
    ('FULL_NAME', 'Full name', 'text', 'sensitive', 1),
    ('DISPLAY_NAME', 'Display name', 'text', 'private', 1),
    ('ACCOUNT_NUMBER', 'Account number', 'text', 'secret', 1),
    ('ACCOUNT_LAST4', 'Account last four digits', 'text', 'sensitive', 1),
    ('STATEMENT_ACCOUNT_REF', 'Statement account reference', 'text', 'sensitive', 1),
    ('ADDRESS_LINE_1', 'Address line 1', 'text', 'sensitive', 1),
    ('ADDRESS_LINE_2', 'Address line 2', 'text', 'sensitive', 1),
    ('ADDRESS_LINE_3', 'Address line 3', 'text', 'sensitive', 1),
    ('ADDRESS_CITY', 'Address city', 'text', 'sensitive', 1),
    ('ADDRESS_STATE', 'Address state or province', 'text', 'sensitive', 1),
    ('ADDRESS_POSTAL_CODE', 'Address postal code', 'text', 'sensitive', 1),
    ('ADDRESS_COUNTRY', 'Address country', 'text', 'sensitive', 1),
    ('JURISDICTION', 'Jurisdiction', 'text', 'private', 1),
    ('CURRENCY', 'Currency', 'text', 'private', 1);

create table BB_ENTITY_ATTRIBUTE (
    entity_attribute_id integer primary key,
    entity_id integer not null references BB_ENTITY(entity_id),
    entity_attribute_type_id integer not null
        references BB_ENTITY_ATTRIBUTE_TYPE(entity_attribute_type_id),
    value_text text,
    value_integer integer,
    value_decimal text,
    value_date text,
    value_boolean integer check (value_boolean in (0, 1)),
    source_document_id integer references BB_DOCUMENT(document_id),
    valid_from text,
    valid_to text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_RELATIONSHIP_TYPE (
    relationship_type_id integer primary key,
    relationship_type_code text not null unique,
    display_name text not null,
    is_system integer not null default 1 check (is_system in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_RELATIONSHIP_TYPE (
    relationship_type_code,
    display_name,
    is_system
) values
    ('OWNS', 'Owns', 1),
    ('MEMBER_OF_HOUSEHOLD', 'Member of household', 1),
    ('HELD_AT_INSTITUTION', 'Held at institution', 1),
    ('ISSUED_BY', 'Issued by', 1),
    ('EVIDENCES', 'Evidences', 1);

create table BB_RELATIONSHIP (
    relationship_id integer primary key,
    relationship_type_id integer not null
        references BB_RELATIONSHIP_TYPE(relationship_type_id),
    source_entity_id integer not null references BB_ENTITY(entity_id),
    target_entity_id integer not null references BB_ENTITY(entity_id),
    source_document_id integer references BB_DOCUMENT(document_id),
    valid_from text,
    valid_to text,
    confidence real not null default 1.0 check (
        confidence >= 0.0 and confidence <= 1.0
    ),
    review_status text not null default 'accepted' check (
        review_status in ('accepted', 'needs_review', 'rejected', 'superseded')
    ),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_OBSERVATION_TYPE (
    observation_type_id integer primary key,
    observation_type_code text not null unique,
    display_name text not null,
    value_kind text not null check (
        value_kind in ('text', 'integer', 'decimal', 'date', 'boolean')
    ),
    is_system integer not null default 1 check (is_system in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into BB_OBSERVATION_TYPE (
    observation_type_code,
    display_name,
    value_kind,
    is_system
) values
    ('DOCUMENT_TYPE', 'Document type', 'text', 1),
    ('STATEMENT_PERIOD', 'Statement period', 'text', 1),
    ('ACCOUNT_BALANCE', 'Account balance', 'decimal', 1),
    ('TRANSACTION', 'Transaction', 'text', 1),
    ('ENTITY_IDENTIFIER', 'Entity identifier', 'text', 1),
    ('TAX_YEAR', 'Tax year', 'integer', 1),
    ('JURISDICTION', 'Jurisdiction', 'text', 1);

create table BB_OBSERVATION (
    observation_id integer primary key,
    observation_type_id integer not null
        references BB_OBSERVATION_TYPE(observation_type_id),
    document_id integer references BB_DOCUMENT(document_id),
    subject_entity_id integer references BB_ENTITY(entity_id),
    value_text text,
    value_integer integer,
    value_decimal text,
    value_date text,
    value_boolean integer check (value_boolean in (0, 1)),
    confidence real not null default 1.0 check (
        confidence >= 0.0 and confidence <= 1.0
    ),
    review_status text not null default 'needs_review' check (
        review_status in ('accepted', 'needs_review', 'rejected', 'superseded')
    ),
    observed_at text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_OBSERVATION_EVIDENCE (
    observation_evidence_id integer primary key,
    observation_id integer not null references BB_OBSERVATION(observation_id),
    document_id integer not null references BB_DOCUMENT(document_id),
    extraction_run_id integer references BB_EXTRACTION_RUN(extraction_run_id),
    evidence_text text,
    page_number integer,
    location_text text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_PERSON (
    person_id integer primary key,
    entity_id integer not null unique references BB_ENTITY(entity_id),
    preferred_name text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_HOUSEHOLD (
    household_id integer primary key,
    entity_id integer not null unique references BB_ENTITY(entity_id),
    household_name text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table BB_HOUSEHOLD_MEMBER (
    household_member_id integer primary key,
    household_id integer not null references BB_HOUSEHOLD(household_id),
    person_id integer not null references BB_PERSON(person_id),
    relationship_label text,
    valid_from text,
    valid_to text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (household_id, person_id, valid_from)
);

create index idx_BB_DOCUMENT_file_hash
on BB_DOCUMENT(file_hash);

create index idx_BB_DOCUMENT_type_year
on BB_DOCUMENT(document_type, tax_year);

create index idx_BB_IMPORT_ATTEMPT_document_status
on BB_IMPORT_ATTEMPT(document_id, import_status);

create index idx_BB_PARSER_file_type
on BB_PARSER(file_type, active);

create index idx_BB_EXTRACTION_RUN_document_parser
on BB_EXTRACTION_RUN(document_id, parser_id);

create index idx_BB_ENTITY_type_status
on BB_ENTITY(entity_type, status);

create index idx_BB_ENTITY_ATTRIBUTE_entity_type
on BB_ENTITY_ATTRIBUTE(entity_id, entity_attribute_type_id);

create index idx_BB_ENTITY_ATTRIBUTE_source_document
on BB_ENTITY_ATTRIBUTE(source_document_id);

create index idx_BB_RELATIONSHIP_source_type
on BB_RELATIONSHIP(source_entity_id, relationship_type_id);

create index idx_BB_RELATIONSHIP_target_type
on BB_RELATIONSHIP(target_entity_id, relationship_type_id);

create index idx_BB_OBSERVATION_subject_type
on BB_OBSERVATION(subject_entity_id, observation_type_id);

create index idx_BB_OBSERVATION_document
on BB_OBSERVATION(document_id);

create index idx_BB_OBSERVATION_review_status
on BB_OBSERVATION(review_status);

create index idx_BB_OBSERVATION_EVIDENCE_observation
on BB_OBSERVATION_EVIDENCE(observation_id);

create index idx_BB_HOUSEHOLD_MEMBER_household
on BB_HOUSEHOLD_MEMBER(household_id);

create index idx_BB_HOUSEHOLD_MEMBER_person
on BB_HOUSEHOLD_MEMBER(person_id);
