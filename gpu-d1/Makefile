NVCC ?= /usr/bin/nvcc
HOSTCXX ?= /usr/bin/g++-12
CUDAFLAGS = -O3 -std=c++17 -arch=sm_75 -ccbin $(HOSTCXX) -Xcompiler -fopenmp -lineinfo
.PHONY: all test clean
all: build/bench
build/bench: src/bench.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) $< -o $@
test: build/bench
	./build/bench --fixture fixtures/fixture.bin --selftest
clean:
	rm -f build/bench

build/learn.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_map.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DFULL_MAP_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_seen.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DSEEN_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DFRONTIER_RING_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring_walls.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring_memory_walls.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_MEMORY_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring12.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DFRONTIER_RING12_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_frontier_memory.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DFRONTIER_MEMORY_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_frontier_memory_walls.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_MEMORY_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring_walls_40.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DLEARN_ENEMIES=40 -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_frontier_memory_walls_40.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DLEARN_ENEMIES=40 -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_MEMORY_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_explore_ring_walls_multi.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DLEARN_ENEMIES=40 -DMULTI_MAP -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_WALLS_OBS -shared -Xcompiler -fPIC $< -o $@

build/test_ring_walls: src/test_wall_observations.cu src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_WALLS_OBS $< -o $@

build/test_frontier_walls: src/test_wall_observations.cu src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_MEMORY_WALLS_OBS $< -o $@

build/test_ring_memory_walls: src/test_wall_observations.cu src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS -DFRONTIER_RING_MEMORY_WALLS_OBS $< -o $@

.PHONY: test-wall-observations
test-wall-observations: build/test_ring_walls build/test_frontier_walls build/test_ring_memory_walls build/learn_sleep_explore_ring_walls.so build/learn_sleep_explore_frontier_memory_walls.so build/learn_sleep_explore_ring_memory_walls.so
	./build/test_ring_walls
	./build/test_frontier_walls
	./build/test_ring_memory_walls
	.venv/bin/python scripts/test_wall_observations.py

build/learn_v2.so: src/learn_v2.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -shared -Xcompiler -fPIC $< -o $@

build/learn_sleep_spatial.so: src/learn.cu src/sim.h
	mkdir -p build
	$(NVCC) $(CUDAFLAGS) -DSLEEP_ON -DEXPLORE_REWARD -DSPATIAL_MAP_OBS -shared -Xcompiler -fPIC $< -o $@
