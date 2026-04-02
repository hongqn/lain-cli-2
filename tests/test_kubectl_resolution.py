import os
from subprocess import CompletedProcess

import lain_cli.utils as utils


def completed_process(args, stdout=b"", stderr=b"", returncode=0):
    return CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def clear_caches():
    utils.asdf_which.cache_clear()
    utils.tell_kubectl_binary.cache_clear()
    utils.warn_if_kubectl_is_shadowed.cache_clear()
    utils.kubectl_version_challenge.cache_clear()


def setup_asdf(monkeypatch, asdf_path):
    monkeypatch.setattr(utils, "has_asdf", lambda: True)
    monkeypatch.setattr(
        utils,
        "asdf",
        lambda *args, **kwargs: completed_process(
            args, stdout=f"{asdf_path}\n".encode("utf-8")
        ),
    )
    monkeypatch.setattr(utils, "isfile", lambda path: path == asdf_path)


def test_tell_kubectl_binary_prefers_asdf(monkeypatch):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    assert utils.tell_kubectl_binary() == asdf_path


def test_tell_kubectl_binary_falls_back_to_path(monkeypatch):
    clear_caches()
    monkeypatch.setattr(utils, "has_asdf", lambda: False)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    assert utils.tell_kubectl_binary() == "/usr/local/bin/kubectl"


def test_warn_if_kubectl_is_shadowed_warns_once(monkeypatch, tmp_path):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warnings = []
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(utils.click, "get_app_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )

    utils.warn_if_kubectl_is_shadowed()
    utils.warn_if_kubectl_is_shadowed()

    assert len(warnings) == 1
    assert "/usr/local/bin/kubectl" in warnings[0]
    assert asdf_path in warnings[0]
    assert "asdf-managed kubectl" in warnings[0]


def test_warn_if_kubectl_is_shadowed_records_warning_timestamp(monkeypatch, tmp_path):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warnings = []
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(utils.click, "get_app_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )

    utils.warn_if_kubectl_is_shadowed()

    warning_file = tmp_path / utils.SHADOWED_KUBECTL_WARNING_FILE
    assert len(warnings) == 1
    assert warning_file.is_file()


def test_warn_if_kubectl_is_shadowed_is_snoozed_for_30_days(monkeypatch, tmp_path):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warning_file = tmp_path / utils.SHADOWED_KUBECTL_WARNING_FILE
    warnings = []
    now = 1000.0
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(utils.click, "get_app_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(utils, "time", lambda: now)
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )
    warning_file.parent.mkdir(parents=True, exist_ok=True)
    warning_file.write_text("")
    recent = now - utils.SHADOWED_KUBECTL_WARNING_SNOOZE_SECONDS + 1
    os.utime(warning_file, (recent, recent))

    utils.warn_if_kubectl_is_shadowed()

    assert warnings == []


def test_warn_if_kubectl_is_shadowed_warns_again_after_30_days(monkeypatch, tmp_path):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warning_file = tmp_path / utils.SHADOWED_KUBECTL_WARNING_FILE
    warnings = []
    now = float(utils.SHADOWED_KUBECTL_WARNING_SNOOZE_SECONDS + 100)
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(utils.click, "get_app_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(utils, "time", lambda: now)
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )
    warning_file.parent.mkdir(parents=True, exist_ok=True)
    warning_file.write_text("")
    old = now - utils.SHADOWED_KUBECTL_WARNING_SNOOZE_SECONDS - 1
    os.utime(warning_file, (old, old))

    utils.warn_if_kubectl_is_shadowed()

    assert len(warnings) == 1
    assert warning_file.stat().st_mtime == now


def test_warn_if_kubectl_is_shadowed_can_be_disabled_by_env(monkeypatch, tmp_path):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warnings = []
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(utils.click, "get_app_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )
    monkeypatch.setitem(utils.ENV, utils.SHADOWED_KUBECTL_WARNING_ENV, "true")

    utils.warn_if_kubectl_is_shadowed()

    warning_file = tmp_path / utils.SHADOWED_KUBECTL_WARNING_FILE
    assert warnings == []
    assert not warning_file.exists()


def test_warn_if_kubectl_is_shadowed_accepts_asdf_shim(monkeypatch):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    warnings = []
    clear_caches()
    setup_asdf(monkeypatch, asdf_path)
    monkeypatch.setattr(
        utils.shutil,
        "which",
        lambda name: f"/Users/test/.asdf/shims/{name}",
    )
    monkeypatch.setattr(
        utils, "warn", lambda message, **kwargs: warnings.append(message)
    )

    utils.warn_if_kubectl_is_shadowed()

    assert warnings == []


def test_kubectl_version_challenge_uses_resolved_binary(monkeypatch):
    calls = []
    clear_caches()
    monkeypatch.setattr(utils, "tell_kubectl_binary", lambda: "/tmp/asdf-kubectl")

    def fake_subprocess_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return completed_process(
            cmd,
            stdout=b"Client Version: v1.30.0\nServer Version: v1.30.0\n",
        )

    monkeypatch.setattr(utils, "subprocess_run", fake_subprocess_run)

    assert utils.kubectl_version_challenge() is True
    assert calls == [
        (
            ["/tmp/asdf-kubectl", "version"],
            {
                "capture_output": True,
                "env": utils.ENV,
                "silent": True,
                "check": True,
            },
        )
    ]


def test_kubectl_uses_resolved_binary(monkeypatch):
    calls = []
    checks = []
    warnings = []
    clear_caches()
    monkeypatch.setattr(utils, "tell_kubectl_binary", lambda: "/tmp/asdf-kubectl")
    monkeypatch.setattr(
        utils, "kubectl_version_challenge", lambda check=True: checks.append(check)
    )
    monkeypatch.setattr(
        utils, "warn_if_kubectl_is_shadowed", lambda: warnings.append("warned")
    )

    def fake_subprocess_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return completed_process(cmd)

    monkeypatch.setattr(utils, "subprocess_run", fake_subprocess_run)

    utils.kubectl("get", "pod", capture_output=True)

    assert checks == [True]
    assert warnings == ["warned"]
    assert calls == [
        (
            ["/tmp/asdf-kubectl", "get", "pod"],
            {
                "env": utils.ENV,
                "check": True,
                "dry_run": False,
                "capture_output": True,
                "timeout": 20,
            },
        )
    ]


def test_asdf_global_reports_shadowed_kubectl(monkeypatch):
    asdf_path = "/Users/test/.asdf/installs/kubectl/1.30.0/bin/kubectl"
    messages = []
    clear_caches()
    monkeypatch.setattr(
        utils,
        "asdf",
        lambda *args, **kwargs: completed_process(args, stderr=b"", returncode=0),
    )
    monkeypatch.setattr(utils, "clear_kubectl_caches", lambda: None)
    monkeypatch.setattr(utils, "kubectl_version_challenge", lambda autofix=False: False)
    monkeypatch.setattr(utils, "asdf_which", lambda name: asdf_path)
    monkeypatch.setattr(utils.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    def fake_error(message, exit=None, **kwargs):
        messages.append(message)
        if exit:
            raise SystemExit(exit if isinstance(exit, int) else 1)

    monkeypatch.setattr(utils, "error", fake_error)

    try:
        utils.asdf_global("kubectl", "1.30.0")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("asdf_global should exit when shadowing persists")

    assert messages == [
        "kubectl version still do not match after asdf global kubectl 1.30.0",
        f"shell kubectl still resolves to /usr/local/bin/kubectl, while asdf selected {asdf_path}",
        "put /Users/test/.asdf/shims earlier in PATH, or remove the shadowing kubectl",
    ]
