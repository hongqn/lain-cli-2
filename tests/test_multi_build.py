"""Tests for multi-build feature (builds: config)."""

from os.path import join

import pytest

from lain_cli.utils import (
    DEFAULT_BUILD_NAME,
    DEFAULT_WORKDIR,
    context,
    make_image_str,
    tell_build_deps,
    tell_build_order,
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
    res = run(lain, args=["build", "--name", "default"], returncode=None)  # pyright: ignore[reportArgumentType]
    assert "not found" not in res.output


# ===========================================================================
# Phase 2: from: build chaining and prepare: <string> sharing
# ===========================================================================


# ---------------------------------------------------------------------------
# tell_build_order(): topological sort
# ---------------------------------------------------------------------------


def test_tell_build_order_no_deps():
    """Builds without from: should maintain insertion order."""
    builds = {"a": {}, "b": {}, "c": {}}
    result = tell_build_order(builds)
    assert result == ["a", "b", "c"]


def test_tell_build_order_with_deps():
    """Builds with from: should come after their parent."""
    builds = {"worker": {"from": "default"}, "default": {}, "sidecar": {}}
    result = tell_build_order(builds)
    assert result.index("default") < result.index("worker")
    assert len(result) == 3


def test_tell_build_order_chain():
    """Multi-level from: chain should be ordered correctly."""
    builds = {
        "c": {"from": "b"},
        "b": {"from": "a"},
        "a": {},
    }
    result = tell_build_order(builds)
    assert result == ["a", "b", "c"]


def test_tell_build_order_cycle():
    """Circular from: dependency should be detected."""
    builds = {"a": {"from": "b"}, "b": {"from": "a"}}
    # tell_build_order calls error() with exit=1 on cycle
    # In test context this raises SystemExit
    with pytest.raises(SystemExit):
        tell_build_order(builds)


# ---------------------------------------------------------------------------
# tell_build_deps(): dependency chain for --name
# ---------------------------------------------------------------------------


def test_tell_build_deps_no_deps():
    """Build without from: should return just itself."""
    builds = {"a": {}, "b": {}}
    assert tell_build_deps(builds, "b") == ["b"]


def test_tell_build_deps_with_chain():
    """Build with from: chain should return parents first."""
    builds = {
        "a": {},
        "b": {"from": "a"},
        "c": {"from": "b"},
    }
    assert tell_build_deps(builds, "c") == ["a", "b", "c"]


def test_tell_build_deps_single_parent():
    """Build with single from: should return [parent, self]."""
    builds = {"default": {}, "worker": {"from": "default"}}
    assert tell_build_deps(builds, "worker") == ["default", "worker"]


# ---------------------------------------------------------------------------
# tell_builds() with from: and prepare: <string>
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_with_from():
    """Builds with from: should be returned as-is (resolution happens elsewhere)."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {"from": "default", "script": ["echo extra"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    _, builds = run_under_click_context(tell_builds)
    assert builds["worker"]["from"] == "default"
    assert "base" not in builds["worker"]


@pytest.mark.usefixtures("dummy_helm_chart")
def test_tell_builds_with_prepare_string():
    """Builds with prepare: <string> should be returned as-is."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {
            "base": "python:3.12",
            "prepare": {"keep": ["req.txt"], "script": ["pip install"]},
            "script": ["echo ok"],
        },
        "admin": {"prepare": "default", "script": ["echo admin"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    _, builds = run_under_click_context(tell_builds)
    assert builds["admin"]["prepare"] == "default"


# ---------------------------------------------------------------------------
# Lint: from: and prepare: <string> validation
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_from_invalid_reference():
    """lint should error when from: references nonexistent build."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {"from": "nonexistent", "script": ["echo"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "nonexistent" in res.output
    assert "not defined" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_from_with_base_conflicts():
    """lint should error when build has both from: and base:."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {"from": "default", "base": "node:20", "script": ["echo"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "cannot have both" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_from_with_prepare_dict_conflicts():
    """lint should error when build has both from: and prepare: (dict)."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {
            "from": "default",
            "prepare": {"script": ["pip install"]},
            "script": ["echo"],
        },
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "cannot have both" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_from_valid():
    """lint should pass with valid from: references."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {"from": "default", "script": ["echo extra"]},
    }
    values["deployments"]["web"]["build"] = "worker"
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=0)
    assert "not defined" not in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_prepare_string_invalid():
    """lint should error when prepare: <string> references nonexistent build."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "admin": {"prepare": "nonexistent", "script": ["echo"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "nonexistent" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_prepare_string_no_prepare_in_target():
    """lint should error when prepare: <string> target has no prepare definition."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "admin": {"prepare": "default", "script": ["echo"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "no prepare definition" in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_prepare_string_valid():
    """lint should pass when prepare: <string> references a build with prepare."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {
            "base": "python:3.12",
            "prepare": {"keep": ["req.txt"], "script": ["pip install"]},
            "script": ["echo ok"],
        },
        "admin": {"prepare": "default", "script": ["echo admin"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=0)
    assert "not defined" not in res.output


@pytest.mark.usefixtures("dummy_helm_chart")
def test_lint_circular_from():
    """lint should detect circular from: dependencies."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "a": {"from": "b", "script": ["echo a"]},
        "b": {"from": "a", "script": ["echo b"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["-s", "lint"], returncode=1)
    assert "circular" in res.output


# ---------------------------------------------------------------------------
# Dockerfile rendering: from: and prepare: <string>
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_from_build_uses_parent_image():
    """Build with from: should render Dockerfile FROM parent's image."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "worker": {"from": "default", "script": ["echo extra"]},
    }
    yadu(values, DUMMY_VALUES_PATH)

    # Render template for worker build to check FROM line
    from lain_cli.utils import template_env, DOCKERFILE_NAME

    def render_worker_dockerfile():
        ctx = context()
        from lain_cli.utils import tell_image_repo

        builds = tell_builds()
        build_clause = builds["worker"]
        ctx.obj["build_clause"] = build_clause
        ctx.obj["build_image_repo"] = tell_image_repo("worker")
        ctx.obj["from_build_image"] = make_image_str(
            registry="registry.test", image_tag="test-tag", build_name="default"
        )
        ctx.obj["shared_prepare_repo"] = None
        ctx.obj["current_build_stage"] = "build"
        template = template_env.get_template(f"{DOCKERFILE_NAME}.j2")
        return template.render(**ctx.obj)

    _, dockerfile = run_under_click_context(render_worker_dockerfile)
    assert "FROM registry.test/dummy:test-tag AS build" in dockerfile
    assert "FROM python:3.12" not in dockerfile


@pytest.mark.usefixtures("dummy_helm_chart")
def test_template_prepare_string_uses_shared_prepare():
    """Build with prepare: <string> should use referenced build's prepare image."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {
            "base": "python:3.12",
            "prepare": {"keep": ["req.txt"], "script": ["pip install"]},
            "script": ["echo ok"],
        },
        "admin": {"prepare": "default", "script": ["echo admin"]},
    }
    yadu(values, DUMMY_VALUES_PATH)

    from lain_cli.utils import template_env, DOCKERFILE_NAME

    def render_admin_dockerfile():
        ctx = context()
        from lain_cli.utils import tell_image_repo

        builds = tell_builds()
        build_clause = builds["admin"]
        ctx.obj["build_clause"] = build_clause
        ctx.obj["build_image_repo"] = tell_image_repo("admin")
        ctx.obj["from_build_image"] = None
        ctx.obj["shared_prepare_repo"] = tell_image_repo("default")
        ctx.obj["current_build_stage"] = "build"
        template = template_env.get_template(f"{DOCKERFILE_NAME}.j2")
        return template.render(**ctx.obj)

    _, dockerfile = run_under_click_context(render_admin_dockerfile)
    # Should use default's prepare image, not admin's
    assert f"/{DUMMY_APPNAME}:prepare AS build" in dockerfile
    assert f"/{DUMMY_APPNAME}-admin:prepare" not in dockerfile


# ---------------------------------------------------------------------------
# Regression: tell_build_deps() cycle detection (fixes infinite loop)
# ---------------------------------------------------------------------------


def test_tell_build_deps_cycle():
    """tell_build_deps must detect circular from: and raise SystemExit, not loop."""
    builds = {"a": {"from": "b"}, "b": {"from": "a"}}
    with pytest.raises(SystemExit):
        tell_build_deps(builds, "a")


def test_tell_build_deps_self_cycle():
    """A build with from: pointing to itself should be caught."""
    builds = {"x": {"from": "x"}}
    with pytest.raises(SystemExit):
        tell_build_deps(builds, "x")


# ---------------------------------------------------------------------------
# Regression: lain push --name <missing> config-level validation
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_push_name_not_found():
    """lain push --name nonexistent should fail with a clear config error."""
    res = run(lain, args=["push", "--name", "nonexistent"], returncode=1)
    assert "not found" in res.output
    assert "available" in res.output


# ---------------------------------------------------------------------------
# lain image-repos: list image repository names
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("dummy_helm_chart")
def test_image_repos_single_build():
    """image-repos with old-style build: should output just appname."""
    res = run(lain, args=["image-repos"])
    assert DUMMY_APPNAME in res.output.strip()


@pytest.mark.usefixtures("dummy_helm_chart")
def test_image_repos_multi_build():
    """image-repos with builds: should list all repos."""
    values = load_dummy_values()
    del values["build"]
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo"]},
        "gpu": {"base": "nvidia/cuda:12.6", "script": ["echo"]},
    }
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["image-repos"])
    lines = res.output.strip().splitlines()
    assert DUMMY_APPNAME in lines
    assert f"{DUMMY_APPNAME}-gpu" in lines


@pytest.mark.usefixtures("dummy_helm_chart")
def test_image_repos_no_build():
    """image-repos with no build config should output appname."""
    values = load_dummy_values()
    del values["build"]
    yadu(values, DUMMY_VALUES_PATH)
    res = run(lain, args=["image-repos"])
    assert DUMMY_APPNAME in res.output.strip()


@pytest.mark.usefixtures("dummy_helm_chart")
def test_builds_plural_applies_schema_defaults():
    """builds: (plural) should apply BuildSchema defaults like workdir."""
    values = load_dummy_values()
    del values["build"]
    # Omit workdir — BuildSchema should default it to /lain/app
    values["builds"] = {
        "default": {"base": "python:3.12", "script": ["echo ok"]},
        "gpu": {"base": "nvidia/cuda:12.6", "script": ["echo gpu"]},
    }
    yadu(values, DUMMY_VALUES_PATH)

    def check_defaults():
        builds = tell_builds()
        for name, bc in builds.items():
            assert bc.get("workdir") == DEFAULT_WORKDIR, (
                f"build '{name}' missing workdir default"
            )
            assert bc.get("script") is not None

    run_under_click_context(check_defaults)
