create table account_statement_refs (
    account_statement_ref_id integer primary key,
    account_id integer not null references accounts(account_id) on delete cascade,
    source_format text not null default '*',
    ref_type text not null check (
        ref_type in (
            'full_account_number',
            'last4',
            'masked_account',
            'product'
        )
    ),
    ref_value text not null,
    normalized_ref_value text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (account_id, source_format, ref_type, normalized_ref_value)
);

create index account_statement_refs_lookup_idx
    on account_statement_refs (
        source_format,
        ref_type,
        normalized_ref_value,
        account_id
    );
