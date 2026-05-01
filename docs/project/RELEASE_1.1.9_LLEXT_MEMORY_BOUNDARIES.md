# Release 1.1.9 LLEXT Memory Boundary Notes

## Purpose

This note records the first `EXEC-196` safety boundary for LLEXT memory
configuration candidates. It is intentionally conservative: build-time static
layout evidence can admit a candidate for runtime testing, but cannot promote a
dynamic memory policy by itself.

## Current Default

The release-1.1.8 baseline uses Zephyr's static LLEXT heap path:

- `CONFIG_LLEXT_HEAP_DYNAMIC=n`
- `CONFIG_LLEXT_HEAP_SIZE=64`
- `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`
- `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
- `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`

This remains the release-1.1.9 default until hardware evidence proves a safer
candidate.

## Dynamic Heap Boundary

Zephyr's `CONFIG_LLEXT_HEAP_DYNAMIC` disables the static LLEXT heap allocation.
When it is enabled, the application must call `llext_heap_init()` before loading
extensions. If the heap is not initialized, LLEXT modules will not load. The
heap can only be released with `llext_heap_uninit()` after all extensions are
unloaded; Zephyr reports busy state while extensions remain loaded.

NeuroLink currently does not initialize a dynamic LLEXT heap at runtime. For
that reason, `CONFIG_LLEXT_HEAP_DYNAMIC=y` is a build-evidence candidate only.
It must not be promoted from static layout evidence alone.

## Candidate Gate

Every LLEXT memory candidate must pass these gates in order:

1. Build with an isolated overlay.
2. Dump static layout evidence with `memory layout-dump`.
3. Compare against the baseline with `memory config-plan`.
4. Reject internal `dram0` or `iram0` growth unless the candidate is explicitly
   accepted as a runtime-only experiment.
5. Keep `promotion_allowed=false` until runtime evidence proves update heap,
   app-runtime heap, and staging allocation behavior.
6. For `CONFIG_LLEXT_HEAP_DYNAMIC=y`, require an explicit runtime heap
   initialization implementation and hardware smoke before any promotion.

## Reproducible Candidate Overlays

- `neuro_unit/overlays/llext_dynamic_heap_candidate.conf` enables Zephyr's
  dynamic LLEXT heap mode and preserves conservative staging defaults. It is a
  build/static-layout candidate only until runtime heap initialization is added.
- `neuro_unit/overlays/external_staging_candidate.conf` remains an opt-in
  staging-policy candidate and is not safe for default promotion based on prior
  hardware evidence.
