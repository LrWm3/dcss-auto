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
