-- Separate database for the pytest suite, so tests never touch demo data.
CREATE DATABASE finance_test OWNER finance;
