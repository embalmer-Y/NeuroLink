from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Any, cast

from .maf import build_maf_provider_config


MULTIMODAL_INPUT_SCHEMA_VERSION = "1.2.5-multimodal-input-v1"
INFERENCE_PROFILE_SCHEMA_VERSION = "1.2.5-inference-profile-v1"
INFERENCE_ROUTE_SCHEMA_VERSION = "1.2.5-inference-route-v1"

SUPPORTED_INPUT_MODES = ("text", "image", "audio", "video")
SUPPORTED_RESPONSE_MODES = ("text", "audio")
DEFAULT_RESPONSE_MODES = ("text",)
DEFAULT_LATENCY_CLASS = "interactive"


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