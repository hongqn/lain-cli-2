from copy import deepcopy
from os.path import basename
from typing import Any, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field as PydanticField,
    ValidationInfo,
    field_validator,
    model_validator,
)

from lain_cli.utils import (
    DEFAULT_WORKDIR,
    ENV,
    INGRESS_CANARY_ANNOTATIONS,
    error,
    recursive_update,
)

RESERVED_WORDS: set[str] = set()


def validate_reserved_word(value: str) -> str:
    if value in RESERVED_WORDS:
        raise ValueError("this is a reserved word, please change")
    return value


def validate_reserved_word_mapping_keys(value: Any) -> Any:
    if value is None:
        return value
    for key in value:
        validate_reserved_word(key)
    return value


def validate_canary_group_annotations(value: Any) -> Any:
    if value is None:
        return value
    for annotations in value.values():
        for key in annotations:
            if key not in INGRESS_CANARY_ANNOTATIONS:
                raise ValueError(f"{key} is not a valid ingress canary annotation")
    return value


class SchemaModel(BaseModel):
    @classmethod
    def load(
        cls, data: Any, *, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        model = cls.model_validate(data, context=context)
        return cast(
            dict[str, Any],
            model.model_dump(mode="python", by_alias=True, exclude_none=True),
        )

    def ensure_model_extra(self) -> dict[str, Any]:
        extra = self.model_extra
        if extra is None:
            extra = {}
            object.__setattr__(self, "__pydantic_extra__", extra)
        return extra


class LenientSchema(SchemaModel):
    model_config = ConfigDict(extra="allow")


class StrictSchema(SchemaModel):
    model_config = ConfigDict(extra="forbid")


class PrepareSchema(LenientSchema):
    script: list[str]
    keep: list[str] = PydanticField(default_factory=list)

    @field_validator("keep")
    @classmethod
    def finalize_keep(cls, keep: list[str]) -> list[str]:
        new_keep = []
        for k in keep:
            if "*" in k:
                raise ValueError(f'keep item should not contain "*", got: {k}')
            if k.startswith("/"):
                raise ValueError(f"keep item should not be abs path, got: {k}")
            if not k.startswith("./"):
                k = f"./{k}"
            new_keep.append(k)

        return new_keep


class BuildSchema(LenientSchema):
    base: str
    prepare: PrepareSchema | None = None
    script: list[str] = PydanticField(default_factory=list)
    workdir: str = DEFAULT_WORKDIR


def parse_copy(stuff: Any) -> dict[str, str]:
    """
    >>> parse_copy('/path')
    {'src': '/path', 'dest': '/path'}
    >>> parse_copy({'src': '/path'})
    {'src': '/path', 'dest': '/path'}
    >>> parse_copy({'src': '/path', 'dest': '/another'})
    {'src': '/path', 'dest': '/another'}
    """
    if isinstance(stuff, str):
        return {"src": stuff, "dest": stuff}
    if isinstance(stuff, dict):
        if "src" not in stuff:
            raise ValueError("if copy clause is a dict, it must contain src")
        if "dest" not in stuff:
            stuff["dest"] = stuff["src"]

        return cast(dict[str, str], stuff)
    raise ValueError(f"copy clause must be str or dict, got {stuff}")


class ReleaseSchema(LenientSchema):
    script: list[str] = PydanticField(default_factory=list)
    workdir: str = DEFAULT_WORKDIR
    dest_base: str | None = None
    copy_: list[dict[str, str]] = PydanticField(default_factory=list, alias="copy")

    @field_validator("copy_", mode="before")
    @classmethod
    def parse_copy_items(cls, value: Any) -> list[dict[str, str]]:
        if value is None:
            return []
        return [parse_copy(item) for item in value]


class VolumeMountSchema(LenientSchema):
    mountPath: str
    subPath: str | None = None

    @field_validator("subPath")
    @classmethod
    def validate_sub_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        bn = basename(value)
        if bn != value:
            raise ValueError(f"subPath should be {bn}, not {value}")
        return value


class HPASchema(LenientSchema):
    @model_validator(mode="after")
    def finalize(self) -> "HPASchema":
        if "targetCPUUtilizationPercentage" in (self.model_extra or {}):
            raise ValueError(
                "you should remove targetCPUUtilizationPercentage from hpa, and use hpa.metrics"
            )
        return self


class ResourceSchema(StrictSchema):
    cpu: Any
    memory: Any


class ResourcesSchema(StrictSchema):
    requests: ResourceSchema
    limits: ResourceSchema


env_schema = dict[str, str] | None


class ProcSchema(LenientSchema):
    env: env_schema = None
    resources: ResourcesSchema | None = None
    command: list[str]

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("command should not be empty")
        executable = value[0]
        if " " in executable:
            raise ValueError(
                f"executable name should not contain space, use list instead, got: {executable}"
            )
        return value


class DeploymentSchema(ProcSchema):
    hpa: HPASchema | None = None
    containerPort: int | None = None
    readinessProbe: Any = PydanticField(default_factory=dict)
    replicaCount: int
    resources: ResourcesSchema | None = None

    @model_validator(mode="after")
    def finalize(self) -> "DeploymentSchema":
        if self.resources is None:
            raise ValueError("Field required")
        if self.containerPort is not None and self.readinessProbe is None:
            raise ValueError(
                "when containerPort is defined, you must use readinessProbe as well"
            )
        return self


class JobSchema(ProcSchema):
    initContainers: list[ProcSchema] | None = None


class CronjobSchema(ProcSchema):
    pass


class IngressSchema(LenientSchema):
    host: str
    deployName: str
    paths: list[str]


class HostAliasSchema(StrictSchema):
    ip: str
    hostnames: list[str]


class ClusterConfigSchema(LenientSchema):
    domain: str = ""
    domain_suffix: str = ""
    extra_docs: str | None = None
    secrets_env: dict[str, Any] | None = None
    hostAliases: list[HostAliasSchema] | None = None

    @model_validator(mode="after")
    def finalize(self, info: ValidationInfo) -> "ClusterConfigSchema":
        if self.extra_docs is not None:
            self.extra_docs = self.extra_docs.strip()

        is_current = bool(info.context and info.context.get("is_current", False))
        if is_current:
            secrets_env = self.secrets_env or {}
            extra = self.ensure_model_extra()
            for dest, env in secrets_env.items():
                if isinstance(env, str):
                    env_name = env
                    hint = ""
                else:
                    env_name = env["env_name"]
                    hint = env["hint"]

                if env_name not in ENV:
                    error(
                        f"environment variable {env_name} is missing, hint: {hint}",
                        exit=1,
                    )
                else:
                    extra[dest] = ENV[env_name]
            self.secrets_env = None

        return self


class HelmValuesSchema(LenientSchema):
    appname: str
    releaseName: str | None = None
    env: env_schema = None
    volumeMounts: list[VolumeMountSchema] | None = None
    deployments: dict[str, DeploymentSchema] | None = None
    deploy: dict[str, DeploymentSchema] | None = None
    deployment: dict[str, DeploymentSchema] | None = None
    jobs: dict[str, JobSchema] | None = None
    job: dict[str, JobSchema] | None = None
    cronjobs: dict[str, CronjobSchema] | None = None
    cronjob: dict[str, CronjobSchema] | None = None
    statefulSets: dict[str, Any] | None = None
    statefulSet: dict[str, Any] | None = None
    statefulset: dict[str, Any] | None = None
    sts: dict[str, Any] | None = None
    tests: dict[str, Any] | None = None
    ingresses: list[IngressSchema] | None = None
    ingress: list[IngressSchema] | None = None
    ing: list[IngressSchema] | None = None
    externalIngresses: list[IngressSchema] | None = None
    externalIngress: list[IngressSchema] | None = None
    externalIng: list[IngressSchema] | None = None
    canaryGroups: dict[str, dict[str, str]] | None = None
    build: BuildSchema | None = None
    release: ReleaseSchema | None = None

    @field_validator("appname", "releaseName")
    @classmethod
    def validate_reserved_word_field(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_reserved_word(value)

    @field_validator(
        "deployments",
        "deploy",
        "deployment",
        "jobs",
        "job",
        "cronjobs",
        "cronjob",
        "statefulSets",
        "statefulSet",
        "statefulset",
        "sts",
        "tests",
        mode="before",
    )
    @classmethod
    def validate_reserved_word_mapping(cls, value: Any) -> Any:
        return validate_reserved_word_mapping_keys(value)

    @field_validator("canaryGroups", mode="before")
    @classmethod
    def validate_canary_groups(cls, value: Any) -> Any:
        return validate_canary_group_annotations(value)

    @staticmethod
    def merge_aliases(
        value: dict[str, Any] | None, aliases: tuple[dict[str, Any] | None, ...] = ()
    ) -> dict[str, Any] | None:
        has_value = value is not None or any(alias is not None for alias in aliases)
        merged = deepcopy(value or {})
        for alias in aliases:
            recursive_update(merged, alias or {})
        if has_value:
            return merged
        return None

    @staticmethod
    def merge_list_aliases(
        value: list[Any] | None, aliases: tuple[list[Any] | None, ...] = ()
    ) -> list[Any] | None:
        has_value = value is not None or any(alias is not None for alias in aliases)
        merged = list(value or [])
        for alias in aliases:
            if alias:
                merged.extend(alias)
        if has_value:
            return merged
        return None

    @model_validator(mode="after")
    def finalize(self) -> "HelmValuesSchema":
        self.deployments = cast(
            dict[str, DeploymentSchema] | None,
            self.merge_aliases(
                self.deployments, aliases=(self.deploy, self.deployment)
            ),
        )
        self.jobs = cast(
            dict[str, JobSchema] | None,
            self.merge_aliases(self.jobs, aliases=(self.job,)),
        )
        self.cronjobs = cast(
            dict[str, CronjobSchema] | None,
            self.merge_aliases(self.cronjobs, aliases=(self.cronjob,)),
        )
        self.statefulSets = self.merge_aliases(
            self.statefulSets,
            aliases=(self.sts, self.statefulSet, self.statefulset),
        )
        self.ingresses = cast(
            list[IngressSchema] | None,
            self.merge_list_aliases(self.ingresses, aliases=(self.ingress, self.ing)),
        )
        self.externalIngresses = cast(
            list[IngressSchema] | None,
            self.merge_list_aliases(
                self.externalIngresses,
                aliases=(self.externalIngress, self.externalIng),
            ),
        )
        for key in ["deployments", "cronjobs", "statefulSets", "tests"]:
            if not getattr(self, key):
                setattr(self, key, {})

        procs = cast(dict[str, Any], (self.deployments or {}).copy())
        procs.update(self.cronjobs or {})
        procs.update(self.statefulSets or {})
        deploy_names = set(self.deployments or [])
        cronjob_names = set(self.cronjobs or [])
        sts_names = set(self.statefulSets or [])
        duplicated_names = [
            deploy_names.intersection(cronjob_names),
            deploy_names.intersection(sts_names),
            cronjob_names.intersection(sts_names),
        ]
        if any(duplicated_names):
            raise ValueError(f"proc names should not duplicate: {duplicated_names}")
        if self.release:
            if not self.build:
                raise ValueError("release defined, but not build")
            if self.release.dest_base is None:
                self.release.dest_base = self.build.base

        self.ensure_model_extra()["procs"] = procs
        return self


for schema in (
    PrepareSchema,
    BuildSchema,
    ReleaseSchema,
    VolumeMountSchema,
    HPASchema,
    ProcSchema,
    DeploymentSchema,
    JobSchema,
    CronjobSchema,
    IngressSchema,
    ClusterConfigSchema,
    HelmValuesSchema,
):
    for name, field in schema.model_fields.items():
        RESERVED_WORDS.add(field.alias or name)


__all__ = [
    "BuildSchema",
    "ClusterConfigSchema",
    "CronjobSchema",
    "DeploymentSchema",
    "HPASchema",
    "HelmValuesSchema",
    "HostAliasSchema",
    "IngressSchema",
    "JobSchema",
    "LenientSchema",
    "PrepareSchema",
    "ProcSchema",
    "ReleaseSchema",
    "RESERVED_WORDS",
    "ResourceSchema",
    "ResourcesSchema",
    "SchemaModel",
    "StrictSchema",
    "VolumeMountSchema",
    "parse_copy",
]
