alter table import_files add column original_file_name text;
alter table import_files add column canonical_file_name text;
alter table import_files add column source_path text;
alter table import_files add column processed_path text;
alter table import_files add column statement_start_date text;
alter table import_files add column statement_end_date text;
alter table import_files add column account_ref text;
alter table import_files add column source_format text;

update import_files
set original_file_name = file_name
where original_file_name is null;
