"""Tests for multi-build feature (builds: config)."""

from os.path import join

import pytest

from lain_cli.utils import (
    DEFAULT_BUILD_NAME,
    make_image_str,
    tell_builds,
    tell_image_repo,
    yadu,
)
from tests.conftest import (
    CHART_DIR_NAME,
    DUMMY_APPNAME,
    DUMMY_VALUES_PATH,
    TEST_CLUSTER,
    load_dummy_values,
    render_k8s_specs,
    run,
    run_under_click_context,
)
from lain_cli.lain import lain


# ---------------------------------------------------------------------------
# tell_builds(): normalization of old and new config formats
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_old_format():
    """Old `build:` (singular) should be normalized to {"default": build_clause}."""
    values = load_dummy_values()
    assert "build" in values
    assert "builds" not in values
    _, builds = run_under_click_context(tell_builds)
    assert list(builds.keys()) == [DEFAULT_BUILD_NAME]
    assert builds[DEFAULT_BUILD_NAME]["base"] == values["build"]["base"]


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_old_format_with_release():
    """Old format: top-level `release:` should be merged into the build clause."""
    values = load_dummy_values()
    values["release"] = {
        "dest_base": "nginx:alpine",
        "copy": [{"src": "/lain/app/dist", "dest": "/usr/share/nginx/html"}],
    }
    yadu(values, DUMMY_VALUES_PATH)
    _, builds = run_under_click_context(tell_builds)
    assert "release" in builds[DEFAULT_BUILD_NAME]
    assert builds[DEFAULT_BUILD_NAME]["release"]["dest_base"] == "nginx:alpine"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_new_format():
    """New `builds:` (plural) should be returned as-is."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {
            "base": "python:3.12",
            "script": ["pip install -r requirements.txt"],
        },
        "web": {
            "base": "node:20",
            "script": ["npm ci"],
        },
    }
    yadu(values, DUMMY_VALUES_PATH)
    _, builds = run_under_click_context(tell_builds)
    assert set(builds.keys()) == {"default", "web"}
    assert builds["default"]["base"] == "python:3.12"
    assert builds["web"]["base"] == "node:20"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_mutually_exclusive():
    """Having both `build:` and `builds:` should fail."""
    values = load_dummy_values()
    values["builds"] = {"extra": {"base": "node:20", "script": ["npm ci"]}}
    yadu(values, DUMMY_VALUES_PATH)
    res, _ = run_under_click_context(tell_builds, returncode=1)
    assert "cannot define both" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_empty():
    """No build or builds defined should return empty dict."""
    values = load_dummy_values()
    del values["build"]
    yadu(values, DUMMY_VALUES_PATH)
    _, builds = run_under_click_context(tell_builds)
    assert builds == {}


# ---------------------------------------------------------------------------
# tell_image_repo(): image repository naming
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_image_repo_default():
    """Default build should return plain appname."""
    _, repo = run_under_click_context(tell_image_repo, kwargs={"build_name": "default"})
    assert repo == DUMMY_APPNAME


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_image_repo_none():
    """None build_name should also return plain appname."""
    _, repo = run_under_click_context(tell_image_repo, kwargs={"build_name": None})
    assert repo == DUMMY_APPNAME


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_image_repo_named():
    """Named build should return appname-{name}."""
    _, repo = run_under_click_context(tell_image_repo, kwargs={"build_name": "web"})
    assert repo == f"{DUMMY_APPNAME}-web"


# ---------------------------------------------------------------------------
# make_image_str(): full image string with build_name
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_make_image_str_default_build():
    """Default build_name: image string should not have suffix."""
    image_tag = "1.0"
    _, image = run_under_click_context(
        make_image_str,
        kwargs={
            "registry": "private.com",
            "image_tag": image_tag,
            "build_name": "default",
        },
    )
    assert image == f"private.com/{DUMMY_APPNAME}:1.0"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_make_image_str_named_build():
    """Named build: image string should have -{name} suffix."""
    image_tag = "1.0"
    _, image = run_under_click_context(
        make_image_str,
        kwargs={"registry": "private.com", "image_tag": image_tag, "build_name": "web"},
    )
    assert image == f"private.com/{DUMMY_APPNAME}-web:1.0"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_make_image_str_no_build_name():
    """No build_name (backward compat): should produce plain appname."""
    image_tag = "1.0"
    _, image = run_under_click_context(
        make_image_str,
        kwargs={"registry": "private.com", "image_tag": image_tag},
    )
    assert image == f"private.com/{DUMMY_APPNAME}:1.0"


# ---------------------------------------------------------------------------
# Helm template rendering: deployment image resolution with build: field
# ---------------------------------------------------------------------------


def tell_deployment_image(deployment):
    container_spec = deployment["spec"]["template"]["spec"]
    containers = container_spec["containers"][0]
    return containers["image"]


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_old_format_unchanged():
    """Old format (build: singular) should render deployment image as before."""
    k8s_specs = render_k8s_specs()
    deployment = next(spec for spec in k8s_specs if spec["kind"] == "Deployment")
    image = tell_deployment_image(deployment)
    # image should be {registry}/{appname}:{imageTag}
    assert f"/{DUMMY_APPNAME}:" in image
    # should NOT contain a build suffix
    assert "-web:" not in image


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_multi_build_with_build_field():
    """Deployment with `build: web` should render image using chart.buildImage."""
    values = load_dummy_values()
    values["deployments"]["web"]["build"] = "web"
    fake_registry = "registry.fake"
    fake_image_tag = "test-tag"
    yadu(values, DUMMY_VALUES_PATH)
    override = {"registry": fake_registry, "imageTag": fake_image_tag}
    yadu(override, join(CHART_DIR_NAME, f"values-{TEST_CLUSTER}.yaml"))
    k8s_specs = render_k8s_specs()
    deployment = next(spec for spec in k8s_specs if spec["kind"] == "Deployment")
    image = tell_deployment_image(deployment)
    assert image == f"{fake_registry}/{DUMMY_APPNAME}-web:{fake_image_tag}"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_multi_build_default_no_suffix():
    """Deployment with `build: default` should render image without suffix."""
    values = load_dummy_values()
    values["deployments"]["web"]["build"] = "default"
    fake_registry = "registry.fake"
    fake_image_tag = "test-tag"
    yadu(values, DUMMY_VALUES_PATH)
    override = {"registry": fake_registry, "imageTag": fake_image_tag}
    yadu(override, join(CHART_DIR_NAME, f"values-{TEST_CLUSTER}.yaml"))
    k8s_specs = render_k8s_specs()
    deployment = next(spec for spec in k8s_specs if spec["kind"] == "Deployment")
    image = tell_deployment_image(deployment)
    assert image == f"{fake_registry}/{DUMMY_APPNAME}:{fake_image_tag}"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_no_build_field_uses_chart_image():
    """Deployment without `build:` field should use chart.image (default)."""
    values = load_dummy_values()
    assert "build" not in values["deployments"]["web"]
    fake_registry = "registry.fake"
    fake_image_tag = "test-tag"
    override = {"registry": fake_registry, "imageTag": fake_image_tag}
    yadu(override, join(CHART_DIR_NAME, f"values-{TEST_CLUSTER}.yaml"))
    k8s_specs = render_k8s_specs()
    deployment = next(spec for spec in k8s_specs if spec["kind"] == "Deployment")
    image = tell_deployment_image(deployment)
    assert image == f"{fake_registry}/{DUMMY_APPNAME}:{fake_image_tag}"


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_image_field_takes_priority():
    """Deployment with both `image:` and `build:` — `image:` should win."""
    values = load_dummy_values()
    values["deployments"]["web"]["image"] = "nginx:alpine"
    values["deployments"]["web"]["build"] = "web"
    yadu(values, DUMMY_VALUES_PATH)
    k8s_specs = render_k8s_specs()
    deployment = next(spec for spec in k8s_specs if spec["kind"] == "Deployment")
    image = tell_deployment_image(deployment)
    assert image == "nginx:alpine"


# ---------------------------------------------------------------------------
# Lint: build reference validation
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_invalid_build_reference():
    """lint should error when deployment references nonexistent build."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
    }
    values["deployments"]["web"]["build"] = "nonexistent"
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "nonexistent" in res.output
    assert "not defined" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_valid_build_reference():
    """lint should pass when deployment references an existing build."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "web": {"base": "node:20", "script": ["echo ok"]},
    }
    values["deployments"]["web"]["build"] = "web"
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=0)
    assert "not defined" not in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_no_default_build_warns():
    """lint should warn when multi-build has no 'default' and some workloads lack build: field."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "api": {"base": "python:3.12", "script": ["echo ok"]},
        "web": {"base": "node:20", "script": ["echo ok"]},
    }
    # web deployment has no build: field and no image/imageTag either
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=0)
    assert "no 'build' field" in res.output
    assert "no 'default' build exists" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_old_format_no_new_warnings():
    """lint on old format (build: singular) should not produce multi-build warnings."""
    values = load_dummy_values()
    assert "build" in values
    assert "builds" not in values
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=0)
    assert "no 'build' field" not in res.output
    assert "not defined in builds" not in res.output


# ---------------------------------------------------------------------------
# CLI: build --name validation
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_build_name_not_found():
    """lain build --name nonexistent should fail with helpful error."""
    res = run(lain, args=["build", "--name", "nonexistent"], returncode=1)
    assert "not found" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_build_name_valid_with_old_format():
    """lain build --name default should be accepted when using old build: format."""
    # We can't actually docker-build without a daemon, but we can check that
    # it gets past validation (will fail at docker step, not at name validation)
    res = run(lain, args=["build", "--name", "default"], returncode=None)
    assert "not found" not in res.output
