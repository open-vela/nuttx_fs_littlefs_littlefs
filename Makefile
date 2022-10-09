ifdef BUILDDIR
# make sure BUILDDIR ends with a slash
override BUILDDIR := $(BUILDDIR)/
# bit of a hack, but we want to make sure BUILDDIR directory structure
# is correct before any commands
$(if $(findstring n,$(MAKEFLAGS)),, $(shell mkdir -p \
	$(BUILDDIR) \
	$(BUILDDIR)bd \
	$(BUILDDIR)runners \
	$(BUILDDIR)tests \
	$(BUILDDIR)benches))
endif

# overridable target/src/tools/flags/etc
ifneq ($(wildcard test.c main.c),)
TARGET ?= $(BUILDDIR)lfs
else
TARGET ?= $(BUILDDIR)lfs.a
endif


CC       ?= gcc
AR       ?= ar
SIZE     ?= size
CTAGS    ?= ctags
NM       ?= nm
OBJDUMP  ?= objdump
VALGRIND ?= valgrind
GDB		 ?= gdb
PERF	 ?= perf

SRC  ?= $(filter-out $(wildcard *.*.c),$(wildcard *.c))
OBJ  := $(SRC:%.c=$(BUILDDIR)%.o)
DEP  := $(SRC:%.c=$(BUILDDIR)%.d)
ASM  := $(SRC:%.c=$(BUILDDIR)%.s)
CI   := $(SRC:%.c=$(BUILDDIR)%.ci)
GCDA := $(SRC:%.c=$(BUILDDIR)%.t.a.gcda)

TESTS ?= $(wildcard tests/*.toml)
TEST_SRC ?= $(SRC) \
		$(filter-out $(wildcard bd/*.*.c),$(wildcard bd/*.c)) \
		runners/test_runner.c
TEST_RUNNER ?= $(BUILDDIR)runners/test_runner
TEST_TC   := $(TESTS:%.toml=$(BUILDDIR)%.t.c) \
		$(TEST_SRC:%.c=$(BUILDDIR)%.t.c)
TEST_TAC  := $(TEST_TC:%.t.c=%.t.a.c)
TEST_OBJ  := $(TEST_TAC:%.t.a.c=%.t.a.o)
TEST_DEP  := $(TEST_TAC:%.t.a.c=%.t.a.d)
TEST_CI	  := $(TEST_TAC:%.t.a.c=%.t.a.ci)
TEST_GCNO := $(TEST_TAC:%.t.a.c=%.t.a.gcno)
TEST_GCDA := $(TEST_TAC:%.t.a.c=%.t.a.gcda)
TEST_PERF := $(TEST_RUNNER:%=%.perf)

BENCHES ?= $(wildcard benches/*.toml)
BENCH_SRC ?= $(SRC) \
		$(filter-out $(wildcard bd/*.*.c),$(wildcard bd/*.c)) \
		runners/bench_runner.c
BENCH_RUNNER ?= $(BUILDDIR)runners/bench_runner
BENCH_BC   := $(BENCHES:%.toml=$(BUILDDIR)%.b.c) \
		$(BENCH_SRC:%.c=$(BUILDDIR)%.b.c)
BENCH_BAC  := $(BENCH_BC:%.b.c=%.b.a.c)
BENCH_OBJ  := $(BENCH_BAC:%.b.a.c=%.b.a.o)
BENCH_DEP  := $(BENCH_BAC:%.b.a.c=%.b.a.d)
BENCH_CI   := $(BENCH_BAC:%.b.a.c=%.b.a.ci)
BENCH_GCNO := $(BENCH_BAC:%.b.a.c=%.b.a.gcno)
BENCH_GCDA := $(BENCH_BAC:%.b.a.c=%.b.a.gcda)
BENCH_PERF := $(BENCH_RUNNER:%=%.perf)

ifdef DEBUG
override CFLAGS += -O0
else
override CFLAGS += -Os
endif
ifdef TRACE
override CFLAGS += -DLFS_YES_TRACE
endif
override CFLAGS += -g3
override CFLAGS += -I.
override CFLAGS += -std=c99 -Wall -pedantic
override CFLAGS += -Wextra -Wshadow -Wjump-misses-init -Wundef
override CFLAGS += -ftrack-macro-expansion=0
ifdef YES_COV
override CFLAGS += --coverage
endif
ifdef YES_PERF
override CFLAGS += -fno-omit-frame-pointer
endif

ifdef VERBOSE
override CODEFLAGS   += -v
override DATAFLAGS   += -v
override STACKFLAGS  += -v
override STRUCTFLAGS += -v
override COVFLAGS    += -v
override PERFFLAGS   += -v
endif
ifneq ($(NM),nm)
override CODEFLAGS += --nm-tool="$(NM)"
override DATAFLAGS += --nm-tool="$(NM)"
endif
ifneq ($(OBJDUMP),objdump)
override CODEFLAGS   += --objdump-tool="$(OBJDUMP)"
override DATAFLAGS   += --objdump-tool="$(OBJDUMP)"
override STRUCTFLAGS += --objdump-tool="$(OBJDUMP)"
override PERFFLAGS   += --objdump-tool="$(OBJDUMP)"
endif
ifneq ($(PERF),perf)
override PERFFLAGS += --perf-tool="$(PERF)"
endif

override TESTFLAGS  += -b
override BENCHFLAGS += -b
# forward -j flag
override TESTFLAGS  += $(filter -j%,$(MAKEFLAGS))
override BENCHFLAGS += $(filter -j%,$(MAKEFLAGS))
ifdef YES_PERF
override TESTFLAGS += --perf=$(TEST_PERF)
endif
ifndef NO_PERF
override BENCHFLAGS += --perf=$(BENCH_PERF)
endif
ifdef VERBOSE
override TESTFLAGS   += -v
override TESTCFLAGS  += -v
override BENCHFLAGS  += -v
override BENCHCFLAGS += -v
endif
ifdef EXEC
override TESTFLAGS  += --exec="$(EXEC)"
override BENCHFLAGS += --exec="$(EXEC)"
endif
ifneq ($(GDB),gdb)
override TESTFLAGS  += --gdb-tool="$(GDB)"
override BENCHFLAGS += --gdb-tool="$(GDB)"
endif
ifneq ($(VALGRIND),valgrind)
override TESTFLAGS  += --valgrind-tool="$(VALGRIND)"
override BENCHFLAGS += --valgrind-tool="$(VALGRIND)"
endif
ifneq ($(PERF),perf)
override TESTFLAGS  += --perf-tool="$(PERF)"
override BENCHFLAGS += --perf-tool="$(PERF)"
endif


# commands
.PHONY: all build
all build: $(TARGET)

.PHONY: asm
asm: $(ASM)

.PHONY: size
size: $(OBJ)
	$(SIZE) -t $^

.PHONY: tags
tags:
	$(CTAGS) --totals --c-types=+p $(shell find -H -name '*.h') $(SRC)

.PHONY: test-runner build-test
ifndef NO_COV
test-runner build-test: override CFLAGS+=--coverage
endif
ifdef YES_PERF
bench-runner build-bench: override CFLAGS+=-fno-omit-frame-pointer
endif
test-runner build-test: $(TEST_RUNNER)
ifndef NO_COV
	rm -f $(TEST_GCDA)
endif
ifdef YES_PERF
	rm -f $(TEST_PERF)
endif

.PHONY: test
test: test-runner
	./scripts/test.py $(TEST_RUNNER) $(TESTFLAGS)

.PHONY: test-list
test-list: test-runner
	./scripts/test.py $(TEST_RUNNER) $(TESTFLAGS) -l

.PHONY: bench-runner build-bench
ifdef YES_COV
bench-runner build-bench: override CFLAGS+=--coverage
endif
ifndef NO_PERF
bench-runner build-bench: override CFLAGS+=-fno-omit-frame-pointer
endif
bench-runner build-bench: $(BENCH_RUNNER)
ifdef YES_COV 
	rm -f $(BENCH_GCDA)
endif
ifndef NO_PERF
	rm -f $(BENCH_PERF)
endif

.PHONY: bench
bench: bench-runner
	./scripts/bench.py $(BENCH_RUNNER) $(BENCHFLAGS)

.PHONY: bench-list
bench-list: bench-runner
	./scripts/bench.py $(BENCH_RUNNER) $(BENCHFLAGS) -l

.PHONY: code
code: $(OBJ)
	./scripts/code.py $^ -Ssize $(CODEFLAGS)

.PHONY: data
data: $(OBJ)
	./scripts/data.py $^ -Ssize $(DATAFLAGS)

.PHONY: stack
stack: $(CI)
	./scripts/stack.py $^ -Slimit -Sframe $(STACKFLAGS)

.PHONY: struct
struct: $(OBJ)
	./scripts/struct_.py $^ -Ssize $(STRUCTFLAGS)

.PHONY: cov
cov: $(GCDA)
	$(strip ./scripts/cov.py \
		$^ $(patsubst %,-F%,$(SRC)) \
		-slines -sbranches \
		$(COVFLAGS))

.PHONY: perf
perf: $(BENCH_PERF)
	$(strip ./scripts/perf.py \
		$^ $(patsubst %,-F%,$(SRC)) \
		-Scycles \
		$(PERFFLAGS))

.PHONY: summary sizes
summary sizes: $(BUILDDIR)lfs.csv
	$(strip ./scripts/summary.py -Y $^ \
		-fcode=code_size \
		-fdata=data_size \
		-fstack=stack_limit \
		-fstruct=struct_size \
		--max=stack \
		$(SUMMARYFLAGS))


# rules
-include $(DEP)
-include $(TEST_DEP)
.SUFFIXES:
.SECONDARY:

$(BUILDDIR)lfs: $(OBJ)
	$(CC) $(CFLAGS) $^ $(LFLAGS) -o $@

$(BUILDDIR)lfs.a: $(OBJ)
	$(AR) rcs $@ $^

$(BUILDDIR)lfs.code.csv: $(OBJ)
	./scripts/code.py $^ -q $(CODEFLAGS) -o $@

$(BUILDDIR)lfs.data.csv: $(OBJ)
	./scripts/data.py $^ -q $(CODEFLAGS) -o $@

$(BUILDDIR)lfs.stack.csv: $(CI)
	./scripts/stack.py $^ -q $(CODEFLAGS) -o $@

$(BUILDDIR)lfs.struct.csv: $(OBJ)
	./scripts/struct_.py $^ -q $(CODEFLAGS) -o $@

$(BUILDDIR)lfs.cov.csv: $(GCDA)
	./scripts/cov.py $^ $(patsubst %,-F%,$(SRC)) -q $(COVFLAGS) -o $@

$(BUILDDIR)lfs.perf.csv: $(BENCH_PERF)
	./scripts/perf.py $^ $(patsubst %,-F%,$(SRC)) -q $(PERFFLAGS) -o $@

$(BUILDDIR)lfs.csv: \
		$(BUILDDIR)lfs.code.csv \
		$(BUILDDIR)lfs.data.csv \
		$(BUILDDIR)lfs.stack.csv \
		$(BUILDDIR)lfs.struct.csv
	./scripts/summary.py $^ -q $(SUMMARYFLAGS) -o $@

$(BUILDDIR)runners/test_runner: $(TEST_OBJ)
	$(CC) $(CFLAGS) $^ $(LFLAGS) -o $@

$(BUILDDIR)runners/bench_runner: $(BENCH_OBJ)
	$(CC) $(CFLAGS) $^ $(LFLAGS) -o $@

# our main build rule generates .o, .d, and .ci files, the latter
# used for stack analysis
$(BUILDDIR)%.o $(BUILDDIR)%.ci: %.c
	$(CC) -c -MMD -fcallgraph-info=su $(CFLAGS) $< -o $(BUILDDIR)$*.o

$(BUILDDIR)%.s: %.c
	$(CC) -S $(CFLAGS) $< -o $@

$(BUILDDIR)%.a.c: %.c
	./scripts/prettyasserts.py -p LFS_ASSERT $< -o $@

$(BUILDDIR)%.a.c: $(BUILDDIR)%.c
	./scripts/prettyasserts.py -p LFS_ASSERT $< -o $@

$(BUILDDIR)%.t.c: %.toml
	./scripts/test.py -c $< $(TESTCFLAGS) -o $@

$(BUILDDIR)%.t.c: %.c $(TESTS)
	./scripts/test.py -c $(TESTS) -s $< $(TESTCFLAGS) -o $@

$(BUILDDIR)%.b.c: %.toml
	./scripts/bench.py -c $< $(BENCHCFLAGS) -o $@

$(BUILDDIR)%.b.c: %.c $(BENCHES)
	./scripts/bench.py -c $(BENCHES) -s $< $(BENCHCFLAGS) -o $@

# clean everything
.PHONY: clean
clean:
	rm -f $(BUILDDIR)lfs
	rm -f $(BUILDDIR)lfs.a
	$(strip rm -f \
		$(BUILDDIR)lfs.csv \
		$(BUILDDIR)lfs.code.csv \
		$(BUILDDIR)lfs.data.csv \
		$(BUILDDIR)lfs.stack.csv \
		$(BUILDDIR)lfs.struct.csv \
		$(BUILDDIR)lfs.cov.csv \
		$(BUILDDIR)lfs.perf.csv)
	rm -f $(OBJ)
	rm -f $(DEP)
	rm -f $(ASM)
	rm -f $(CI)
	rm -f $(TEST_RUNNER)
	rm -f $(TEST_TC)
	rm -f $(TEST_TAC)
	rm -f $(TEST_OBJ)
	rm -f $(TEST_DEP)
	rm -f $(TEST_CI)
	rm -f $(TEST_GCNO)
	rm -f $(TEST_GCDA)
	rm -f $(TEST_PERF)
	rm -f $(BENCH_RUNNER)
	rm -f $(BENCH_BC)
	rm -f $(BENCH_BAC)
	rm -f $(BENCH_OBJ)
	rm -f $(BENCH_DEP)
	rm -f $(BENCH_CI)
	rm -f $(BENCH_GCNO)
	rm -f $(BENCH_GCDA)
	rm -f $(BENCH_PERF)
