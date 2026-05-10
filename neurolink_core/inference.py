from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, cast

from .maf import MAF_PROVIDER_DEPLOYMENT_ENV_VARS
from .maf import MAF_PROVIDER_ENDPOINT_ENV_VARS
from .maf import MAF_PROVIDER_MODEL_ENV_VARS
from .maf import build_maf_provider_config


MULTIMODAL_INPUT_SCHEMA_VERSION = "1.2.5-multimodal-input-v1"
INFERENCE_PROFILE_SCHEMA_VERSION = "1.2.5-inference-profile-v1"
INFERENCE_ROUTE_SCHEMA_VERSION = "1.2.5-inference-route-v1"
PROVIDER_PROFILE_SCHEMA_VERSION = "2.2.1-provider-profile-v1"
PROVIDER_PROFILE_REGISTRY_SCHEMA_VERSION = "2.2.1-provider-profile-registry-v1"
PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION = "2.2.1-provider-profile-config-v1"
MODEL_PROFILE_SMOKE_SCHEMA_VERSION = "2.2.1-model-profile-smoke-v1"
MODEL_LIST_SCHEMA_VERSION = "2.2.1-model-list-v1"

SUPPORTED_INPUT_MODES = ("text", "image", "audio", "video")
SUPPORTED_RESPONSE_MODES = ("text", "audio")
DEFAULT_RESPONSE_MODES = ("text",)
DEFAULT_LATENCY_CLASS = "interactive"
DEFAULT_ACTIVE_MODEL_SLOTS = ("affective", "rational")


@dataclass(frozen=True)
class MediaReference:
    mode: str
    ref: str
    ref_kind: str
    provenance: str

    def to_dict(self) -> dict[str, str]:
        return {
            "mode": self.mode,
            "ref": self.ref,
            "ref_kind": self.ref_kind,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class NormalizedMultimodalInput:
    request_id: str
    profile_hint: str
    input_modes: tuple[str, ...]
    response_modes: tuple[str, ...]
    latency_class: str
    text: tuple[str, ...]
    images: tuple[MediaReference, ...]
    audio: tuple[MediaReference, ...]
    video: tuple[MediaReference, ...]
    provenance: str
    schema_version: str = MULTIMODAL_INPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "profile_hint": self.profile_hint,
            "input_modes": list(self.input_modes),
            "response_modes": list(self.response_modes),
            "latency_class": self.latency_class,
            "inputs": {
                "text": list(self.text),
                "images": [item.to_dict() for item in self.images],
                "audio": [item.to_dict() for item in self.audio],
                "video": [item.to_dict() for item in self.video],
            },
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class InferenceProfile:
    name: str
    backend: str
    model_family: str
    input_modes: tuple[str, ...]
    output_modes: tuple[str, ...]
    local_default: bool
    resource_class: str
    requires_external_service: bool
    priority: int
    schema_version: str = INFERENCE_PROFILE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "backend": self.backend,
            "model_family": self.model_family,
            "input_modes": list(self.input_modes),
            "output_modes": list(self.output_modes),
            "local_default": self.local_default,
            "resource_class": self.resource_class,
            "requires_external_service": self.requires_external_service,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    provider_kind: str
    credential_env_var: str
    endpoint_env_var: str
    model_env_var: str
    deployment_env_var: str
    endpoint_url: str | None = None
    configured_model: str | None = None
    configured_deployment: str | None = None
    endpoint_configured: bool = False
    credential_configured: bool = False
    supports_model_discovery: bool = False
    active_slots: tuple[str, ...] = DEFAULT_ACTIVE_MODEL_SLOTS
    enabled: bool = True
    schema_version: str = PROVIDER_PROFILE_SCHEMA_VERSION

    @property
    def model_identifier_configured(self) -> bool:
        return bool(self.configured_model or self.configured_deployment)

    @property
    def ready_for_model_call(self) -> bool:
        return self.enabled and self.credential_configured and self.model_identifier_configured

    def missing_requirements(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.enabled:
            missing.append("enabled_profile")
        if not self.credential_configured:
            missing.append("credential_reference")
        if not self.model_identifier_configured:
            missing.append("model_identifier")
        return tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "provider_kind": self.provider_kind,
            "enabled": self.enabled,
            "credential_env_var": self.credential_env_var,
            "credential_configured": self.credential_configured,
            "credential_value_masked": "***" if self.credential_configured else "",
            "endpoint_env_var": self.endpoint_env_var,
            "endpoint_url": self.endpoint_url,
            "endpoint_configured": self.endpoint_configured,
            "model_env_var": self.model_env_var,
            "deployment_env_var": self.deployment_env_var,
            "configured_model": self.configured_model,
            "configured_deployment": self.configured_deployment,
            "model_identifier_configured": self.model_identifier_configured,
            "supports_model_discovery": self.supports_model_discovery,
            "active_slots": list(self.active_slots),
            "ready_for_model_call": self.ready_for_model_call,
            "missing_requirements": list(self.missing_requirements()),
        }

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider_kind": self.provider_kind,
            "enabled": self.enabled,
            "credential_env_var": self.credential_env_var,
            "endpoint_env_var": self.endpoint_env_var,
            "endpoint_url": self.endpoint_url,
            "model_env_var": self.model_env_var,
            "deployment_env_var": self.deployment_env_var,
            "configured_model": self.configured_model,
            "configured_deployment": self.configured_deployment,
            "supports_model_discovery": self.supports_model_discovery,
            "active_slots": list(self.active_slots),
        }


@dataclass(frozen=True)
class ProviderProfileRegistry:
    profiles: tuple[ProviderProfile, ...]
    active_affective_profile: str
    active_rational_profile: str
    schema_version: str = PROVIDER_PROFILE_REGISTRY_SCHEMA_VERSION

    def get_profile(self, name: str) -> ProviderProfile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def active_profile_names(self) -> tuple[str, ...]:
        return _dedupe((self.active_affective_profile, self.active_rational_profile))

    def active_profiles(self) -> tuple[ProviderProfile, ...]:
        profiles: list[ProviderProfile] = []
        for profile_name in self.active_profile_names():
            profile = self.get_profile(profile_name)
            if profile is not None:
                profiles.append(profile)
        return tuple(profiles)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active_affective_profile": self.active_affective_profile,
            "active_rational_profile": self.active_rational_profile,
            "active_profile_names": list(self.active_profile_names()),
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


INFERENCE_PROFILES: tuple[InferenceProfile, ...] = (
    InferenceProfile(
        name="local_16g",
        backend="vllm_openai_compatible",
        model_family="gemma-3n-e4b",
        input_modes=("text", "image", "audio", "video"),
        output_modes=("text",),
        local_default=True,
        resource_class="single_local_16gb_gpu",
        requires_external_service=True,
        priority=10,
    ),
    InferenceProfile(
        name="visual_heavy",
        backend="vllm_openai_compatible",
        model_family="qwen3-vl-4b-instruct",
        input_modes=("text", "image", "video"),
        output_modes=("text",),
        local_default=False,
        resource_class="visual_local_or_remote",
        requires_external_service=True,
        priority=20,
    ),
    InferenceProfile(
        name="omni_premium",
        backend="vllm_openai_compatible",
        model_family="qwen3-omni-30b-a3b",
        input_modes=("text", "image", "audio", "video"),
        output_modes=("text", "audio"),
        local_default=False,
        resource_class="premium_multimodal",
        requires_external_service=True,
        priority=30,
    ),
    InferenceProfile(
        name="remote_openai_compatible",
        backend="openai_compatible_remote",
        model_family="operator_configured",
        input_modes=("text", "image", "audio", "video"),
        output_modes=("text",),
        local_default=False,
        resource_class="remote_provider",
        requires_external_service=True,
        priority=90,
    ),
)


def _dedupe(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return tuple(deduped)


def _classify_reference(ref: str) -> str:
    if ref.startswith("http://") or ref.startswith("https://"):
        return "uri"
    if ref.startswith("file:"):
        return "file_uri"
    if "/" in ref or ref.startswith("."):
        return "path"
    return "opaque_id"


def _normalize_refs(mode: str, refs: list[str] | tuple[str, ...], provenance: str) -> tuple[MediaReference, ...]:
    normalized: list[MediaReference] = []
    for raw_ref in refs:
        ref = raw_ref.strip()
        if not ref:
            raise ValueError(f"{mode}_reference_empty")
        if any(char in ref for char in ("\n", "\r", "\t")):
            raise ValueError(f"{mode}_reference_contains_control_whitespace")
        normalized.append(
            MediaReference(
                mode=mode,
                ref=ref,
                ref_kind=_classify_reference(ref),
                provenance=provenance,
            )
        )
    return tuple(normalized)


def normalize_multimodal_input(
    *,
    request_id: str = "multimodal-request-001",
    text: list[str] | tuple[str, ...] | None = None,
    image_refs: list[str] | tuple[str, ...] | None = None,
    audio_refs: list[str] | tuple[str, ...] | None = None,
    video_refs: list[str] | tuple[str, ...] | None = None,
    response_modes: list[str] | tuple[str, ...] | None = None,
    profile_hint: str = "auto",
    latency_class: str = DEFAULT_LATENCY_CLASS,
    provenance: str = "operator_cli",
) -> NormalizedMultimodalInput:
    normalized_text = tuple(item.strip() for item in (text or ()) if item.strip())
    images = _normalize_refs("image", image_refs or (), provenance)
    audio = _normalize_refs("audio", audio_refs or (), provenance)
    video = _normalize_refs("video", video_refs or (), provenance)
    normalized_response_modes = _dedupe(tuple(response_modes or DEFAULT_RESPONSE_MODES))
    unsupported_response_modes = sorted(
        mode for mode in normalized_response_modes if mode not in SUPPORTED_RESPONSE_MODES
    )
    if unsupported_response_modes:
        raise ValueError(
            "unsupported_response_modes:" + ",".join(unsupported_response_modes)
        )

    input_modes: list[str] = []
    if normalized_text:
        input_modes.append("text")
    if images:
        input_modes.append("image")
    if audio:
        input_modes.append("audio")
    if video:
        input_modes.append("video")
    if not input_modes:
        raise ValueError("multimodal_input_requires_at_least_one_input")

    return NormalizedMultimodalInput(
        request_id=request_id,
        profile_hint=profile_hint or "auto",
        input_modes=tuple(input_modes),
        response_modes=normalized_response_modes,
        latency_class=latency_class or DEFAULT_LATENCY_CLASS,
        text=normalized_text,
        images=images,
        audio=audio,
        video=video,
        provenance=provenance,
    )


def get_inference_profile(name: str) -> InferenceProfile | None:
    for profile in INFERENCE_PROFILES:
        if profile.name == name:
            return profile
    return None


def inference_profile_catalog() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in INFERENCE_PROFILES]


def _first_present_env_var(
    env: Mapping[str, str],
    names: tuple[str, ...],
) -> tuple[str, str | None]:
    for name in names:
        value = env.get(name)
        if value:
            return name, value
    return names[0], None


def _credential_present(env: Mapping[str, str], name: str) -> bool:
    return bool(name and env.get(name))


def default_provider_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "runtime_provider_profiles.json"


def _normalize_slots(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return DEFAULT_ACTIVE_MODEL_SLOTS
    raw_items = cast(list[Any], raw_value)
    slots = tuple(
        str(item) for item in raw_items if str(item) in DEFAULT_ACTIVE_MODEL_SLOTS
    )
    return slots or DEFAULT_ACTIVE_MODEL_SLOTS


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return default


def load_provider_profile_config(
    *,
    config_path: str = "",
) -> dict[str, Any]:
    resolved_path = Path(config_path) if config_path else default_provider_config_path()
    if not resolved_path.exists():
        return {
            "schema_version": PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION,
            "config_path": str(resolved_path),
            "exists": False,
            "active_affective_profile": "openai_compatible",
            "active_rational_profile": "openai_compatible",
            "profiles": [],
        }
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider_profile_config_invalid_payload")
    payload_dict = cast(dict[str, Any], payload)
    return {
        "schema_version": str(
            payload_dict.get("schema_version")
            or PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION
        ),
        "config_path": str(resolved_path),
        "exists": True,
        "active_affective_profile": str(
            payload_dict.get("active_affective_profile") or "openai_compatible"
        ),
        "active_rational_profile": str(
            payload_dict.get("active_rational_profile") or "openai_compatible"
        ),
        "profiles": list(cast(list[Any], payload_dict.get("profiles") or [])),
    }


def _write_provider_profile_config(payload: dict[str, Any], *, config_path: str = "") -> dict[str, Any]:
    resolved_path = Path(config_path) if config_path else default_provider_config_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    write_payload: dict[str, Any] = {
        "schema_version": PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION,
        "active_affective_profile": str(payload.get("active_affective_profile") or "openai_compatible"),
        "active_rational_profile": str(payload.get("active_rational_profile") or "openai_compatible"),
        "profiles": list(payload.get("profiles") or []),
    }
    resolved_path.write_text(json.dumps(write_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **write_payload,
        "config_path": str(resolved_path),
        "exists": True,
    }


def _overlay_profile_from_config(
    profile: ProviderProfile,
    config_entry: dict[str, Any],
    *,
    env: Mapping[str, str],
) -> ProviderProfile:
    credential_env_var = str(config_entry.get("credential_env_var") or profile.credential_env_var)
    endpoint_env_var = str(config_entry.get("endpoint_env_var") or profile.endpoint_env_var)
    model_env_var = str(config_entry.get("model_env_var") or profile.model_env_var)
    deployment_env_var = str(config_entry.get("deployment_env_var") or profile.deployment_env_var)
    endpoint_url = str(config_entry.get("endpoint_url") or profile.endpoint_url or "") or None
    configured_model = cast(str | None, config_entry.get("configured_model") or profile.configured_model)
    configured_deployment = cast(
        str | None,
        config_entry.get("configured_deployment") or profile.configured_deployment,
    )
    return ProviderProfile(
        name=str(config_entry.get("name") or profile.name),
        provider_kind=str(config_entry.get("provider_kind") or profile.provider_kind),
        credential_env_var=credential_env_var,
        endpoint_env_var=endpoint_env_var,
        model_env_var=model_env_var,
        deployment_env_var=deployment_env_var,
        endpoint_url=endpoint_url,
        configured_model=configured_model,
        configured_deployment=configured_deployment,
        endpoint_configured=bool(endpoint_url or (endpoint_env_var and env.get(endpoint_env_var))),
        credential_configured=_credential_present(env, credential_env_var),
        supports_model_discovery=_coerce_bool(
            config_entry.get("supports_model_discovery"),
            default=profile.supports_model_discovery,
        ),
        active_slots=_normalize_slots(config_entry.get("active_slots")),
        enabled=_coerce_bool(config_entry.get("enabled"), default=profile.enabled),
    )


def provider_profile_registry(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
    active_affective_profile: str | None = None,
    active_rational_profile: str | None = None,
) -> ProviderProfileRegistry:
    resolved_env = env if env is not None else os.environ
    config_payload = load_provider_profile_config(config_path=config_path)
    endpoint_env_var, _endpoint_value = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_ENDPOINT_ENV_VARS,
    )
    model_env_var, configured_model = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_MODEL_ENV_VARS,
    )
    deployment_env_var, configured_deployment = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_DEPLOYMENT_ENV_VARS,
    )
    detected_kind = build_maf_provider_config(env=resolved_env).provider_kind

    openai_profile = ProviderProfile(
        name="openai_compatible",
        provider_kind="openai_compatible",
        credential_env_var="OPENAI_API_KEY",
        endpoint_env_var=endpoint_env_var if endpoint_env_var == "OPENAI_BASE_URL" else "OPENAI_BASE_URL",
        model_env_var=model_env_var,
        deployment_env_var="",
        configured_model=configured_model,
        credential_configured=_credential_present(resolved_env, "OPENAI_API_KEY"),
        endpoint_configured=bool(resolved_env.get("OPENAI_BASE_URL")),
        supports_model_discovery=True,
        enabled=detected_kind in {"openai_compatible", "unknown"},
    )
    azure_profile = ProviderProfile(
        name="azure_openai",
        provider_kind="azure_openai",
        credential_env_var="AZURE_OPENAI_API_KEY",
        endpoint_env_var="AZURE_OPENAI_ENDPOINT",
        model_env_var="",
        deployment_env_var=deployment_env_var,
        endpoint_url=None,
        configured_deployment=configured_deployment,
        credential_configured=_credential_present(resolved_env, "AZURE_OPENAI_API_KEY"),
        endpoint_configured=bool(resolved_env.get("AZURE_OPENAI_ENDPOINT")),
        enabled=detected_kind in {"azure_openai", "unknown"},
    )
    profiles_by_name: dict[str, ProviderProfile] = {
        openai_profile.name: openai_profile,
        azure_profile.name: azure_profile,
    }
    for raw_entry in cast(list[Any], config_payload.get("profiles") or []):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, Any], raw_entry)
        profile_name = str(entry.get("name") or "")
        if not profile_name:
            continue
        base_profile = profiles_by_name.get(
            profile_name,
            ProviderProfile(
                name=profile_name,
                provider_kind=str(entry.get("provider_kind") or "custom"),
                credential_env_var=str(entry.get("credential_env_var") or "OPENAI_API_KEY"),
                endpoint_env_var=str(entry.get("endpoint_env_var") or "OPENAI_BASE_URL"),
                model_env_var=str(entry.get("model_env_var") or "OPENAI_MODEL"),
                deployment_env_var=str(entry.get("deployment_env_var") or ""),
                enabled=True,
            ),
        )
        profiles_by_name[profile_name] = _overlay_profile_from_config(
            base_profile,
            entry,
            env=resolved_env,
        )
    return ProviderProfileRegistry(
        profiles=tuple(profiles_by_name.values()),
        active_affective_profile=active_affective_profile
        or str(config_payload.get("active_affective_profile") or "openai_compatible"),
        active_rational_profile=active_rational_profile
        or str(config_payload.get("active_rational_profile") or "openai_compatible"),
    )


def provider_profile_catalog(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
) -> dict[str, Any]:
    registry = provider_profile_registry(env=env, config_path=config_path)
    config_payload = load_provider_profile_config(config_path=config_path)
    payload = registry.to_dict()
    payload["config_path"] = str(config_payload.get("config_path") or default_provider_config_path())
    payload["config_exists"] = bool(config_payload.get("exists", False))
    payload["config_schema_version"] = str(
        config_payload.get("schema_version") or PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION
    )
    return payload


def build_provider_runtime_env(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
    preferred_slot: str = "affective",
) -> dict[str, str]:
    base_env = dict(env if env is not None else os.environ)
    registry = provider_profile_registry(env=base_env, config_path=config_path)
    active_profile_name = (
        registry.active_affective_profile
        if preferred_slot == "affective"
        else registry.active_rational_profile
    )
    profile = registry.get_profile(active_profile_name)
    if profile is None:
        return base_env

    runtime_env = dict(base_env)
    if profile.provider_kind == "azure_openai":
        canonical_credential_env = "AZURE_OPENAI_API_KEY"
        canonical_endpoint_env = "AZURE_OPENAI_ENDPOINT"
        canonical_model_env = "AZURE_OPENAI_CHAT_DEPLOYMENT"
        configured_identifier = profile.configured_deployment or profile.configured_model
    else:
        canonical_credential_env = "OPENAI_API_KEY"
        canonical_endpoint_env = "OPENAI_BASE_URL"
        canonical_model_env = "OPENAI_MODEL"
        configured_identifier = profile.configured_model or profile.configured_deployment

    credential_value = runtime_env.get(profile.credential_env_var) or runtime_env.get(
        canonical_credential_env
    )
    if credential_value:
        runtime_env[canonical_credential_env] = credential_value

    endpoint_value = (
        profile.endpoint_url
        or runtime_env.get(profile.endpoint_env_var)
        or runtime_env.get(canonical_endpoint_env)
    )
    if endpoint_value:
        runtime_env[canonical_endpoint_env] = endpoint_value

    if configured_identifier:
        runtime_env[canonical_model_env] = configured_identifier

    return runtime_env


def provider_model_list(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
) -> dict[str, Any]:
    registry = provider_profile_registry(env=env, config_path=config_path)
    entries: list[dict[str, Any]] = []
    for profile in registry.profiles:
        entries.append(
            {
                "profile": profile.name,
                "provider_kind": profile.provider_kind,
                "configured_model": profile.configured_model,
                "configured_deployment": profile.configured_deployment,
                "effective_model_identifier": profile.configured_deployment or profile.configured_model or "",
                "active_slots": list(profile.active_slots),
                "ready_for_model_call": profile.ready_for_model_call,
                "supports_model_discovery": profile.supports_model_discovery,
                "missing_requirements": list(profile.missing_requirements()),
            }
        )
    return {
        "schema_version": MODEL_LIST_SCHEMA_VERSION,
        "command": "model-list",
        "config_path": str(load_provider_profile_config(config_path=config_path).get("config_path") or default_provider_config_path()),
        "active_affective_profile": registry.active_affective_profile,
        "active_rational_profile": registry.active_rational_profile,
        "configured_profiles": entries,
        "inference_profiles": inference_profile_catalog(),
        "ok": True,
    }


def provider_config_update(
    *,
    profile_name: str,
    config_path: str = "",
    provider_kind: str | None = None,
    credential_env_var: str | None = None,
    endpoint_env_var: str | None = None,
    endpoint_url: str | None = None,
    model_env_var: str | None = None,
    deployment_env_var: str | None = None,
    configured_model: str | None = None,
    configured_deployment: str | None = None,
    supports_model_discovery: bool | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    config_payload = load_provider_profile_config(config_path=config_path)
    profiles = [
        cast(dict[str, Any], entry)
        for entry in cast(list[Any], config_payload.get("profiles") or [])
        if isinstance(entry, dict)
    ]
    existing_index: int | None = None
    for index, entry in enumerate(profiles):
        if str(entry.get("name") or "") == profile_name:
            existing_index = index
            break
    current_entry: dict[str, Any] = (
        profiles[existing_index] if existing_index is not None else {"name": profile_name}
    )
    updated_entry: dict[str, Any] = dict(current_entry)
    if provider_kind is not None:
        updated_entry["provider_kind"] = provider_kind
    if credential_env_var is not None:
        updated_entry["credential_env_var"] = credential_env_var
    if endpoint_env_var is not None:
        updated_entry["endpoint_env_var"] = endpoint_env_var
    if endpoint_url is not None:
        updated_entry["endpoint_url"] = endpoint_url
    if model_env_var is not None:
        updated_entry["model_env_var"] = model_env_var
    if deployment_env_var is not None:
        updated_entry["deployment_env_var"] = deployment_env_var
    if configured_model is not None:
        updated_entry["configured_model"] = configured_model
    if configured_deployment is not None:
        updated_entry["configured_deployment"] = configured_deployment
    if supports_model_discovery is not None:
        updated_entry["supports_model_discovery"] = supports_model_discovery
    if enabled is not None:
        updated_entry["enabled"] = enabled
    if existing_index is None:
        profiles.append(updated_entry)
    else:
        profiles[existing_index] = updated_entry
    written = _write_provider_profile_config(
        {
            "active_affective_profile": config_payload.get("active_affective_profile") or "openai_compatible",
            "active_rational_profile": config_payload.get("active_rational_profile") or "openai_compatible",
            "profiles": profiles,
        },
        config_path=config_path,
    )
    return {
        "schema_version": PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION,
        "command": "provider-config",
        "config_path": str(written.get("config_path") or default_provider_config_path()),
        "updated_profile": profile_name,
        "config": written,
        "provider_profile_registry": provider_profile_catalog(config_path=config_path),
        "ok": True,
    }


def set_active_provider_profile(
    *,
    slot: str,
    profile_name: str,
    config_path: str = "",
) -> dict[str, Any]:
    if slot not in DEFAULT_ACTIVE_MODEL_SLOTS:
        raise ValueError("unsupported_model_slot")
    config_payload = load_provider_profile_config(config_path=config_path)
    updated_payload: dict[str, Any] = {
        "active_affective_profile": profile_name
        if slot == "affective"
        else str(config_payload.get("active_affective_profile") or "openai_compatible"),
        "active_rational_profile": profile_name
        if slot == "rational"
        else str(config_payload.get("active_rational_profile") or "openai_compatible"),
        "profiles": list(config_payload.get("profiles") or []),
    }
    written = _write_provider_profile_config(updated_payload, config_path=config_path)
    return {
        "schema_version": PROVIDER_PROFILE_CONFIG_SCHEMA_VERSION,
        "command": "model-set-active",
        "config_path": str(written.get("config_path") or default_provider_config_path()),
        "slot": slot,
        "active_profile": profile_name,
        "provider_profile_registry": provider_profile_catalog(config_path=config_path),
        "ok": True,
    }


def model_profile_smoke(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
    active_affective_profile: str | None = None,
    active_rational_profile: str | None = None,
) -> dict[str, Any]:
    registry = provider_profile_registry(
        env=env,
        config_path=config_path,
        active_affective_profile=active_affective_profile,
        active_rational_profile=active_rational_profile,
    )
    active_profiles = registry.active_profiles()
    known_profile_names = {profile.name for profile in registry.profiles}
    unknown_active_profiles = sorted(
        set(registry.active_profile_names()).difference(known_profile_names)
    )
    active_ready = bool(active_profiles) and all(
        profile.ready_for_model_call for profile in active_profiles
    )
    missing_requirements = {
        profile.name: list(profile.missing_requirements())
        for profile in active_profiles
        if not profile.ready_for_model_call
    }
    fail_closed = bool(unknown_active_profiles) or bool(missing_requirements)
    registry_payload = registry.to_dict()
    closure_gates = {
        "provider_profiles_recorded": bool(registry.profiles),
        "active_slots_recorded": bool(registry.active_affective_profile)
        and bool(registry.active_rational_profile),
        "active_profiles_resolve_or_fail_closed": not unknown_active_profiles
        or fail_closed,
        "missing_requirements_recorded": not fail_closed
        or bool(unknown_active_profiles)
        or bool(missing_requirements),
        "secret_values_masked": "secret" not in json.dumps(
            registry_payload,
            separators=(",", ":"),
        ).lower(),
        "no_model_call_executed": True,
    }
    return {
        "ok": all(closure_gates.values()),
        "status": "ready" if active_ready else "configured_fail_closed",
        "reason": "active_model_profiles_ready"
        if active_ready
        else "active_model_profiles_not_ready",
        "command": "model-profile-smoke",
        "schema_version": MODEL_PROFILE_SMOKE_SCHEMA_VERSION,
        "config_path": str(load_provider_profile_config(config_path=config_path).get("config_path") or default_provider_config_path()),
        "provider_profile_registry": registry_payload,
        "active_profile_readiness": [profile.to_dict() for profile in active_profiles],
        "unknown_active_profiles": unknown_active_profiles,
        "missing_requirements": missing_requirements,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "active_affective_profile": registry.active_affective_profile,
            "active_rational_profile": registry.active_rational_profile,
            "active_profile_count": len(active_profiles),
            "active_profiles_ready": active_ready,
            "unknown_active_profile_count": len(unknown_active_profiles),
            "fail_closed": fail_closed,
        },
        "executes_model_call": False,
    }


def profile_readiness(
    profile: InferenceProfile,
    *,
    env: Mapping[str, str] | None = None,
    require_live_backend: bool = False,
) -> dict[str, Any]:
    if not require_live_backend:
        return {
            "profile": profile.name,
            "ok": True,
            "status": "deterministic_ready",
            "reason": "live_backend_not_required_for_deterministic_route",
            "requires_external_service": profile.requires_external_service,
        }

    resolved_env = env if env is not None else os.environ
    provider_config = build_maf_provider_config(env=resolved_env)
    ready = provider_config.ready_for_model_call
    if ready:
        status = "ready"
        reason = "provider_configuration_available"
    elif not provider_config.credentials_available:
        status = "unavailable"
        reason = "model_credentials_not_configured"
    else:
        status = "unavailable"
        reason = "model_identifier_not_configured"
    return {
        "profile": profile.name,
        "ok": ready,
        "status": status,
        "reason": reason,
        "requires_external_service": profile.requires_external_service,
        "provider_config": provider_config.to_dict(),
    }


def build_inference_route(
    normalized_input: NormalizedMultimodalInput,
    *,
    profile_override: str = "",
    env: Mapping[str, str] | None = None,
    require_live_backend: bool = False,
) -> dict[str, Any]:
    requested_profile = profile_override or normalized_input.profile_hint
    if requested_profile == "auto":
        requested_profile = ""

    candidate_profiles = list(INFERENCE_PROFILES)
    if requested_profile:
        selected = get_inference_profile(requested_profile)
        if selected is None:
            return {
                "schema_version": INFERENCE_ROUTE_SCHEMA_VERSION,
                "ok": False,
                "status": "profile_not_found",
                "requested_profile": requested_profile,
                "failure_status": "unknown_inference_profile",
                "normalized_input": normalized_input.to_dict(),
                "available_profiles": [profile.name for profile in INFERENCE_PROFILES],
            }
        candidate_profiles = [selected]

    required_inputs = set(normalized_input.input_modes)
    required_outputs = set(normalized_input.response_modes)
    rejections: list[dict[str, Any]] = []
    for profile in sorted(candidate_profiles, key=lambda item: item.priority):
        missing_inputs = sorted(required_inputs.difference(profile.input_modes))
        missing_outputs = sorted(required_outputs.difference(profile.output_modes))
        readiness = profile_readiness(
            profile,
            env=env,
            require_live_backend=require_live_backend,
        )
        if not missing_inputs and not missing_outputs and readiness["ok"]:
            return {
                "schema_version": INFERENCE_ROUTE_SCHEMA_VERSION,
                "ok": True,
                "status": "routed",
                "selected_profile": profile.to_dict(),
                "profile_readiness": readiness,
                "requested_profile": requested_profile or "auto",
                "normalized_input": normalized_input.to_dict(),
                "route_reason": "operator_override" if requested_profile else "best_available_profile",
                "fallback_used": False,
                "candidate_rejections": rejections,
            }
        rejections.append(
            {
                "profile": profile.name,
                "missing_input_modes": missing_inputs,
                "missing_response_modes": missing_outputs,
                "readiness": readiness,
            }
        )

    return {
        "schema_version": INFERENCE_ROUTE_SCHEMA_VERSION,
        "ok": False,
        "status": "no_compatible_profile",
        "requested_profile": requested_profile or "auto",
        "failure_status": "no_profile_supports_requested_modes_and_readiness",
        "normalized_input": normalized_input.to_dict(),
        "candidate_rejections": rejections,
    }


def multimodal_profile_smoke(
    *,
    text: list[str] | tuple[str, ...] | None = None,
    image_refs: list[str] | tuple[str, ...] | None = None,
    audio_refs: list[str] | tuple[str, ...] | None = None,
    video_refs: list[str] | tuple[str, ...] | None = None,
    response_modes: list[str] | tuple[str, ...] | None = None,
    profile_hint: str = "auto",
    profile_override: str = "",
    require_live_backend: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_multimodal_input(
        text=text,
        image_refs=image_refs,
        audio_refs=audio_refs,
        video_refs=video_refs,
        response_modes=response_modes,
        profile_hint=profile_hint,
        provenance="multimodal_profile_smoke",
    )
    route = build_inference_route(
        normalized,
        profile_override=profile_override,
        env=env,
        require_live_backend=require_live_backend,
    )
    route_ok = bool(route.get("ok"))
    selected_profile = cast(
        dict[str, Any] | None,
        route.get("selected_profile") if route_ok else None,
    )
    selected_profile_name = (
        str(selected_profile.get("name") or "")
        if isinstance(selected_profile, dict)
        else ""
    )
    closure_gates = {
        "multimodal_input_recorded": True,
        "route_decision_recorded": True,
        "profile_readiness_recorded": bool(
            route.get("profile_readiness") or route.get("candidate_rejections")
        ),
        "route_ready": route_ok,
        "fail_closed_when_unroutable": route_ok
        or str(route.get("status") or "")
        in {"profile_not_found", "no_compatible_profile"},
        "no_model_call_executed": True,
    }
    return {
        "ok": route_ok,
        "status": "ready" if route_ok else "error",
        "command": "multimodal-profile-smoke",
        "schema_version": INFERENCE_ROUTE_SCHEMA_VERSION,
        "multimodal_input": normalized.to_dict(),
        "inference_route": route,
        "evidence_summary": {
            "input_modes": list(normalized.input_modes),
            "response_modes": list(normalized.response_modes),
            "requested_profile": str(route.get("requested_profile") or "auto"),
            "selected_profile": selected_profile_name,
            "route_status": str(route.get("status") or "unknown"),
            "route_reason": str(route.get("route_reason") or ""),
            "fallback_used": bool(route.get("fallback_used", False)),
            "failure_status": str(route.get("failure_status") or ""),
            "candidate_rejection_count": len(
                list(route.get("candidate_rejections") or [])
            ),
            "requires_live_backend": require_live_backend,
        },
        "closure_gates": closure_gates,
        "profile_catalog": inference_profile_catalog(),
        "requires_live_backend": require_live_backend,
        "executes_model_call": False,
    }