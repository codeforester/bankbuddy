alter table import_attempts rename to import_attempts_old;

create table import_attempts (
    attempt_id integer primary key,
    file_id integer not null references import_files(file_id),
    bank_id integer references banks(bank_id),
    account_id integer references accounts(account_id),
    import_status text not null check (
        import_status in ('success', 'failed', 'partial', 'duplicate')
    ),
    started_at text not null default current_timestamp,
    finished_at text,
    rows_parsed integer not null default 0 check (rows_parsed >= 0),
    rows_imported integer not null default 0 check (rows_imported >= 0),
    rows_skipped_duplicate integer not null default 0 check (rows_skipped_duplicate >= 0),
    transfer_candidates integer not null default 0 check (transfer_candidates >= 0),
    error_message text,
    duplicate_path text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

insert into import_attempts (
    attempt_id,
    file_id,
    bank_id,
    account_id,
    import_status,
    started_at,
    finished_at,
    rows_parsed,
    rows_imported,
    rows_skipped_duplicate,
    transfer_candidates,
    error_message,
    created_at,
    updated_at
)
select
    attempt_id,
    file_id,
    bank_id,
    account_id,
    import_status,
    started_at,
    finished_at,
    rows_parsed,
    rows_imported,
    rows_skipped_duplicate,
    transfer_candidates,
    error_message,
    created_at,
    updated_at
from import_attempts_old;

drop table import_attempts_old;
