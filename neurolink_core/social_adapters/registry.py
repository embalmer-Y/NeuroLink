from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
from urllib.parse import urlparse
from typing import Any, cast

from ..social import MockSocialAdapter, SocialDeliveryRecord, SocialMessageEnvelope
from .onebot_qq import OneBotQQSocialAdapter
from .qq_openclaw import QQOpenClawSocialAdapter
from .qq_official import QQOfficialSocialAdapter
from .samples import onebot_direct_message_sample
from .samples import onebot_group_message_no_mention_sample
from .samples import onebot_direct_message_sample
from .samples import qq_openclaw_direct_message_sample
from .samples import qq_openclaw_group_message_no_mention_sample
from .samples import qq_openclaw_group_message_sample
from .samples import onebot_group_message_sample, qq_official_group_message_sample
from .samples import qq_official_direct_message_sample
from .samples import qq_official_group_message_no_mention_sample
from .samples import wechat_ilink_direct_message_sample
from .samples import wechat_ilink_group_message_no_mention_sample
from .samples import wechat_ilink_group_message_sample
from .samples import wecom_direct_message_sample
from .samples import wecom_group_message_no_mention_sample
from .samples import wecom_group_message_sample
from .wechat_ilink import WeChatILinkSocialAdapter
from .wecom import WeComSocialAdapter
SOCIAL_ADAPTER_SAMPLE_SCENARIOS = ("group", "direct", "group_no_mention")




SOCIAL_ADAPTER_PROFILE_SCHEMA_VERSION = "2.2.2-social-adapter-profile-v1"
SOCIAL_ADAPTER_REGISTRY_SCHEMA_VERSION = "2.2.2-social-adapter-registry-v1"
SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION = "2.2.2-social-adapter-config-v1"
SOCIAL_ADAPTER_TEST_SCHEMA_VERSION = "2.2.2-social-adapter-test-v1"
DEFAULT_SUPPORTED_CHANNEL_KINDS = ("direct", "group", "channel")
LAB_COMPLIANCE_CLASSES = {"lab_bridge", "personal_account_bridge"}


def _dedupe(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


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


def _normalize_channel_kinds(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return DEFAULT_SUPPORTED_CHANNEL_KINDS
    raw_items = cast(list[Any], raw_value)
    channels = tuple(
        str(item).strip().lower()
        for item in raw_items
        if str(item).strip().lower() in DEFAULT_SUPPORTED_CHANNEL_KINDS
    )
    return _dedupe(channels) or DEFAULT_SUPPORTED_CHANNEL_KINDS


def _normalize_credential_env_vars(raw_value: Any) -> tuple[str, ...]:
    if isinstance(raw_value, str):
        return (raw_value.strip(),) if raw_value.strip() else ()
    if isinstance(raw_value, list):
        return _dedupe(tuple(str(item) for item in cast(list[Any], raw_value)))
    return ()


def _credentials_present(env: Mapping[str, str], credential_env_vars: tuple[str, ...]) -> bool:
    if not credential_env_vars:
        return True
    return all(bool(env.get(env_var)) for env_var in credential_env_vars)


def _endpoint_target(profile: SocialAdapterProfile) -> tuple[str, int] | None:
    endpoint = profile.webhook_url or profile.endpoint_url or ""
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").strip()
    if not host:
        return None
    scheme = (parsed.scheme or "").strip().lower()
    if parsed.port is not None:
        port = parsed.port
    elif scheme in {"https", "wss"}:
        port = 443
    elif scheme in {"http", "ws"}:
        port = 80
    else:
        port = 443 if profile.transport_kind == "https" else 80
    return host, port


def _tcp_probe(host: str, port: int, timeout_seconds: float) -> str | None:
    try:
        with socket.create_connection((host, port), timeout_seconds):
            return None
    except OSError as exc:
        return str(exc)


def _transport_probe(profile: SocialAdapterProfile, timeout_seconds: float) -> dict[str, Any]:
    target = _endpoint_target(profile)
    if target is None:
        return {
            "status": "skipped",
            "reason": "transport_endpoint_not_configured",
            "ok": False,
        }
    host, port = target
    error = _tcp_probe(host, port, timeout_seconds)
    if error:
        return {
            "status": "error",
            "reason": "transport_unreachable",
            "host": host,
            "port": port,
            "error": error,
            "ok": False,
        }
    return {
        "status": "ready",
        "reason": "transport_reachable",
        "host": host,
        "port": port,
        "ok": True,
    }


@dataclass(frozen=True)
class SocialAdapterProfile:
    name: str
    adapter_kind: str
    enabled: bool
    runtime_host: str = "direct"
    endpoint_url: str | None = None
    webhook_url: str | None = None
    host_url: str | None = None
    credential_env_vars: tuple[str, ...] = ()
    supported_channel_kinds: tuple[str, ...] = DEFAULT_SUPPORTED_CHANNEL_KINDS
    default_channel_policy: str = "direct_and_group"
    mention_policy: str = "optional"
    transport_kind: str = "local"
    share_session_in_group: bool = False
    plugin_id: str | None = None
    plugin_package: str | None = None
    installer_package: str | None = None
    plugin_installed: bool = False
    account_session_ready: bool = False
    compliance_class: str = "deterministic_mock"
    compliance_acknowledged: bool = True
    live_network_allowed: bool = False
    endpoint_configured: bool = False
    credential_configured: bool = True
    schema_version: str = SOCIAL_ADAPTER_PROFILE_SCHEMA_VERSION

    @property
    def compliance_ready(self) -> bool:
        return self.compliance_class not in LAB_COMPLIANCE_CLASSES or self.compliance_acknowledged

    @property
    def ready_for_live_io(self) -> bool:
        if self.transport_kind == "openclaw_gateway":
            return (
                self.enabled
                and self.endpoint_configured
                and self.credential_configured
                and bool(self.plugin_package)
                and self.plugin_installed
                and self.account_session_ready
                and self.compliance_ready
            )
        return (
            self.enabled
            and self.endpoint_configured
            and self.credential_configured
            and self.compliance_ready
        )

    def missing_requirements(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.enabled:
            missing.append("enabled_adapter")
        if not self.endpoint_configured:
            if self.transport_kind == "openclaw_gateway":
                missing.append("host_endpoint_reference")
            else:
                missing.append("endpoint_reference")
        if self.transport_kind == "openclaw_gateway" and not self.plugin_package:
            missing.append("plugin_package_coordinate")
        if self.transport_kind == "openclaw_gateway" and not self.plugin_installed:
            missing.append("plugin_installed_evidence")
        if self.transport_kind == "openclaw_gateway" and not self.account_session_ready:
            missing.append("account_session_ready")
        if not self.endpoint_configured and self.transport_kind != "openclaw_gateway":
            missing.append("endpoint_reference")
        if not self.credential_configured:
            missing.append("credential_reference")
        if not self.compliance_ready:
            missing.append("compliance_acknowledgement")
        return tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "adapter_kind": self.adapter_kind,
            "enabled": self.enabled,
            "runtime_host": self.runtime_host,
            "endpoint_url": self.endpoint_url,
            "webhook_url": self.webhook_url,
            "host_url": self.host_url,
            "endpoint_configured": self.endpoint_configured,
            "credential_env_vars": list(self.credential_env_vars),
            "credential_configured": self.credential_configured,
            "credential_values_masked": ["***" for _ in self.credential_env_vars]
            if self.credential_configured
            else [],
            "supported_channel_kinds": list(self.supported_channel_kinds),
            "default_channel_policy": self.default_channel_policy,
            "mention_policy": self.mention_policy,
            "transport_kind": self.transport_kind,
            "share_session_in_group": self.share_session_in_group,
            "plugin_id": self.plugin_id,
            "plugin_package": self.plugin_package,
            "installer_package": self.installer_package,
            "plugin_installed": self.plugin_installed,
            "account_session_ready": self.account_session_ready,
            "compliance_class": self.compliance_class,
            "compliance_acknowledged": self.compliance_acknowledged,
            "compliance_ready": self.compliance_ready,
            "live_network_allowed": self.live_network_allowed,
            "ready_for_live_io": self.ready_for_live_io,
            "missing_requirements": list(self.missing_requirements()),
        }

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapter_kind": self.adapter_kind,
            "enabled": self.enabled,
            "runtime_host": self.runtime_host,
            "endpoint_url": self.endpoint_url,
            "webhook_url": self.webhook_url,
            "host_url": self.host_url,
            "credential_env_vars": list(self.credential_env_vars),
            "supported_channel_kinds": list(self.supported_channel_kinds),
            "default_channel_policy": self.default_channel_policy,
            "mention_policy": self.mention_policy,
            "transport_kind": self.transport_kind,
            "share_session_in_group": self.share_session_in_group,
            "plugin_id": self.plugin_id,
            "plugin_package": self.plugin_package,
            "installer_package": self.installer_package,
            "plugin_installed": self.plugin_installed,
            "account_session_ready": self.account_session_ready,
            "compliance_class": self.compliance_class,
            "compliance_acknowledged": self.compliance_acknowledged,
            "live_network_allowed": self.live_network_allowed,
        }


@dataclass(frozen=True)
class SocialAdapterRegistry:
    profiles: tuple[SocialAdapterProfile, ...]
    active_adapter: str
    schema_version: str = SOCIAL_ADAPTER_REGISTRY_SCHEMA_VERSION

    def get_profile(self, name: str) -> SocialAdapterProfile | None:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active_adapter": self.active_adapter,
            "profiles": [profile.to_dict() for profile in self.profiles],
            "ready_adapter_names": [
                profile.name for profile in self.profiles if profile.ready_for_live_io
            ],
        }


def default_social_adapter_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "social_adapter_profiles.json"


def load_social_adapter_config(*, config_path: str = "") -> dict[str, Any]:
    resolved_path = Path(config_path) if config_path else default_social_adapter_config_path()
    if not resolved_path.exists():
        return {
            "schema_version": SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION,
            "config_path": str(resolved_path),
            "exists": False,
            "active_adapter": "mock_social",
            "profiles": [],
        }
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("social_adapter_config_invalid_payload")
    payload_dict = cast(dict[str, Any], payload)
    return {
        "schema_version": str(
            payload_dict.get("schema_version") or SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION
        ),
        "config_path": str(resolved_path),
        "exists": True,
        "active_adapter": str(payload_dict.get("active_adapter") or "mock_social"),
        "profiles": list(cast(list[Any], payload_dict.get("profiles") or [])),
    }


def _write_social_adapter_config(payload: dict[str, Any], *, config_path: str = "") -> dict[str, Any]:
    resolved_path = Path(config_path) if config_path else default_social_adapter_config_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    write_payload: dict[str, Any] = {
        "schema_version": SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION,
        "active_adapter": str(payload.get("active_adapter") or "mock_social"),
        "profiles": list(payload.get("profiles") or []),
    }
    resolved_path.write_text(
        json.dumps(write_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        **write_payload,
        "config_path": str(resolved_path),
        "exists": True,
    }


def _default_profiles(env: Mapping[str, str]) -> dict[str, SocialAdapterProfile]:
    return {
        "mock_social": SocialAdapterProfile(
            name="mock_social",
            adapter_kind="mock_social",
            enabled=True,
            endpoint_url="local://mock-social",
            endpoint_configured=True,
            credential_env_vars=(),
            credential_configured=True,
            mention_policy="optional",
            transport_kind="local",
            compliance_class="deterministic_mock",
            compliance_acknowledged=True,
        ),
        "qq_official": SocialAdapterProfile(
            name="qq_official",
            adapter_kind="qq_official",
            enabled=False,
            endpoint_url="https://api.sgroup.qq.com",
            endpoint_configured=True,
            credential_env_vars=("QQ_BOT_TOKEN", "QQ_BOT_SECRET"),
            credential_configured=_credentials_present(
                env,
                ("QQ_BOT_TOKEN", "QQ_BOT_SECRET"),
            ),
            supported_channel_kinds=("direct", "group"),
            default_channel_policy="mention_or_direct",
            mention_policy="mention_or_direct",
            transport_kind="https",
            compliance_class="official_api",
            compliance_acknowledged=True,
        ),
        "onebot_qq": SocialAdapterProfile(
            name="onebot_qq",
            adapter_kind="onebot_qq",
            enabled=False,
            endpoint_url=None,
            endpoint_configured=False,
            credential_env_vars=("ONEBOT_ACCESS_TOKEN",),
            credential_configured=_credentials_present(env, ("ONEBOT_ACCESS_TOKEN",)),
            supported_channel_kinds=("direct", "group"),
            default_channel_policy="lab_opt_in",
            mention_policy="mention_or_direct",
            transport_kind="reverse_websocket",
            share_session_in_group=False,
            compliance_class="lab_bridge",
            compliance_acknowledged=False,
        ),
        "wecom": SocialAdapterProfile(
            name="wecom",
            adapter_kind="wecom",
            enabled=False,
            runtime_host="direct",
            endpoint_url=None,
            endpoint_configured=False,
            credential_env_vars=("WECOM_BOT_TOKEN",),
            credential_configured=_credentials_present(env, ("WECOM_BOT_TOKEN",)),
            supported_channel_kinds=("direct", "group"),
            default_channel_policy="mention_or_direct",
            mention_policy="mention_or_direct",
            transport_kind="websocket",
            share_session_in_group=False,
            compliance_class="official_api",
            compliance_acknowledged=True,
        ),
        "wechat_ilink": SocialAdapterProfile(
            name="wechat_ilink",
            adapter_kind="wechat_ilink",
            enabled=False,
            runtime_host="openclaw",
            endpoint_url=None,
            host_url=None,
            endpoint_configured=False,
            credential_env_vars=("WECHAT_ILINK_TOKEN",),
            credential_configured=_credentials_present(env, ("WECHAT_ILINK_TOKEN",)),
            supported_channel_kinds=("direct", "group"),
            default_channel_policy="lab_opt_in",
            mention_policy="mention_or_direct",
            transport_kind="openclaw_gateway",
            share_session_in_group=False,
            plugin_id="wechat_ilink",
            plugin_package="@tencent/openclaw-weixin",
            installer_package="@tencent-weixin/openclaw-weixin-cli",
            plugin_installed=False,
            account_session_ready=False,
            compliance_class="personal_account_bridge",
            compliance_acknowledged=False,
        ),
        "qq_openclaw": SocialAdapterProfile(
            name="qq_openclaw",
            adapter_kind="qq_openclaw",
            enabled=False,
            runtime_host="openclaw",
            endpoint_url=None,
            host_url=None,
            endpoint_configured=False,
            credential_env_vars=("QQ_OPENCLAW_TOKEN",),
            credential_configured=_credentials_present(env, ("QQ_OPENCLAW_TOKEN",)),
            supported_channel_kinds=("direct", "group"),
            default_channel_policy="lab_opt_in",
            mention_policy="mention_or_direct",
            transport_kind="openclaw_gateway",
            share_session_in_group=False,
            plugin_id="qq_openclaw",
            plugin_package=None,
            installer_package=None,
            plugin_installed=False,
            account_session_ready=False,
            compliance_class="personal_account_bridge",
            compliance_acknowledged=False,
        ),
    }


def _overlay_profile_from_config(
    profile: SocialAdapterProfile,
    config_entry: dict[str, Any],
    *,
    env: Mapping[str, str],
) -> SocialAdapterProfile:
    credential_env_vars = _normalize_credential_env_vars(
        config_entry.get("credential_env_vars")
        if "credential_env_vars" in config_entry
        else list(profile.credential_env_vars)
    )
    endpoint_url = str(config_entry.get("endpoint_url") or profile.endpoint_url or "") or None
    webhook_url = str(config_entry.get("webhook_url") or profile.webhook_url or "") or None
    host_url = str(config_entry.get("host_url") or profile.host_url or "") or None
    return SocialAdapterProfile(
        name=str(config_entry.get("name") or profile.name),
        adapter_kind=str(config_entry.get("adapter_kind") or profile.adapter_kind),
        enabled=_coerce_bool(config_entry.get("enabled"), default=profile.enabled),
        runtime_host=str(config_entry.get("runtime_host") or profile.runtime_host),
        endpoint_url=endpoint_url,
        webhook_url=webhook_url,
        host_url=host_url,
        credential_env_vars=credential_env_vars,
        supported_channel_kinds=_normalize_channel_kinds(
            config_entry.get("supported_channel_kinds")
            if "supported_channel_kinds" in config_entry
            else list(profile.supported_channel_kinds)
        ),
        default_channel_policy=str(
            config_entry.get("default_channel_policy") or profile.default_channel_policy
        ),
        mention_policy=str(config_entry.get("mention_policy") or profile.mention_policy),
        transport_kind=str(config_entry.get("transport_kind") or profile.transport_kind),
        share_session_in_group=_coerce_bool(
            config_entry.get("share_session_in_group"),
            default=profile.share_session_in_group,
        ),
        plugin_id=str(config_entry.get("plugin_id") or profile.plugin_id or "") or None,
        plugin_package=str(
            config_entry.get("plugin_package") or profile.plugin_package or ""
        )
        or None,
        installer_package=str(
            config_entry.get("installer_package") or profile.installer_package or ""
        )
        or None,
        plugin_installed=_coerce_bool(
            config_entry.get("plugin_installed"),
            default=profile.plugin_installed,
        ),
        account_session_ready=_coerce_bool(
            config_entry.get("account_session_ready"),
            default=profile.account_session_ready,
        ),
        compliance_class=str(config_entry.get("compliance_class") or profile.compliance_class),
        compliance_acknowledged=_coerce_bool(
            config_entry.get("compliance_acknowledged"),
            default=profile.compliance_acknowledged,
        ),
        live_network_allowed=_coerce_bool(
            config_entry.get("live_network_allowed"),
            default=profile.live_network_allowed,
        ),
        endpoint_configured=bool(host_url or endpoint_url or webhook_url),
        credential_configured=_credentials_present(env, credential_env_vars),
    )


def social_adapter_registry(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
) -> SocialAdapterRegistry:
    resolved_env = env if env is not None else os.environ
    config_payload = load_social_adapter_config(config_path=config_path)
    profiles_by_name = _default_profiles(resolved_env)
    for raw_entry in cast(list[Any], config_payload.get("profiles") or []):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, Any], raw_entry)
        profile_name = str(entry.get("name") or "")
        if not profile_name:
            continue
        base_profile = profiles_by_name.get(
            profile_name,
            SocialAdapterProfile(
                name=profile_name,
                adapter_kind=str(entry.get("adapter_kind") or profile_name),
                enabled=True,
                endpoint_url=None,
                endpoint_configured=False,
                credential_env_vars=_normalize_credential_env_vars(
                    entry.get("credential_env_vars")
                ),
                credential_configured=False,
                compliance_class=str(entry.get("compliance_class") or "custom"),
                compliance_acknowledged=True,
            ),
        )
        profiles_by_name[profile_name] = _overlay_profile_from_config(
            base_profile,
            entry,
            env=resolved_env,
        )
    return SocialAdapterRegistry(
        profiles=tuple(profiles_by_name.values()),
        active_adapter=str(config_payload.get("active_adapter") or "mock_social"),
    )


def social_adapter_list(
    *,
    env: Mapping[str, str] | None = None,
    config_path: str = "",
) -> dict[str, Any]:
    registry = social_adapter_registry(env=env, config_path=config_path)
    config_payload = load_social_adapter_config(config_path=config_path)
    payload = registry.to_dict()
    payload["command"] = "social-adapter-list"
    payload["config_path"] = str(
        config_payload.get("config_path") or default_social_adapter_config_path()
    )
    payload["config_exists"] = bool(config_payload.get("exists", False))
    payload["config_schema_version"] = str(
        config_payload.get("schema_version") or SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION
    )
    payload["ok"] = True
    return payload


def social_adapter_config_update(
    *,
    adapter_name: str,
    config_path: str = "",
    adapter_kind: str | None = None,
    endpoint_url: str | None = None,
    webhook_url: str | None = None,
    host_url: str | None = None,
    credential_env_vars: list[str] | None = None,
    supported_channel_kinds: list[str] | None = None,
    default_channel_policy: str | None = None,
    mention_policy: str | None = None,
    transport_kind: str | None = None,
    share_session_in_group: bool | None = None,
    runtime_host: str | None = None,
    plugin_id: str | None = None,
    plugin_package: str | None = None,
    installer_package: str | None = None,
    plugin_installed: bool | None = None,
    account_session_ready: bool | None = None,
    compliance_class: str | None = None,
    compliance_acknowledged: bool | None = None,
    live_network_allowed: bool | None = None,
    enabled: bool | None = None,
    active: bool = False,
) -> dict[str, Any]:
    config_payload = load_social_adapter_config(config_path=config_path)
    profiles = [
        cast(dict[str, Any], entry)
        for entry in cast(list[Any], config_payload.get("profiles") or [])
        if isinstance(entry, dict)
    ]
    existing_index: int | None = None
    for index, entry in enumerate(profiles):
        if str(entry.get("name") or "") == adapter_name:
            existing_index = index
            break
    current_entry: dict[str, Any] = (
        profiles[existing_index] if existing_index is not None else {"name": adapter_name}
    )
    updated_entry: dict[str, Any] = dict(current_entry)
    if adapter_kind is not None:
        updated_entry["adapter_kind"] = adapter_kind
    if endpoint_url is not None:
        updated_entry["endpoint_url"] = endpoint_url
    if webhook_url is not None:
        updated_entry["webhook_url"] = webhook_url
    if host_url is not None:
        updated_entry["host_url"] = host_url
    if credential_env_vars is not None:
        updated_entry["credential_env_vars"] = list(_dedupe(tuple(credential_env_vars)))
    if supported_channel_kinds is not None:
        updated_entry["supported_channel_kinds"] = list(
            _normalize_channel_kinds(supported_channel_kinds)
        )
    if default_channel_policy is not None:
        updated_entry["default_channel_policy"] = default_channel_policy
    if mention_policy is not None:
        updated_entry["mention_policy"] = mention_policy
    if transport_kind is not None:
        updated_entry["transport_kind"] = transport_kind
    if share_session_in_group is not None:
        updated_entry["share_session_in_group"] = share_session_in_group
    if runtime_host is not None:
        updated_entry["runtime_host"] = runtime_host
    if plugin_id is not None:
        updated_entry["plugin_id"] = plugin_id
    if plugin_package is not None:
        updated_entry["plugin_package"] = plugin_package
    if installer_package is not None:
        updated_entry["installer_package"] = installer_package
    if plugin_installed is not None:
        updated_entry["plugin_installed"] = plugin_installed
    if account_session_ready is not None:
        updated_entry["account_session_ready"] = account_session_ready
    if compliance_class is not None:
        updated_entry["compliance_class"] = compliance_class
    if compliance_acknowledged is not None:
        updated_entry["compliance_acknowledged"] = compliance_acknowledged
    if live_network_allowed is not None:
        updated_entry["live_network_allowed"] = live_network_allowed
    if enabled is not None:
        updated_entry["enabled"] = enabled
    if existing_index is None:
        profiles.append(updated_entry)
    else:
        profiles[existing_index] = updated_entry
    active_adapter = adapter_name if active else str(config_payload.get("active_adapter") or "mock_social")
    written = _write_social_adapter_config(
        {
            "active_adapter": active_adapter,
            "profiles": profiles,
        },
        config_path=config_path,
    )
    return {
        "schema_version": SOCIAL_ADAPTER_CONFIG_SCHEMA_VERSION,
        "command": "social-adapter-config",
        "config_path": str(written.get("config_path") or default_social_adapter_config_path()),
        "updated_adapter": adapter_name,
        "config": written,
        "social_adapter_registry": social_adapter_list(config_path=config_path),
        "ok": True,
    }


def _adapter_for_kind(adapter_kind: str) -> Any:
    if adapter_kind == "qq_official":
        return QQOfficialSocialAdapter()
    if adapter_kind == "onebot_qq":
        return OneBotQQSocialAdapter()
    if adapter_kind == "wecom":
        return WeComSocialAdapter()
    if adapter_kind == "wechat_ilink":
        return WeChatILinkSocialAdapter()
    if adapter_kind == "qq_openclaw":
        return QQOpenClawSocialAdapter()
    return MockSocialAdapter()


def _sample_envelope(
    profile: SocialAdapterProfile,
    *,
    sample_scenario: str,
) -> SocialMessageEnvelope:
    if profile.adapter_kind == "qq_official":
        if sample_scenario == "direct":
            payload = qq_official_direct_message_sample()
        elif sample_scenario == "group_no_mention":
            payload = qq_official_group_message_no_mention_sample()
        else:
            payload = qq_official_group_message_sample()
        return QQOfficialSocialAdapter().envelope_from_event(payload)
    if profile.adapter_kind == "onebot_qq":
        if sample_scenario == "direct":
            payload = onebot_direct_message_sample()
        elif sample_scenario == "group_no_mention":
            payload = onebot_group_message_no_mention_sample()
        else:
            payload = onebot_group_message_sample()
        payload["share_session_in_group"] = profile.share_session_in_group
        return OneBotQQSocialAdapter().envelope_from_event(payload)
    if profile.adapter_kind == "wecom":
        if sample_scenario == "direct":
            payload = wecom_direct_message_sample()
        elif sample_scenario == "group_no_mention":
            payload = wecom_group_message_no_mention_sample()
        else:
            payload = wecom_group_message_sample()
        return WeComSocialAdapter().envelope_from_event(payload)
    if profile.adapter_kind == "wechat_ilink":
        if sample_scenario == "direct":
            payload = wechat_ilink_direct_message_sample()
        elif sample_scenario == "group_no_mention":
            payload = wechat_ilink_group_message_no_mention_sample()
        else:
            payload = wechat_ilink_group_message_sample()
        payload["share_session_in_group"] = profile.share_session_in_group
        return WeChatILinkSocialAdapter().envelope_from_event(payload)
    if profile.adapter_kind == "qq_openclaw":
        if sample_scenario == "direct":
            payload = qq_openclaw_direct_message_sample()
        elif sample_scenario == "group_no_mention":
            payload = qq_openclaw_group_message_no_mention_sample()
        else:
            payload = qq_openclaw_group_message_sample()
        payload["share_session_in_group"] = profile.share_session_in_group
        return QQOpenClawSocialAdapter().envelope_from_event(payload)
    return MockSocialAdapter().bind_principal(
        adapter_kind=profile.adapter_kind,
        channel_id="mock-social-001",
        channel_kind="group",
        external_user_id="alice",
        text="please check current status",
        received_at="2026-05-11T12:00:00Z",
    )


def _build_test_result(
    profile: SocialAdapterProfile,
    *,
    probe_transport: bool,
    sample_scenario: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    adapter = _adapter_for_kind(profile.adapter_kind)
    envelope = _sample_envelope(profile, sample_scenario=sample_scenario)
    event = adapter.to_perception_event(envelope)
    delivery = cast(
        SocialDeliveryRecord,
        adapter.deliver_affective_response(
            envelope,
            {"speaker": "affective", "text": "I can help with that."},
        ),
    )
    status = "ready" if profile.ready_for_live_io else "skipped"
    reason = (
        "social_adapter_ready"
        if profile.ready_for_live_io
        else "social_adapter_requirements_missing"
    )
    transport_probe: dict[str, Any] = {
        "status": "not_requested",
        "reason": "transport_probe_not_requested",
        "ok": True,
    }
    transport_probe_allowed = (
        probe_transport
        and profile.live_network_allowed
        and profile.compliance_ready
        and profile.endpoint_configured
    )
    if probe_transport and not transport_probe_allowed:
        transport_probe = {
            "status": "skipped",
            "reason": "transport_probe_blocked_by_policy",
            "ok": False,
        }
    elif probe_transport:
        transport_probe = _transport_probe(profile, timeout_seconds)
    closure_gates: dict[str, bool] = {
        "readiness_reported": True,
        "social_ingress_normalized": event.get("source_kind") == "social",
        "principal_bound": bool(envelope.principal_id),
        "affective_delivery_recorded": delivery.speaker == "affective"
        and delivery.delivery_status == "delivered",
        "network_execution_policy_respected": (
            not probe_transport
            or transport_probe_allowed
        ),
        "secrets_not_persisted": "credential_values" not in profile.to_dict(),
        "transport_probe_policy_respected": not probe_transport or transport_probe_allowed,
        "transport_probe_recorded": not probe_transport
        or str(transport_probe.get("status") or "") in {"ready", "error"},
    }
    return {
        "adapter": profile.name,
        "adapter_kind": profile.adapter_kind,
        "status": status,
        "reason": reason,
        "sample_scenario": sample_scenario,
        "profile": profile.to_dict(),
        "social_envelope": envelope.to_dict(),
        "perception_event": event,
        "delivery_record": delivery.to_dict(),
        "probe_requested": probe_transport,
        "transport_probe": transport_probe,
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()) and bool(transport_probe.get("ok", False)),
    }


def social_adapter_test(
    *,
    adapter_name: str = "",
    env: Mapping[str, str] | None = None,
    config_path: str = "",
    probe_transport: bool = False,
    sample_scenario: str = "group",
    timeout_seconds: float = 1.5,
) -> dict[str, Any]:
    if sample_scenario not in SOCIAL_ADAPTER_SAMPLE_SCENARIOS:
        raise ValueError("unknown_social_adapter_sample_scenario")
    registry = social_adapter_registry(env=env, config_path=config_path)
    selected_profiles: list[SocialAdapterProfile]
    if adapter_name:
        profile = registry.get_profile(adapter_name)
        if profile is None:
            raise ValueError("unknown_social_adapter_profile")
        selected_profiles = [profile]
    else:
        selected_profiles = list(registry.profiles)
    results = [
        _build_test_result(
            profile,
            probe_transport=probe_transport,
            sample_scenario=sample_scenario,
            timeout_seconds=timeout_seconds,
        )
        for profile in selected_profiles
    ]
    ready_count = sum(1 for result in results if result.get("status") == "ready")
    deterministic_ready_count = sum(
        1
        for result in results
        if bool(cast(dict[str, Any], result.get("closure_gates") or {}).get("social_ingress_normalized"))
        and bool(cast(dict[str, Any], result.get("closure_gates") or {}).get("principal_bound"))
        and bool(cast(dict[str, Any], result.get("closure_gates") or {}).get("affective_delivery_recorded"))
    )
    transport_probe_status_counts: dict[str, int] = {}
    for result in results:
        probe = cast(dict[str, Any], result.get("transport_probe") or {})
        probe_status = str(probe.get("status") or "unknown")
        transport_probe_status_counts[probe_status] = transport_probe_status_counts.get(probe_status, 0) + 1
    return {
        "schema_version": SOCIAL_ADAPTER_TEST_SCHEMA_VERSION,
        "command": "social-adapter-test",
        "status": "ready" if ready_count else "skipped",
        "reason": "social_adapter_test_completed",
        "config_path": str(load_social_adapter_config(config_path=config_path).get("config_path") or default_social_adapter_config_path()),
        "adapter_filter": adapter_name,
        "sample_scenario": sample_scenario,
        "ready_count": ready_count,
        "deterministic_ready_count": deterministic_ready_count,
        "tested_count": len(results),
        "probe_requested": probe_transport,
        "executes_live_network": probe_transport,
        "probe_timeout_seconds": timeout_seconds,
        "evidence_summary": {
            "sample_scenario": sample_scenario,
            "deterministic_normalization": {
                "ready_count": deterministic_ready_count,
                "tested_count": len(results),
            },
            "transport_reachability": {
                "probe_requested": probe_transport,
                "status_counts": transport_probe_status_counts,
            },
        },
        "results": results,
        "ok": all(bool(result.get("ok")) for result in results),
    }
