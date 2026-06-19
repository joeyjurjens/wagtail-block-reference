import os
import socket
import subprocess
import sys
import time

import pytest

SETTINGS = "tests.e2e.settings"
HOST = "127.0.0.1"
PORT = 9876
BASE_URL = f"http://{HOST}:{PORT}"


def _wait_for_server(timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Django server at {BASE_URL} did not start within {timeout}s")


@pytest.fixture(scope="session")
def django_server(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("e2e") / "e2e.sqlite3")
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": SETTINGS, "E2E_DB_PATH": db_path}
    python = sys.executable

    subprocess.run(
        [python, "-m", "django", "migrate", "--run-syncdb", "--verbosity=0"],
        env=env,
        check=True,
    )
    subprocess.run(
        [
            python,
            "-m",
            "django",
            "shell",
            "-c",
            "from django.contrib.auth import get_user_model; U = get_user_model();"
            "U.objects.filter(username='admin').exists() or "
            "U.objects.create_superuser('admin', 'admin@example.com', 'password')",
        ],
        env=env,
        check=True,
    )

    proc = subprocess.Popen(
        [
            python,
            "-m",
            "django",
            "runserver",
            f"{HOST}:{PORT}",
            "--noreload",
            "--verbosity=0",
        ],
        env=env,
    )
    try:
        _wait_for_server()
        yield BASE_URL
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(scope="session")
def base_url(django_server):
    return django_server


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1280, "height": 800}}


@pytest.fixture(scope="session")
def logged_in_context(browser, django_server):
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{django_server}/admin/login/")
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "password")
    page.click('[type="submit"]')
    page.wait_for_url(f"{django_server}/admin/")
    page.close()
    yield context
    context.close()


@pytest.fixture()
def admin_page(logged_in_context, django_server):
    page = logged_in_context.new_page()
    yield page, django_server
    page.close()
