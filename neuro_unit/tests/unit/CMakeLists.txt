# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(neuro_unit_module_tests)

target_sources(app PRIVATE
  ../../src/neuro_unit_dispatch.c
  ../../src/neuro_unit_diag.c
  ../../src/neuro_unit_response.c
  ../../src/neuro_unit_app_command.c
  ../../src/neuro_unit_update_service.c
  ../../src/neuro_artifact_store.c
  ../../src/neuro_app_command_registry.c
  ../../src/neuro_app_callback_bridge.c
  ../../src/neuro_lease_manager.c
  ../../src/neuro_state_registry.c
  ../../src/neuro_update_manager.c
  ../../src/neuro_recovery_seed_store.c
  ../../src/neuro_request_envelope.c
  ../../src/neuro_request_policy.c
  ../../src/neuro_protocol_codec.c
  ../../src/neuro_unit_event.c
  ../../src/neuro_network_manager.c
  ../../src/zenoh/neuro_unit_zenoh_config.c
  ../../src/runtime/app_runtime_cmd.c
  ../../src/runtime/app_runtime_exception.c
  ../../src/runtime/app_runtime_elf_staging.c
  ../../src/port/neuro_unit_port_contract.c
  ../../src/port/neuro_unit_port_generic.c
  src/protocol/test_neuro_protocol.c
  src/protocol/test_neuro_protocol_codec.c
  src/lifecycle/test_neuro_update_manager.c
  src/lifecycle/test_neuro_lease_manager.c
  src/lifecycle/test_neuro_unit_dispatch.c
  src/lifecycle/test_neuro_unit_diag.c
  src/lifecycle/test_neuro_unit_response.c
  src/lifecycle/test_neuro_unit_zenoh_config.c
  src/lifecycle/test_neuro_state_registry.c
  src/lifecycle/test_neuro_unit_update_service.c
  src/recovery/test_neuro_recovery_seed_store.c
  src/recovery/test_neuro_recovery_reconcile.c
  src/app/test_neuro_app_command_registry.c
  src/app/test_neuro_app_callback_bridge.c
  src/app/test_neuro_unit_app_command.c
  src/app/test_neuro_unit_app_api.c
  src/app/test_neuro_unit_event.c
  src/request/test_neuro_request_envelope.c
  src/request/test_neuro_request_policy.c
  src/port/test_neuro_unit_port_fs_contract.c
  src/port/test_neuro_network_manager_port.c
  src/runtime/test_app_runtime_cmd_capability.c
  src/runtime/test_app_runtime_elf_staging.c
)

target_sources_ifdef(CONFIG_NEUROLINK_PROTOCOL_CBOR app PRIVATE
  ../../src/neuro_protocol_codec_cbor.c
)

target_include_directories(app PRIVATE
  ../../include
  ../../include/runtime
  ../../include/port
)

target_compile_definitions(app PRIVATE
  NEURO_UNIT_OPAQUE_ZENOH_TYPES=1
)

