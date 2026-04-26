# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(neurolink_unit)

zephyr_include_directories(
  include
  include/runtime
)

target_sources(app PRIVATE
  src/main.c
  src/neuro_unit.c
  src/neuro_unit_dispatch.c
  src/neuro_unit_diag.c
  src/neuro_unit_response.c
  src/neuro_unit_update_service.c
  src/neuro_artifact_store.c
  src/neuro_app_command_registry.c
  src/neuro_app_callback_bridge.c
  src/neuro_state_registry.c
  src/neuro_unit_app_command.c
  src/neuro_update_manager.c
  src/neuro_recovery_seed_store.c
  src/neuro_lease_manager.c
  src/neuro_network_manager.c
  src/neuro_request_envelope.c
  src/neuro_request_policy.c
  src/neuro_protocol_codec.c
  src/neuro_unit_event.c
  src/zenoh/neuro_unit_zenoh.c
  src/neuro_unit_llext_exports.c
  src/runtime/app_runtime_exception.c
  src/runtime/app_runtime.c
  src/runtime/app_runtime_cmd.c
  src/shell/neuro_unit_shell.c
  src/shell/neuro_unit_shell_lifecycle.c
  src/shell/neuro_unit_shell_network.c
  src/shell/neuro_unit_shell_storage.c
  src/shell/neuro_unit_shell_zenoh.c
  src/port/neuro_unit_port_contract.c
  src/port/neuro_unit_port_generic.c
  src/port/neuro_unit_port_generic_dnesp32s3b.c
)

target_include_directories(app PRIVATE
  include/port
)

if(CONFIG_NEUROLINK_ZENOH_PICO_DEBUG)
  target_compile_definitions(app PRIVATE
    ZENOH_LOG_DEBUG
    ZENOH_DEBUG=${CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL}
  )
endif()
