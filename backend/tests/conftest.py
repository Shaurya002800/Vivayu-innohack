import pytest

from app.state import application_state


@pytest.fixture(autouse=True)
def reset_shared_application_state():
    application_state.reset()
    yield
    application_state.reset()
