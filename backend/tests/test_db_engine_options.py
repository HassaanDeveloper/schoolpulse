from backend.db.session import build_engine_options


def test_sqlite_gets_no_pool_sizing():
    options = build_engine_options("sqlite:///./example.db")
    assert "pool_size" not in options


def test_psycopg3_disables_prepared_statements():
    options = build_engine_options("postgresql+psycopg://u:p@host:6543/db")
    assert options["connect_args"]["prepare_threshold"] is None
    assert options["connect_args"]["connect_timeout"] > 0
    assert options["pool_size"] >= 1


def test_psycopg2_has_no_prepare_setting():
    options = build_engine_options("postgresql+psycopg2://u:p@host:5432/db")
    assert "prepare_threshold" not in options["connect_args"]