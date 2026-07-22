import pytest
from django.core.exceptions import ImproperlyConfigured

from poems.runtime_config import REQUIRED_SPACES_ENV, validate_production_config


def production_environment():
    return {name: "configured" for name in REQUIRED_SPACES_ENV}


def test_production_requires_explicit_postgresql():
    with pytest.raises(ImproperlyConfigured):
        validate_production_config(False, "", production_environment())
    with pytest.raises(ImproperlyConfigured):
        validate_production_config(
            False,
            "sqlite:////tmp/poetry.sqlite3",
            production_environment(),
        )


@pytest.mark.parametrize("missing_name", REQUIRED_SPACES_ENV)
def test_production_requires_every_spaces_setting(missing_name):
    environment = production_environment()
    environment[missing_name] = ""
    with pytest.raises(ImproperlyConfigured, match=missing_name):
        validate_production_config(
            False,
            "postgresql://poetry:secret@database.example/poetry",
            environment,
        )


def test_production_accepts_postgresql_and_complete_spaces_settings():
    validate_production_config(
        False,
        "postgresql://poetry:secret@database.example/poetry",
        production_environment(),
    )
