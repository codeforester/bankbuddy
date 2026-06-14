update banks
set
    country = 'US',
    updated_at = current_timestamp
where lower(replace(replace(trim(country), '.', ''), ' ', '')) in (
    'us',
    'usa',
    'unitedstates',
    'unitedstatesofamerica'
);

update banks
set
    country = 'IN',
    updated_at = current_timestamp
where lower(replace(replace(trim(country), '.', ''), ' ', '')) in (
    'in',
    'india'
);
