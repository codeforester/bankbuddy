create table banks (
    bank_id integer primary key,
    bank_name text not null unique,
    country text not null,
    default_currency text not null check (default_currency in ('USD', 'INR')),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table accounts (
    account_id integer primary key,
    bank_id integer not null references banks(bank_id),
    account_number text not null,
    account_type text not null check (
        account_type in ('checking', 'savings', 'cd', 'credit_card', 'investment')
    ),
    currency text not null check (currency in ('USD', 'INR')),
    statement_account_ref text,
    display_name text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (bank_id, account_number)
);

create table categories (
    category_id integer primary key,
    category_name text not null unique,
    category_kind text not null check (
        category_kind in ('income', 'expense', 'special')
    ),
    is_system integer not null check (is_system in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into categories (category_name, category_kind, is_system) values
    ('Salary', 'income', 1),
    ('Interest', 'income', 1),
    ('Dividends', 'income', 1),
    ('Groceries', 'expense', 1),
    ('Dining', 'expense', 1),
    ('Utilities', 'expense', 1),
    ('Travel', 'expense', 1),
    ('Healthcare', 'expense', 1),
    ('Shopping', 'expense', 1),
    ('Entertainment', 'expense', 1),
    ('Education', 'expense', 1),
    ('Insurance', 'expense', 1),
    ('Rent / Mortgage', 'expense', 1),
    ('Transfer', 'special', 1),
    ('Uncategorized', 'special', 1);

create table import_files (
    file_id integer primary key,
    file_name text not null,
    file_hash text not null unique,
    bank_id integer references banks(bank_id),
    first_seen_at text not null default current_timestamp,
    last_success_at text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table import_attempts (
    attempt_id integer primary key,
    file_id integer not null references import_files(file_id),
    bank_id integer references banks(bank_id),
    import_status text not null check (
        import_status in ('success', 'failed', 'partial')
    ),
    started_at text not null default current_timestamp,
    finished_at text,
    rows_parsed integer not null default 0 check (rows_parsed >= 0),
    rows_imported integer not null default 0 check (rows_imported >= 0),
    rows_skipped_duplicate integer not null default 0 check (rows_skipped_duplicate >= 0),
    transfer_candidates integer not null default 0 check (transfer_candidates >= 0),
    error_message text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table transactions (
    transaction_id integer primary key,
    account_id integer not null references accounts(account_id),
    category_id integer not null references categories(category_id),
    file_id integer not null references import_files(file_id),
    transaction_date text not null,
    amount_minor_units integer not null,
    currency text not null check (currency in ('USD', 'INR')),
    description text not null,
    normalized_description text not null,
    check_number text,
    source_row_key text,
    transaction_hash text not null,
    transfer_pair_id text,
    transfer_status text not null check (
        transfer_status in ('none', 'candidate', 'confirmed')
    ),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (account_id, transaction_hash)
);

create table category_rules (
    rule_id integer primary key,
    pattern text not null,
    category_id integer not null references categories(category_id),
    priority integer not null,
    match_type text not null check (match_type in ('contains', 'regex')),
    is_user_defined integer not null check (is_user_defined in (0, 1)),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table budgets (
    budget_id integer primary key,
    category_id integer not null references categories(category_id),
    currency text not null check (currency in ('USD', 'INR')),
    budget_type text not null check (budget_type in ('monthly', 'annual')),
    min_amount_minor_units integer,
    max_amount_minor_units integer,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique (category_id, currency),
    check (
        min_amount_minor_units is null
        or max_amount_minor_units is null
        or min_amount_minor_units <= max_amount_minor_units
    )
);
