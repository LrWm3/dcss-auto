#pragma once
#include <stdint.h>
struct GpuNativeStats {
    uint64_t turns, actions, attacks, blocks, dodges, damage, deaths, resets, moves, repairs,
        stalls, move_turns, combat_turns;
};
// Hooks are inert outside the explicitly invoked reference benchmark.
extern bool gpu_d1_active;
extern GpuNativeStats gpu_d1_stats;
struct gpu_d1_terminal {};
void gpu_native_clear_queue();
