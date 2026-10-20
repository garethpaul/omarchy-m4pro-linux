// SPDX-License-Identifier: GPL-3.0-only
// Adapted from ADevWithAnIdea/agx-re's iohello_compute.m, Copyright (c) 2026 Cody Ho.
// Exact upstream revision and source digest are recorded in upstream.json.
// Public Metal APIs and our own XOR/store shaders; no vendor shader bytes.

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <dispatch/dispatch.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <sys/utsname.h>
#include <time.h>

enum { XOR_WORDS = 16, STORE_WORDS = 256 };
static const uint32_t XOR_MARKER = 0x6145a55aU;

static uint64_t monotonic_ns(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return 0;
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static void emit(NSString *event, NSDictionary *fields) {
    NSMutableDictionary *record = [@{@"schema": @1, @"event": event,
                                     @"monotonic_ns": @(monotonic_ns())} mutableCopy];
    [record addEntriesFromDictionary:fields];
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (!data) { fputs("JSON encoding failed\n", stderr); exit(70); }
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
}

static int fail(NSString *reason, int code) {
    emit(@"ERROR", @{@"reason": reason});
    return code;
}

static BOOL gate(NSString *event, const char *expected, unsigned index) {
    emit(event, @{@"expect_stdin": @(expected), @"submission": @(index)});
    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return NO;
    size_t length = strlen(line);
    if (length && line[length - 1] == '\n') line[--length] = 0;
    if (length && line[length - 1] == '\r') line[--length] = 0;
    if (strcmp(line, expected) != 0) return NO;
    emit(@"GATE_ACCEPTED", @{@"gate": event, @"accepted_stdin": @(expected), @"submission": @(index)});
    return YES;
}

static NSString *model(void) {
    char value[128] = {0};
    size_t length = sizeof(value);
    if (sysctlbyname("hw.model", value, &length, NULL, 0) != 0) return @"";
    value[sizeof(value) - 1] = 0;
    return @(value);
}

static NSArray *word_strings(const uint32_t *words, unsigned count) {
    NSMutableArray *values = [NSMutableArray arrayWithCapacity:count];
    for (unsigned index = 0; index < count; index++)
        [values addObject:[NSString stringWithFormat:@"%08x", words[index]]];
    return values;
}

static NSString *little_endian_address(uint64_t address) {
    NSMutableString *value = [NSMutableString string];
    for (unsigned index = 0; index < 8; index++)
        [value appendFormat:@"%02x", (unsigned)((address >> (8 * index)) & 0xff)];
    return value;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        BOOL run = NO, dry_run = NO, second = NO, fixture_store42 = NO;
        unsigned timeout_ms = 10000;
        NSString *expected_model = @"Mac16,8";
        NSString *device_prefix = @"Apple M4 Pro";
        for (int index = 1; index < argc; index++) {
            if (!strcmp(argv[index], "--run")) run = YES;
            else if (!strcmp(argv[index], "--dry-run")) dry_run = YES;
            else if (!strcmp(argv[index], "--second")) second = YES;
            else if (!strcmp(argv[index], "--fixture-store42")) fixture_store42 = YES;
            else if (!strcmp(argv[index], "--expect-model") && index + 1 < argc)
                expected_model = @(argv[++index]);
            else if (!strcmp(argv[index], "--expect-device-prefix") && index + 1 < argc)
                device_prefix = @(argv[++index]);
            else if (!strcmp(argv[index], "--timeout-ms") && index + 1 < argc) {
                char *end = NULL;
                errno = 0;
                unsigned long value = strtoul(argv[++index], &end, 10);
                if (errno || !end || *end || value == 0 || value > 30000)
                    return fail(@"timeout must be 1..30000 milliseconds", 64);
                timeout_ms = (unsigned)value;
            } else {
                fputs("Usage: compute-trigger (--dry-run | --run) [--second] [--fixture-store42] [--timeout-ms N]\n"
                      "  [--expect-model MODEL] [--expect-device-prefix PREFIX]\n", stderr);
                return 64;
            }
        }
        if (run == dry_run || expected_model.length == 0 || device_prefix.length == 0)
            return fail(@"choose exactly one mode and nonempty hardware expectations", 64);
        unsigned word_count = fixture_store42 ? STORE_WORDS : XOR_WORDS;
        uint32_t expected[STORE_WORDS];
        for (unsigned index = 0; index < word_count; index++)
            expected[index] = fixture_store42 ? 42U : index ^ XOR_MARKER;
        NSMutableDictionary *plan = [@{@"words": @(word_count), @"buffer_bytes": @(word_count * sizeof(uint32_t)),
                        @"submissions": @(second ? 2 : 1),
                        @"workload": fixture_store42 ? @"store42-256" : @"xor16",
                        @"threadgroups": @[@1, @1, @1],
                        @"threads_per_threadgroup": @[@(word_count), @1, @1],
                        @"grid": @[@(word_count), @1, @1],
                        @"expected_first_output": word_strings(expected, word_count),
                        @"expected_model": expected_model, @"expected_device_prefix": device_prefix,
                        @"timeout_ms": @(timeout_ms)} mutableCopy];
        if (fixture_store42)
            [plan addEntriesFromDictionary:@{@"initial_word_hex": @"a5a5a5a5", @"store_value": @42,
                                              @"dispatch_api": @"dispatchThreadgroups",
                                              @"surrounding_bo_canaries": @"UNTESTED; outside the owned Metal buffer"}];
        else
            [plan addEntriesFromDictionary:@{@"xor_hex": @"6145a55a", @"dispatch_api": @"dispatchThreads"}];
        emit(@"PLAN", plan);
        if (dry_run) return 0;  // No Metal API has been invoked by this process.

        struct utsname architecture;
        if (uname(&architecture) || strcmp(architecture.machine, "arm64"))
            return fail(@"native arm64 is required", 78);
        NSString *actual_model = model();
        if (![actual_model isEqualToString:expected_model])
            return fail(@"hardware model does not match explicit expectation", 78);
        if (!gate(@"WAIT_START", "START", 0))
            return fail(@"START gate refused before device creation", 65);

        emit(@"BEFORE_DEVICE", @{});
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device || ![device.name hasPrefix:device_prefix])
            return fail(@"Metal device does not match explicit expectation", 78);
        emit(@"DEVICE_READY", @{@"name": device.name, @"model": actual_model});

        // One buffer and one operation. Both shaders are our own source.
        NSString *source = fixture_store42 ? @"#include <metal_stdlib>\nusing namespace metal;\n"
            "kernel void fixture_store42(device uint* words [[buffer(0)]],\n"
            "                            uint i [[thread_position_in_grid]]) {\n"
            "  words[i] = 42u;\n}\n" : @"#include <metal_stdlib>\nusing namespace metal;\n"
            "kernel void marker_xor(device uint* words [[buffer(0)]],\n"
            "                       uint i [[thread_position_in_grid]]) {\n"
            "  if (i < 16u) words[i] = words[i] ^ 0x6145a55au;\n}\n";
        NSError *error = nil;
        emit(@"BEFORE_LIBRARY", @{});
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) return fail(error.localizedDescription ?: @"Metal library compilation failed", 70);
        id<MTLFunction> function = [library newFunctionWithName:fixture_store42 ? @"fixture_store42" : @"marker_xor"];
        if (!function) return fail(@"Metal function missing", 70);
        emit(@"BEFORE_PIPELINE", @{});
        id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&error];
        if (!pipeline) return fail(error.localizedDescription ?: @"compute pipeline creation failed", 70);
        if (pipeline.maxTotalThreadsPerThreadgroup < word_count)
            return fail(@"pipeline cannot execute the required complete local workgroup", 70);
        emit(@"PIPELINE_READY", @{@"thread_execution_width": @(pipeline.threadExecutionWidth),
                                 @"max_threads_per_threadgroup": @(pipeline.maxTotalThreadsPerThreadgroup)});

        emit(@"BEFORE_BUFFER", @{});
        id<MTLBuffer> buffer = [device newBufferWithLength:word_count * sizeof(uint32_t)
                                                options:MTLResourceStorageModeShared];
        if (!buffer || !buffer.contents) return fail(@"shared Metal buffer allocation failed", 70);
        uint32_t *words = buffer.contents;
        for (unsigned index = 0; index < word_count; index++)
            words[index] = fixture_store42 ? 0xa5a5a5a5U : index;
        emit(@"BUFFER_READY", @{@"gpu_address_hex": [NSString stringWithFormat:@"%016llx", (unsigned long long)buffer.gpuAddress],
                                 @"gpu_address_le": little_endian_address(buffer.gpuAddress),
                                 @"input": word_strings(words, word_count)});
        emit(@"BEFORE_QUEUE", @{});
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!queue) return fail(@"Metal command queue creation failed", 70);

        for (unsigned submission = 0; submission < (second ? 2U : 1U); submission++) {
            if (submission && !gate(@"WAIT_SECOND", "SECOND", submission))
                return fail(@"second submission gate refused", 65);
            emit(@"BEFORE_ENCODING", @{@"submission": @(submission)});
            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
            if (!command || !encoder) return fail(@"compute command encoding unavailable", 70);
            [encoder setComputePipelineState:pipeline];
            [encoder setBuffer:buffer offset:0 atIndex:0];
            if (fixture_store42)
                [encoder dispatchThreadgroups:MTLSizeMake(1, 1, 1)
                       threadsPerThreadgroup:MTLSizeMake(STORE_WORDS, 1, 1)];
            else
                [encoder dispatchThreads:MTLSizeMake(XOR_WORDS, 1, 1)
                  threadsPerThreadgroup:MTLSizeMake(XOR_WORDS, 1, 1)];
            [encoder endEncoding];
            const char *commit_gate = submission ? "COMMIT1" : "COMMIT0";
            if (!gate(@"WAIT_COMMIT", commit_gate, submission))
                return fail(@"commit gate refused", 65);
            dispatch_semaphore_t completed = dispatch_semaphore_create(0);
            [command addCompletedHandler:^(id<MTLCommandBuffer> unused) {
                (void)unused;
                dispatch_semaphore_signal(completed);
            }];
            emit(@"BEFORE_COMMIT", @{@"submission": @(submission)});
            [command commit];
            long waited = dispatch_semaphore_wait(completed,
                dispatch_time(DISPATCH_TIME_NOW, (int64_t)timeout_ms * NSEC_PER_MSEC));
            if (waited) return fail(@"GPU completion timeout; no success inferred", 75);
            emit(@"COMMAND_COMPLETED", @{@"submission": @(submission), @"status": @((long)command.status)});
            if (command.status != MTLCommandBufferStatusCompleted)
                return fail(command.error.localizedDescription ?: @"Metal command failed", 70);
            BOOL correct = YES;
            for (unsigned index = 0; index < word_count; index++) {
                uint32_t wanted = fixture_store42 ? 42U : (submission ? index : expected[index]);
                if (words[index] != wanted) correct = NO;
            }
            emit(@"READBACK", @{@"submission": @(submission), @"pass": @(correct), @"words": word_strings(words, word_count)});
            if (!correct) return fail(@"GPU result did not match CPU expectation", 65);
        }
        emit(@"DONE", @{@"submissions": @(second ? 2 : 1), @"verified_words_per_submission": @(word_count)});
        return 0;
    }
}
