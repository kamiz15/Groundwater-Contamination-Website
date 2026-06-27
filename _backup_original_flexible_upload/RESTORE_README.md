# Backup — original files before the flexible-upload (catalog-driven) changes

Verbatim copies of every file the flexible-upload plan modifies, taken BEFORE
any changes were made. Use them to roll back if the new upload pipeline does
not work out.

## Restore one file (from project root)
    cp _backup_original_flexible_upload/site_routes.py site_routes.py

## Restore everything
    cp -r _backup_original_flexible_upload/* .
    # delete RESTORE_README.md from root afterward if unwanted

## Files backed up
symbol_registry.py, data_queries.py, db_setup.sql, site_routes.py,
analytical_routes.py, numerical_routes.py, model_site_validation.py,
numerical_input_validation.py, empirical_routes.py,
templates/site_database.html, tests/test_csv_import.py,
tests/test_numerical_autofill.py, tests/test_multiple_wrappers.py,
tests/test_model_site_filtering.py, tests/test_site_validation.py

Note: these files are also recoverable via git (git checkout -- <file>).
