from __future__ import annotations

import neuro_protocol as protocol


RELEASE_TARGET = "1.2.2"


def release_label(suffix: str) -> str:
    return f"release-{RELEASE_TARGET}-{suffix}"


def default_app_echo() -> str:
    return f"neuro_unit_app-{RELEASE_TARGET}-cbor-v2"


WORKFLOW_PLANS = {
    "setup-linux": {
        "category": "setup",
        "description": "construct and validate a Linux NeuroLink build/test/control host",
        "commands": [
            "sudo apt-get update",
            "sudo apt-get install -y git python3 python3-venv python3-pip cmake ninja-build gperf ccache dfu-util device-tree-compiler wget curl xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev libmagic1 clang-format perl usbutils",
            "python3 -m venv .venv",
            "source .venv/bin/activate && python3 -m pip install --upgrade pip wheel west",
            "source .venv/bin/activate && python3 -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt",
            "source .venv/bin/activate && west update",
            "cat zephyr/SDK_VERSION",
            "export ZEPHYR_SDK_INSTALL_DIR=${HOME}/zephyr-sdk-$(cat zephyr/SDK_VERSION)",
            "source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-tests",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight",
        ],
        "artifacts": [
            ".venv",
            "build/neurolink_unit",
            "build/neurolink_unit_ut_check",
            "build/neurolink_unit_app",
        ],
    },
    "setup-windows": {
        "category": "setup",
        "description": "construct and validate a Windows NeuroLink build/test/control host",
        "commands": [
            "winget install --id Git.Git -e --source winget",
            "winget install --id Python.Python.3.12 -e --source winget",
            "winget install --id Kitware.CMake -e --source winget",
            "winget install --id Ninja-build.Ninja -e --source winget",
            "winget install --id Microsoft.PowerShell -e --source winget",
            "py -3 -m venv .venv",
            ". .venv/Scripts/Activate.ps1",
            "python -m pip install --upgrade pip wheel west",
            "python -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt",
            "west update",
            "Get-Content zephyr/SDK_VERSION",
            "$env:ZEPHYR_SDK_INSTALL_DIR = \"$HOME/zephyr-sdk-$(Get-Content zephyr/SDK_VERSION)\"",
            ". applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Strict",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight",
        ],
        "artifacts": [
            ".venv",
            "build/neurolink_unit",
            "build/neurolink_unit_app",
            "applocation/NeuroLink/smoke-evidence",
        ],
    },
    "discover-host": {
        "category": "discovery",
        "description": "read local NeuroLink workspace and CLI capability state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "status": "ready",
                "release_target": RELEASE_TARGET,
                "agent_skill": {
                    "name": "neuro-cli",
                    "source_of_truth": "canonical",
                },
                "protocol": {
                    "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
                },
            },
            "failure_statuses": ["workspace_not_found", "handler_failed"],
        },
    },
    "discover-router": {
        "category": "discovery",
        "description": "classify Linux Zenoh router listener state without app control",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --install-missing-cli-deps --output json",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "status": "ready",
                "ready": True,
                "router": {
                    "listening": True,
                    "port": 7447,
                    "auto_started": False,
                },
            },
            "failure_statuses": [
                "router_not_listening",
                "router_failed_to_start",
                "no_reply_board_not_attached",
                "no_reply_board_unreachable",
            ],
        },
    },
    "discover-serial": {
        "category": "discovery",
        "description": "classify Linux USB serial visibility before hardware evidence",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --require-serial --output json",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "serial": {
                    "present": True,
                    "devices": ["/dev/ttyACM0"],
                },
            },
            "failure_statuses": ["serial_device_missing"],
        },
    },
    "serial-discover": {
        "category": "discovery",
        "description": "list host serial ports available for Unit UART recovery",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial list",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "status": "ok",
                "devices": [{"device": "/dev/ttyACM0", "source": "pyserial"}],
            },
            "failure_statuses": ["serial_device_missing"],
        },
    },
    "serial-zenoh-config": {
        "category": "configuration",
        "description": "configure the Unit Zenoh connect endpoint through UART shell",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh show --port /dev/ttyACM0",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh set tcp/<host-ip>:7447 --port /dev/ttyACM0",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 5 query device",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence/serial-diag"],
        "json_contract": {
            "success": {
                "ok": True,
                "status": "ok",
                "endpoint": "tcp/<host-ip>:7447",
                "verified": True,
            },
            "failure_statuses": [
                "serial_dependency_missing",
                "serial_device_missing",
                "serial_open_failed",
                "serial_timeout",
                "shell_error",
                "endpoint_verify_failed",
                "no_reply",
            ],
        },
    },
    "serial-zenoh-recover": {
        "category": "configuration",
        "description": "recover Unit connectivity when router endpoint drift causes no_reply",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-router",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan serial-discover",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan serial-zenoh-config",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 5 query device",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence/serial-diag"],
        "json_contract": {
            "success": {
                "serial_config": {"status": "ok"},
                "device_query": {"status": "ok", "node_id": "unit-01"},
            },
            "failure_statuses": [
                "router_not_listening",
                "serial_device_missing",
                "endpoint_verify_failed",
                "no_reply_board_unreachable",
                "no_reply",
            ],
        },
    },
    "discover-device": {
        "category": "discovery",
        "description": "query Unit reachability and device state through the router",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query device",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "session_ready": True,
                        },
                    }
                ],
            },
            "failure_statuses": [
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "discover-apps": {
        "category": "discovery",
        "description": "query deployed Unit apps and runtime/update state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query apps",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "app_count": 0,
                            "running_count": 0,
                            "suspended_count": 0,
                            "apps": [],
                        },
                    }
                ],
            },
            "failure_statuses": [
                "app_not_running",
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "discover-leases": {
        "category": "discovery",
        "description": "query active Unit leases before protected control",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "leases": [],
                        },
                    }
                ],
            },
            "failure_statuses": [
                "lease_conflict",
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "control-health": {
        "category": "control",
        "description": "run read-only health queries before protected control",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "device": {"status": "ok", "node_id": "unit-01"},
                "apps": {"status": "ok", "apps": []},
                "leases": {"status": "ok", "leases": []},
            },
            "failure_statuses": [
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "control-deploy": {
        "category": "control",
        "description": "protected deploy prepare/verify/activate sequence with lease cleanup",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource update/app/neuro_unit_app/activate --lease-id "
            f"{release_label('deploy')}-lease --ttl-ms 120000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy prepare --app-id neuro_unit_app --file build/neurolink_unit_app/neuro_unit_app.llext",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy verify --app-id neuro_unit_app",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy activate --app-id neuro_unit_app --lease-id "
            f"{release_label('deploy')}-lease --start-args release={RELEASE_TARGET}",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('deploy')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [
            "build/neurolink_unit_app/neuro_unit_app.llext",
            "applocation/NeuroLink/smoke-evidence",
        ],
        "json_contract": {
            "success": {
                "lease_acquire": {"status": "ok", "lease_id": f"{release_label('deploy')}-lease"},
                "deploy_prepare": {"status": "ok", "app_id": "neuro_unit_app"},
                "deploy_verify": {"status": "ok", "app_id": "neuro_unit_app"},
                "deploy_activate": {"status": "ok", "app_id": "neuro_unit_app"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "lease_conflict",
                "artifact_missing",
                "artifact_stale",
                "prepare_failed",
                "verify_failed",
                "activate_failed",
                "payload.status:error",
            ],
        },
    },
    "control-app-invoke": {
        "category": "control",
        "description": "protected app command invocation with app-control lease cleanup",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource app/neuro_unit_app/control --lease-id "
            f"{release_label('app-control')}-lease --ttl-ms 60000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_unit_app --lease-id "
            f"{release_label('app-control')}-lease --command invoke --args-json '{{\"echo\": \"{default_app_echo()}\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('app-control')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "lease_acquire": {"status": "ok", "resource": "app/neuro_unit_app/control"},
                "app_invoke": {"status": "ok", "app_id": "neuro_unit_app"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "app_not_running",
                "lease_conflict",
                "invalid_input",
                "handler_failed",
                "payload.status:error",
            ],
        },
    },
    "control-callback": {
        "category": "control",
        "description": "protected callback configuration and same-session callback smoke",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource app/neuro_unit_app/control --lease-id "
            f"{release_label('callback')}-lease --ttl-ms 60000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app callback-config --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --mode on --trigger-every 1 --event-name callback",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --command invoke --args-json '{{\"echo\": \"{default_app_echo()}\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 5 --max-events 1",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app callback-config --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --mode off --event-name callback",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('callback')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence"],
        "json_contract": {
            "success": {
                "callback_config": {"status": "ok", "callback_enabled": True},
                "app_invoke": {"status": "ok", "app_id": "neuro_unit_app"},
                "event": {"keyexpr": "neuro/unit-01/event/app/neuro_unit_app/callback"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "callback_timeout",
                "handler_failed",
                "lease_conflict",
                "app_not_running",
                "payload.status:error",
            ],
        },
    },
    "control-monitor": {
        "category": "control",
        "description": "monitor app-scoped events with explicit optional handler audit",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 10 --max-events 1",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 10 --max-events 1 --handler-python applocation/NeuroLink/neuro_cli/skill/assets/callback_handler.py --handler-timeout 5",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "subscription": {"status": "ok", "app_id": "neuro_unit_app"},
                "handler_audit": {
                    "runner": "explicit",
                    "returncode": 0,
                    "max_output_bytes": 16384,
                },
            },
            "failure_statuses": [
                "callback_timeout",
                "handler_failed",
                "handler_timeout",
                "handler_output_truncated",
            ],
        },
    },
    "control-cleanup": {
        "category": "control",
        "description": "release known workflow leases and confirm clean lease state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('deploy')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('app-control')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('callback')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {"leases": []},
            "failure_statuses": [
                "lease_not_found",
                "session_open_failed",
                "no_reply",
                "payload.status:error",
            ],
        },
    },
    "app-build": {
        "category": "app_development",
        "description": "build the sample LLEXT app artifact",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit_app/neuro_unit_app.llext"],
    },
    "demo-build": {
        "category": "app_development",
        "description": "build the first release-1.2.0 demo artifact through the catalog-backed wrapper",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink_demo.sh --demo neuro_demo_net_event --no-c-style-check",
            "bash applocation/NeuroLink/scripts/build_neurolink_demo.sh --demo neuro_demo_net_event --print-artifact-path --no-c-style-check",
        ],
        "artifacts": [
            "build/neurolink_unit/llext/neuro_demo_net_event.llext",
            "applocation/NeuroLink/subprojects/demo_catalog.json",
        ],
    },
    "unit-build": {
        "category": "board_operation",
        "description": "build Neuro Unit firmware",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit/zephyr/zephyr.elf"],
    },
    "unit-edk": {
        "category": "app_development",
        "description": "build the Unit EDK headers and LLEXT support output",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit/zephyr/llext-edk"],
    },
    "unit-tests": {
        "category": "verification",
        "description": "run native_sim Neuro Unit tests",
        "commands": [
            "west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run",
        ],
        "artifacts": ["build/neurolink_unit_ut_check"],
    },
    "cli-tests": {
        "category": "verification",
        "description": "run Neuro CLI regression tests",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q",
        ],
        "artifacts": [],
    },
    "memory-evidence": {
        "category": "verification",
        "description": "collect build-time Neuro Unit memory evidence",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py "
            f"--run-build --no-c-style-check --label {release_label('memory-evidence')}",
        ],
        "artifacts": ["applocation/NeuroLink/memory-evidence"],
    },
    "llext-lifecycle": {
        "category": "app_development",
        "description": "exercise explicit LLEXT install, runtime unload, and artifact delete semantics",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-deploy",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app stop --app-id neuro_unit_app --lease-id <lease>",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app unload --app-id neuro_unit_app --lease-id <lease>",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app delete --app-id neuro_unit_app --lease-id <lease>",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query apps",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence"],
        "json_contract": {
            "success": {
                "deploy_activate": {"status": "ok"},
                "runtime_unload": {"status": "ok"},
                "artifact_delete": {"status": "ok"},
            },
            "failure_statuses": [
                "lease_conflict",
                "app_not_running",
                "artifact_missing",
                "delete_active_app_rejected",
                "payload.status:error",
            ],
        },
    },
    "memory-layout-dump": {
        "category": "verification",
        "description": "dump board static memory layout from Unit build artifacts",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py "
            "memory layout-dump "
            "--build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence "
            f"--label {release_label('static-layout-baseline')}",
        ],
        "artifacts": ["applocation/NeuroLink/memory-evidence"],
        "json_contract": {
            "success": {
                "section_totals": {"dram0": 377188},
                "config": {"CONFIG_LLEXT_HEAP_SIZE": 64},
                "sections": [{"name": ".dram0.bss", "size": 0}],
            },
            "failure_statuses": [
                "build_dir_missing",
                "zephyr_stat_missing",
                "config_missing",
                "parse_failed",
            ],
        },
    },
    "llext-memory-config": {
        "category": "app_development",
        "description": "plan LLEXT memory configuration candidates from static layout evidence",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-layout-dump",
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --overlay-config applocation/NeuroLink/neuro_unit/overlays/<llext-memory-candidate>.conf --no-c-style-check",
            "/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py memory layout-dump --build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence --label release-1.1.9-llext-memory-candidate",
            "/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py memory config-plan --baseline-json applocation/NeuroLink/memory-evidence/release-1.1.8-closure.json --candidate-json applocation/NeuroLink/memory-evidence/release-1.1.9-llext-memory-candidate.json",
        ],
        "artifacts": ["applocation/NeuroLink/memory-evidence"],
        "json_contract": {
            "success": {
                "baseline_layout": {"status": "ok"},
                "candidate_layout": {"status": "ok"},
                "promotion_allowed": False,
            },
            "failure_statuses": [
                "baseline_layout_missing",
                "candidate_layout_missing",
                "loaded_extensions_present",
                "candidate_build_failed",
                "runtime_heap_dynamic_unsafe",
                "memory_regression",
                "parse_failed",
            ],
        },
    },
    "preflight": {
        "category": "board_operation",
        "description": "run Linux host and board preflight checks",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text",
        ],
        "artifacts": [],
    },
    "smoke": {
        "category": "board_operation",
        "description": "run the Linux NeuroLink smoke path",
        "commands": [
            "bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence"],
    },
    "callback-smoke": {
        "category": "board_operation",
        "description": "run the app callback smoke path through the CLI wrapper",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py "
            "app-callback-smoke --app-id neuro_unit_app "
            f"--expected-app-echo {default_app_echo()} --trigger-every 1 "
            "--invoke-count 2",
        ],
        "artifacts": [],
    },
    "demo-net-event-smoke": {
        "category": "board_operation",
        "description": "review the first network event demo smoke path without executing it",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan demo-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases",
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --artifact-file build/neurolink_unit/llext/neuro_demo_net_event.llext --auto-start-router --require-serial --install-missing-cli-deps --output text",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource update/app/neuro_demo_net_event/activate --lease-id "
            f"{release_label('demo-net-event-deploy')}-lease --ttl-ms 120000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy prepare --app-id neuro_demo_net_event --file build/neurolink_unit/llext/neuro_demo_net_event.llext",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy verify --app-id neuro_demo_net_event",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy activate --app-id neuro_demo_net_event --lease-id "
            f"{release_label('demo-net-event-deploy')}-lease --start-args mode=demo,profile=event_bridge",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource app/neuro_demo_net_event/control --lease-id "
            f"{release_label('demo-net-event-control')}-lease --ttl-ms 60000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_demo_net_event --lease-id "
            f"{release_label('demo-net-event-control')}-lease --command invoke --args-json '{{\"action\": \"capability\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_demo_net_event --lease-id "
            f"{release_label('demo-net-event-control')}-lease --command invoke --args-json '{{\"action\": \"publish\", \"detail\": \"workflow-plan\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_demo_net_event --duration 10 --max-events 1",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('demo-net-event-control')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('demo-net-event-deploy')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [
            "build/neurolink_unit/llext/neuro_demo_net_event.llext",
            "applocation/NeuroLink/smoke-evidence",
        ],
        "json_contract": {
            "success": {
                "deploy_activate": {"status": "ok", "app_id": "neuro_demo_net_event"},
                "capability_invoke": {"status": "ok", "app_id": "neuro_demo_net_event"},
                "publish_invoke": {"status": "ok", "app_id": "neuro_demo_net_event"},
                "event": {"keyexpr": "neuro/unit-01/event/app/neuro_demo_net_event/demo_event"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "serial_device_missing",
                "no_reply_board_unreachable",
                "lease_conflict",
                "app_not_running",
                "not_implemented",
                "payload.status:error",
            ],
        },
    },
    "release-closure": {
        "category": "verification",
        "description": "review the release closure gate sequence without executing it",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py "
            f"--run-build --no-c-style-check --label {release_label('closure')}",
            "/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py",
            "/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q",
            "bash applocation/NeuroLink/tests/scripts/run_all_tests.sh",
            "git -C applocation/NeuroLink diff --check",
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text",
            "bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5",
        ],
        "artifacts": [
            "applocation/NeuroLink/memory-evidence",
            "applocation/NeuroLink/smoke-evidence",
        ],
    },
}


WORKFLOW_METADATA_DEFAULTS = {
    "host_support": ["linux", "wsl"],
    "requires_hardware": False,
    "requires_serial": False,
    "requires_router": False,
    "requires_network": True,
    "destructive": False,
    "preconditions": [
        "west workspace contains applocation/NeuroLink",
        "NeuroLink Python environment is active or wrapper Python is explicit",
    ],
    "expected_success": [
        "process exit code is 0",
        "no JSON payload field reports ok=false or status=error",
    ],
    "failure_statuses": [
        {
            "status": "process_nonzero",
            "next_action": "inspect stderr and command-specific logs",
        },
        {
            "status": "json_parse_failed",
            "next_action": "treat stdout contract as broken for Agent automation",
        },
    ],
    "cleanup": [],
}


WORKFLOW_PLAN_METADATA = {
    "setup-linux": {
        "host_support": ["linux"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": True,
        "destructive": False,
        "preconditions": [
            "network access is available",
            "operator approves sudo package installation commands before running them",
            "workspace root contains zephyr and applocation/NeuroLink",
            "Zephyr SDK version from zephyr/SDK_VERSION is installed or will be installed before build commands",
        ],
        "expected_success": [
            "required system commands are available",
            "repository-local .venv exists and has west plus Neuro CLI dependencies",
            "ZEPHYR_SDK_INSTALL_DIR points at the SDK version recorded in zephyr/SDK_VERSION",
            "setup_neurolink_env.sh strict validation exits 0",
            "system init and system capabilities return ok=true JSON",
        ],
        "failure_statuses": [
            {
                "status": "missing_required_command",
                "next_action": "install the named system package and rerun setup validation",
            },
            {
                "status": "zephyr_sdk_missing",
                "next_action": "install Zephyr SDK or export ZEPHYR_SDK_INSTALL_DIR",
            },
            {
                "status": "python_dependency_missing",
                "next_action": "run pip install for Zephyr and Neuro CLI requirements",
            },
        ],
        "cleanup": [],
    },
    "setup-windows": {
        "host_support": ["windows", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": True,
        "destructive": False,
        "preconditions": [
            "network access is available",
            "operator approves winget or manual installer prompts before running them",
            "PowerShell execution policy allows activating the local virtual environment",
            "workspace root contains zephyr and applocation/NeuroLink",
            "Zephyr SDK version from zephyr/SDK_VERSION is installed or will be installed before build commands",
        ],
        "expected_success": [
            "required commands are available from PowerShell",
            "repository-local .venv exists and has west plus Neuro CLI dependencies",
            "ZEPHYR_SDK_INSTALL_DIR points at the SDK version recorded in zephyr/SDK_VERSION",
            "setup_neurolink_env.ps1 strict validation exits 0",
            "system init and system capabilities return ok=true JSON",
        ],
        "failure_statuses": [
            {
                "status": "missing_required_command",
                "next_action": "install the named Windows tool and rerun setup validation",
            },
            {
                "status": "execution_policy_blocked",
                "next_action": "approve a process-scoped PowerShell execution policy change before activating .venv",
            },
            {
                "status": "zephyr_sdk_missing",
                "next_action": "install Zephyr SDK or set ZEPHYR_SDK_INSTALL_DIR",
            },
            {
                "status": "wsl_usb_required",
                "next_action": "switch to WSL USB/IP attach flow for Linux-canonical hardware evidence",
            },
        ],
        "cleanup": [],
    },
    "discover-host": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "workspace root contains zephyr and applocation/NeuroLink",
            "Neuro CLI wrapper can import the local source tree",
        ],
        "expected_success": [
            "system init reports ok=true and status=ready",
            "system capabilities reports protocol and release metadata",
            "agent_skill paths identify the canonical skill package",
        ],
        "failure_statuses": [
            {
                "status": "workspace_not_found",
                "next_action": "run from the west workspace root or pass an explicit project path in the Agent context",
            },
            {
                "status": "handler_failed",
                "next_action": "inspect CLI traceback-safe JSON error and Python environment",
            },
        ],
        "cleanup": [],
    },
    "discover-router": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "Linux shell can run the preflight helper",
            "operator approves auto-starting a local zenoh router if none is listening",
        ],
        "expected_success": [
            "preflight JSON includes router.listening=true",
            "router.port is 7447 unless overridden by the operator",
            "Unit no-reply is reported separately from router listener state",
        ],
        "failure_statuses": [
            {
                "status": "router_not_listening",
                "next_action": "start the router or rerun with --auto-start-router after operator approval",
            },
            {
                "status": "router_failed_to_start",
                "next_action": "inspect zenohd install/log output and port binding conflicts",
            },
            {
                "status": "no_reply_board_unreachable",
                "next_action": "router is reachable locally; check board network readiness or UART logs",
            },
        ],
        "cleanup": ["stop only router processes started by this workflow"],
    },
    "discover-serial": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "target Unit USB cable is attached",
            "Linux user has permission to read /dev/ttyACM* or /dev/ttyUSB*",
        ],
        "expected_success": [
            "preflight JSON includes serial.present=true",
            "serial.devices lists at least one /dev/ttyACM* or /dev/ttyUSB* path",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "check USB cable, dialout permissions, or WSL USB attach state",
            }
        ],
        "cleanup": [],
    },
    "serial-discover": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "target Unit USB serial device is attached",
            "pyserial is installed in the Neuro CLI Python environment",
        ],
        "expected_success": [
            "serial list returns ok=true",
            "devices contains at least one candidate Unit UART path",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "check USB cable, host permissions, WSL USB attach, or pass --port explicitly",
            },
            {
                "status": "serial_dependency_missing",
                "next_action": "install applocation/NeuroLink/neuro_cli/requirements.txt",
            },
        ],
        "cleanup": [],
    },
    "serial-zenoh-config": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": False,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "serial-discover finds the target Unit UART port or operator passes --port",
            "target router endpoint is known, for example tcp/<host-ip>:7447",
            "Unit firmware includes app zenoh_connect_show/set/clear shell commands",
        ],
        "expected_success": [
            "serial zenoh set returns ok=true",
            "reply endpoint matches the requested locator",
            "follow-up query device succeeds after reconnect when router is reachable",
        ],
        "failure_statuses": [
            {
                "status": "serial_dependency_missing",
                "next_action": "install applocation/NeuroLink/neuro_cli/requirements.txt",
            },
            {
                "status": "serial_device_missing",
                "next_action": "attach the Unit UART device or pass --port explicitly",
            },
            {
                "status": "serial_open_failed",
                "next_action": "check permissions or close other programs using the UART port",
            },
            {
                "status": "serial_timeout",
                "next_action": "confirm shell is enabled and baud rate matches the Unit UART",
            },
            {
                "status": "endpoint_verify_failed",
                "next_action": "inspect shell output and rerun serial zenoh show before retrying",
            },
        ],
        "cleanup": [],
    },
    "serial-zenoh-recover": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-router reports the expected host router listener",
            "serial-discover can reach the Unit UART shell",
            "Zenoh no_reply is suspected to be endpoint drift rather than app failure",
        ],
        "expected_success": [
            "serial endpoint config returns ok=true",
            "query device reaches status=ok after reconnect retries",
        ],
        "failure_statuses": [
            {
                "status": "serial_open_failed",
                "next_action": "recover serial access before endpoint recovery",
            },
            {
                "status": "no_reply",
                "next_action": "inspect board network readiness and UART logs after endpoint config",
            },
            {
                "status": "router_not_listening",
                "next_action": "start zenohd before changing the Unit endpoint",
            },
        ],
        "cleanup": [],
    },
    "discover-device": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "Zenoh router is listening on the expected endpoint",
            "target Unit has joined the router network",
        ],
        "expected_success": [
            "query device returns ok=true",
            "reply payload reports status=ok and node_id for the target Unit",
            "session_ready and network_state are captured when provided by firmware",
        ],
        "failure_statuses": [
            {
                "status": "session_open_failed",
                "next_action": "check router availability and Zenoh configuration",
            },
            {
                "status": "no_reply",
                "next_action": "run discover-router and discover-serial to split router, USB, and board-network causes",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "discover-apps": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "Unit query apps route is supported by firmware",
        ],
        "expected_success": [
            "query apps returns ok=true",
            "reply payload includes app_count, running_count, suspended_count, and apps list",
            "app_not_running is reported as a state classification before app invoke/control",
        ],
        "failure_statuses": [
            {
                "status": "app_not_running",
                "next_action": "deploy or activate the app only through protected control workflows",
            },
            {
                "status": "no_reply",
                "next_action": "rerun discover-device before app-specific diagnosis",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "discover-leases": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "Unit query leases route is supported by firmware",
        ],
        "expected_success": [
            "query leases returns ok=true",
            "reply payload includes leases list",
            "empty leases list is required before starting release smoke/control closure",
        ],
        "failure_statuses": [
            {
                "status": "lease_conflict",
                "next_action": "release owned stale leases or wait for TTL expiry before protected control",
            },
            {
                "status": "no_reply",
                "next_action": "rerun discover-device before lease-specific diagnosis",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "control-health": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps and discover-leases are available for the target Unit",
        ],
        "expected_success": [
            "query device, query apps, and query leases all return ok=true",
            "nested reply payloads report status=ok",
            "lease list is empty or only contains leases intentionally owned by the operator",
        ],
        "failure_statuses": [
            {
                "status": "no_reply",
                "next_action": "rerun discover-router and discover-device before control",
            },
            {
                "status": "payload.status:error",
                "next_action": "stop control flow and inspect nested Unit status_code/message",
            },
        ],
        "cleanup": [],
    },
    "control-deploy": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-leases shows no conflicting update/app lease",
            "fresh LLEXT artifact exists at build/neurolink_unit/llext/neuro_unit_app.llext",
        ],
        "expected_success": [
            "lease acquire returns status=ok for update/app/neuro_unit_app/activate",
            "deploy prepare, verify, and activate return status=ok in order",
            "post-activate query apps reports neuro_unit_app active or running",
            "cleanup releases the deploy lease and query leases is empty",
        ],
        "failure_statuses": [
            {
                "status": "lease_conflict",
                "next_action": "release owned stale update lease or wait for TTL expiry",
            },
            {
                "status": "artifact_missing",
                "next_action": "run workflow plan app-build and rebuild the LLEXT artifact",
            },
            {
                "status": "payload.status:error",
                "next_action": "stop deploy flow and preserve prepare/verify/activate payload evidence",
            },
        ],
        "cleanup": [
            f"release lease {release_label('deploy')}-lease",
            "query leases until update/app/neuro_unit_app/activate lease is absent",
        ],
    },
    "control-app-invoke": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps reports neuro_unit_app running or ready for invoke",
            "discover-leases shows no conflicting app control lease",
        ],
        "expected_success": [
            "lease acquire returns status=ok for app/neuro_unit_app/control",
            "app invoke returns status=ok and app_id=neuro_unit_app",
            "cleanup releases the app control lease and query leases is empty",
        ],
        "failure_statuses": [
            {
                "status": "app_not_running",
                "next_action": "run control-deploy before app invoke",
            },
            {
                "status": "lease_conflict",
                "next_action": "release owned stale app control lease or wait for TTL expiry",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as command failure",
            },
        ],
        "cleanup": [
            f"release lease {release_label('app-control')}-lease",
            "query leases until app/neuro_unit_app/control lease is absent",
        ],
    },
    "control-callback": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps reports neuro_unit_app running",
            "callback handler execution is explicitly enabled if a handler is used",
        ],
        "expected_success": [
            "callback config on returns status=ok",
            "app invoke returns status=ok and publishes the callback event",
            "monitor app-events captures a fresh app-scoped callback event",
            "callback config off and lease release complete during cleanup",
        ],
        "failure_statuses": [
            {
                "status": "callback_timeout",
                "next_action": "check app callback config, event name, and app-scoped subscription path",
            },
            {
                "status": "handler_failed",
                "next_action": "inspect explicit handler audit stdout/stderr/returncode",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as callback control failure",
            },
        ],
        "cleanup": [
            "turn callback mode off when the workflow enabled it",
            f"release lease {release_label('callback')}-lease",
            "undeclare event subscribers and query leases",
        ],
    },
    "control-monitor": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "operator explicitly approves any local handler command or handler Python file",
        ],
        "expected_success": [
            "monitor app-events subscribes to the app-scoped callback key expression",
            "optional handler audit reports runner, cwd, timeout, returncode, stdout, and stderr",
            "event collection stops on max-events or duration without leaking non-JSON stdout",
        ],
        "failure_statuses": [
            {
                "status": "handler_failed",
                "next_action": "inspect handler audit fields and do not retry blindly",
            },
            {
                "status": "callback_timeout",
                "next_action": "verify callback is enabled and event name matches monitor path",
            },
        ],
        "cleanup": ["undeclare subscriber and stop local handler execution"],
    },
    "control-cleanup": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "one or more known release workflow lease ids may still be active",
            "target Unit is reachable enough to query leases",
        ],
        "expected_success": [
            "owned workflow leases are released or already absent",
            "final query leases returns ok=true with an empty leases list for closure",
        ],
        "failure_statuses": [
            {
                "status": "lease_not_found",
                "next_action": "treat as already-clean for the named workflow lease and continue final query leases",
            },
            {
                "status": "payload.status:error",
                "next_action": "inspect lease payload and avoid claiming cleanup closure",
            },
        ],
        "cleanup": ["repeat query leases after each release attempt"],
    },
    "app-build": {
        "preconditions": [
            "Unit EDK headers and LLEXT support output are available or buildable",
            "Zephyr toolchain and west workspace are configured",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit_app/neuro_unit_app.llext exists",
        ],
    },
    "demo-build": {
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "subprojects/demo_catalog.json contains the selected demo app id",
            "build_neurolink_demo.sh is available and the Zephyr build toolchain is configured",
            "the selected demo source directory has a valid CMakeLists.txt and toolchain.cmake",
        ],
        "expected_success": [
            "catalog-backed wrapper exits 0",
            "wrapper reports demo_app_id=neuro_demo_net_event and artifact_file for the staged output",
            "build/neurolink_unit/llext/neuro_demo_net_event.llext exists after the build",
        ],
        "failure_statuses": [
            {
                "status": "demo_not_defined",
                "next_action": "choose an app id that exists in subprojects/demo_catalog.json",
            },
            {
                "status": "app source dir not found",
                "next_action": "restore the selected demo subproject or correct the catalog source_dir",
            },
            {
                "status": "artifact missing or empty",
                "next_action": "inspect the selected demo build log and rebuild after fixing the compile failure",
            },
        ],
        "cleanup": [],
    },
    "unit-build": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "west workspace modules are initialized",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit/zephyr/zephyr.elf exists",
        ],
    },
    "unit-edk": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "Unit firmware build configuration can generate LLEXT EDK output",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit/zephyr/llext-edk exists",
        ],
    },
    "unit-tests": {
        "preconditions": [
            "native_sim toolchain support is available",
            "west workspace modules are initialized",
        ],
        "expected_success": [
            "west build exits 0",
            "native_sim Unit tests report success",
        ],
    },
    "cli-tests": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_network": False,
        "preconditions": [
            "Neuro CLI Python test dependencies are installed",
            "zenoh import is available or tests install a fake module where expected",
        ],
        "expected_success": [
            "pytest exits 0",
            "CLI JSON and wrapper contract regressions pass",
        ],
    },
    "memory-evidence": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "memory evidence collector can run a Unit build",
        ],
        "expected_success": [
            "collector exits 0",
            "memory evidence JSON and summary artifacts are written",
        ],
    },
    "llext-lifecycle": {
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "control-deploy can activate the sample LLEXT app",
            "operator owns required app/update leases before destructive lifecycle changes",
        ],
        "expected_success": [
            "runtime unload and artifact delete report distinct status fields",
            "query apps confirms no stale running app after lifecycle cleanup",
        ],
        "failure_statuses": [
            {
                "status": "delete_active_app_rejected",
                "next_action": "stop and unload the running app before deleting its artifact",
            },
            {
                "status": "artifact_missing",
                "next_action": "treat as already deleted only when query apps/artifacts confirms clean state",
            },
        ],
    },
    "memory-layout-dump": {
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "build/neurolink_unit contains Zephyr build artifacts",
            "memory evidence collector can parse .config and zephyr.stat",
        ],
        "expected_success": [
            "static layout JSON and summary artifacts are written",
            "section totals include dram0, iram0, flash, and ext_ram when available",
        ],
        "failure_statuses": [
            {
                "status": "build_dir_missing",
                "next_action": "run workflow plan unit-build before dumping static layout",
            },
            {
                "status": "zephyr_stat_missing",
                "next_action": "inspect the Unit build output and rebuild if needed",
            },
        ],
    },
    "llext-memory-config": {
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "memory-layout-dump baseline exists",
            "candidate overlay changes only LLEXT memory/staging configuration",
        ],
        "expected_success": [
            "candidate build evidence is comparable with static layout baseline",
            "promotion remains blocked until hardware runtime evidence is collected",
        ],
        "failure_statuses": [
            {
                "status": "runtime_heap_dynamic_unsafe",
                "next_action": "keep the change as a build-time overlay candidate",
            },
            {
                "status": "memory_regression",
                "next_action": "reject the candidate or collect a narrower isolated overlay",
            },
        ],
    },
    "preflight": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "preconditions": [
            "target Unit USB serial device is visible to the host",
            "Zenoh router can be started or is already reachable",
            "Neuro CLI Python dependencies are installed or installable",
        ],
        "expected_success": [
            "preflight exits 0",
            "serial, router, and Unit query checks pass",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "check USB cable, permissions, or WSL USB attach",
            },
            {
                "status": "no_reply_board_unreachable",
                "next_action": "check board network readiness and UART logs",
            },
        ],
        "cleanup": ["stop only router processes started by this workflow"],
    },
    "smoke": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "preflight passes for the target Unit",
            "fresh Unit app artifact is buildable",
        ],
        "expected_success": [
            "smoke script exits 0",
            "fresh smoke evidence is written",
            "post-smoke lease query is empty",
        ],
        "cleanup": ["release any acquired app/update leases"],
    },
    "callback-smoke": {
        "requires_hardware": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "target Unit is reachable through query device",
            "neuro_unit_app is deployed and activated",
            "callback handler execution is explicitly enabled if a handler is used",
        ],
        "expected_success": [
            "wrapper exits 0",
            "callback events are fresh and app-scoped",
            "nested Unit reply payloads do not report status=error",
        ],
        "failure_statuses": [
            {
                "status": "handler_failed",
                "next_action": "inspect audited handler stderr/stdout and return code",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit reply as command failure",
            },
        ],
        "cleanup": ["release callback smoke lease when acquired"],
    },
    "demo-net-event-smoke": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "workflow plan demo-build succeeds and build/neurolink_unit/llext/neuro_demo_net_event.llext is fresh",
            "preflight passes for the target Unit when artifact_file points at neuro_demo_net_event.llext",
            "discover-leases shows no conflicting update or app-control lease for neuro_demo_net_event",
        ],
        "expected_success": [
            "deploy prepare, verify, and activate return status=ok for neuro_demo_net_event",
            "capability and publish invoke commands return status=ok without nested payload.status:error",
            "monitor app-events captures a fresh demo_event for neuro_demo_net_event",
            "cleanup releases both demo leases and query leases is empty",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "restore Unit USB serial visibility before claiming hardware readiness",
            },
            {
                "status": "no_reply_board_unreachable",
                "next_action": "check board network readiness, UART logs, and router reachability before deploy",
            },
            {
                "status": "lease_conflict",
                "next_action": "release the stale deploy/app-control lease or wait for TTL expiry before retrying",
            },
            {
                "status": "not_implemented",
                "next_action": "treat this as unsupported runtime capability and collect capability reply evidence instead of smoke closure",
            },
            {
                "status": "payload.status:error",
                "next_action": "stop the demo smoke flow and preserve the failing Unit reply payload",
            },
        ],
        "cleanup": [
            f"release lease {release_label('demo-net-event-control')}-lease",
            f"release lease {release_label('demo-net-event-deploy')}-lease",
            "query leases until both demo lease ids are absent",
        ],
    },
    "release-closure": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "local CLI, wrapper, script, build, and skill gates are green",
            "hardware preflight and smoke can run against the target Unit",
            "release identity has not been promoted prematurely",
        ],
        "expected_success": [
            "all listed gates exit 0",
            "memory and smoke evidence are fresh",
            "release identity remains controlled until final promotion slice",
        ],
        "cleanup": ["release any acquired leases", "capture final evidence paths"],
    },
}

