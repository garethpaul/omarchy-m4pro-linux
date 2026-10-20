# SPDX-License-Identifier: MIT
CC ?= cc
CFLAGS ?= -O2 -g
WARNINGS = -std=c11 -Wall -Wextra -Wconversion -Werror -Wshadow -Wpedantic
BUILD ?= build
.PHONY: all test clean
all: $(BUILD)/g16s-inspect $(BUILD)/g16s-main-inspect
$(BUILD)/g16s-main-inspect: g16s-main-inspect.c g16s_main.h g16s_abi.h
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(WARNINGS) $< -o $@
$(BUILD)/g16s-inspect: g16s-inspect.c g16s_abi.h
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(WARNINGS) $< -o $@
$(BUILD)/test_g16s_abi: test_g16s_abi.c test-fixture.h g16s_abi.h
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(WARNINGS) $< -o $@
$(BUILD)/test_g16s_main: test_g16s_main.c test-fixture.h g16s_main.h g16s_abi.h
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(WARNINGS) $< -o $@
test: $(BUILD)/test_g16s_abi $(BUILD)/test_g16s_main
	./$(BUILD)/test_g16s_abi
	./$(BUILD)/test_g16s_main
clean:
	rm -rf $(BUILD)
