alter table transactions add column value_date text;

alter table accounts add column latest_balance_minor_units integer;
alter table accounts add column latest_balance_currency text check (
    latest_balance_currency is null
    or latest_balance_currency in ('USD', 'INR')
);
alter table accounts add column latest_balance_as_of_date text;
alter table accounts add column latest_balance_source_file_id integer references import_files(file_id);
