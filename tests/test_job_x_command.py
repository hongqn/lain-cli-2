from subprocess import CompletedProcess

import lain_cli.lain as lain_module
import pytest
from click.testing import CliRunner

from lain_cli.lain import lain

APPNAME = "dummy"


def run_cli(monkeypatch, args, obj=None, returncode=0):
    monkeypatch.setattr(lain_module, "ensure_helm_initiated", lambda: None)
    monkeypatch.setattr(lain_module, "version_challenge", lambda: None)
    runner = CliRunner()
    res = runner.invoke(lain, args=args, obj=obj or {})
    assert res.exit_code == returncode, res.output
    return res


def test_lain_job_x_uses_latest_running_job_pod(monkeypatch):
    picked = []
    kubectl_calls = []

    def fake_pick_job_pod(appname, job_name=None):
        picked.append((appname, job_name))
        return "dummy-job-pod"

    def fake_kubectl(*args, **kwargs):
        kubectl_calls.append((args, kwargs))
        return CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(lain_module, "pick_job_pod", fake_pick_job_pod)
    monkeypatch.setattr(lain_module, "kubectl", fake_kubectl)

    run_cli(monkeypatch, args=["job", "x"], obj={"appname": APPNAME})

    assert picked == [(APPNAME, None)]
    assert kubectl_calls == [
        (
            ("exec", "-it", "dummy-job-pod", "--", "bash"),
            {"check": False, "timeout": None},
        )
    ]


def test_lain_job_x_accepts_job_name_before_command(monkeypatch):
    picked = []
    kubectl_calls = []
    job_name = "dummy-5562bd9d33e0c6ce"

    def fake_pick_job_pod(appname, job_name=None):
        picked.append((appname, job_name))
        return "dummy-job-pod"

    def fake_kubectl(*args, **kwargs):
        kubectl_calls.append((args, kwargs))
        return CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(lain_module, "pick_job_pod", fake_pick_job_pod)
    monkeypatch.setattr(lain_module, "kubectl", fake_kubectl)

    run_cli(
        monkeypatch,
        args=["job", "x", job_name, "--", "sh", "-c", "env"],
        obj={"appname": APPNAME},
    )

    assert picked == [(APPNAME, job_name)]
    assert kubectl_calls == [
        (
            ("exec", "-it", "dummy-job-pod", "--", "sh", "-c", "env"),
            {"check": False, "timeout": None},
        )
    ]


def test_lain_job_x_interprets_unknown_job_name_as_command(monkeypatch):
    picked = []
    kubectl_calls = []
    warnings = []

    def fake_pick_job_pod(appname, job_name=None):
        picked.append((appname, job_name))
        if job_name == "python3":
            return None
        return "dummy-job-pod"

    def fake_kubectl(*args, **kwargs):
        kubectl_calls.append((args, kwargs))
        return CompletedProcess(args=args, returncode=0)

    def fake_warn(message, *args, **kwargs):
        warnings.append(message)

    monkeypatch.setattr(lain_module, "pick_job_pod", fake_pick_job_pod)
    monkeypatch.setattr(lain_module, "kubectl", fake_kubectl)
    monkeypatch.setattr(lain_module, "warn", fake_warn)

    run_cli(
        monkeypatch,
        args=["job", "x", "python3", "manage.py", "showmigrations"],
        obj={"appname": APPNAME},
    )

    assert picked == [(APPNAME, "python3"), (APPNAME, None)]
    assert warnings == [
        "python3 is not a running job name, thus interpreting the command as `['python3', 'manage.py', 'showmigrations']`"
    ]
    assert kubectl_calls == [
        (
            (
                "exec",
                "-it",
                "dummy-job-pod",
                "--",
                "python3",
                "manage.py",
                "showmigrations",
            ),
            {"check": False, "timeout": None},
        )
    ]


def test_lain_job_x_rejects_job_creation_options(monkeypatch):
    res = run_cli(
        monkeypatch,
        args=["job", "--force", "x"],
        obj={"appname": APPNAME},
        returncode=2,
    )

    assert "`lain job x` does not accept job creation options: --force" in res.output


def test_lain_job_still_uses_existing_create_flow(monkeypatch):
    cache = {}

    def fake_run_job_command(**kwargs):
        cache.update(kwargs)

    def fail_if_called(**kwargs):
        pytest.fail(f"did not expect enter_job_container to be called: {kwargs}")

    monkeypatch.setattr(lain_module, "run_job_command", fake_run_job_command)
    monkeypatch.setattr(lain_module, "enter_job_container", fail_if_called)

    run_cli(monkeypatch, args=["job", "env"], obj={"appname": APPNAME})

    assert cache["command"] == ("env",)
