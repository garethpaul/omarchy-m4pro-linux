#!/usr/bin/env python3
"""Read only saved source/artifacts; emit hashes and address-free contract facts."""
import argparse
import hashlib
import json
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--workspace', type=Path, required=True)
a = p.parse_args()
w = a.workspace.resolve()
def digest(path):
    return hashlib.sha256((w/path).read_bytes()).hexdigest()
def read(path):
    return (w/path).read_text()
paths = ['m1n1-native/src/j614s_native.c', 'm1n1-native/src/kboot.c',
         'm1n1-native/src/memory.c', 'm1n1-native/src/memory.h', 'm1n1-native/src/rtkit.c',
         'hardware-private/test56-archive-source-manifest.json',
         'overnight-test56-archive/drivers/nvme/host/apple.c']
facts = {'status': 'BLOCKED (borrowed-buffer cache/ownership handoff unqualified)',
         'mode': 'read-only cached source/artifacts', 'files': [{'path': s, 'sha256': digest(s)} for s in paths],
         'firmware_or_runtime_addresses_exported': False, 'target_access': False}
native = read(paths[0]);kboot = read(paths[1]);memory = read(paths[2]);rtkit = read(paths[4])
facts['source_contract'] = {
    'native_ram_size_bytes': 4 << 30,
    'native_replaces_memory_reg_with_only_owned_ram': 'set_pair(dt, memory, "reg", start, RAM_SIZE)' in native,
    'native_reserved_node_allowlist': ['ramoops', 'retention-control', 'mtp-firmware'],
    'native_reserves_predecessor_prefix': 'fdt_add_mem_rsv' in native,
    'generic_kboot_retained_heap_guard_t8140': 'if (chip_id == T8140)' in kboot and 'FDT: retained heap' in kboot,
    'generic_kboot_warns_whole_dram_linear_mapping_breaks_ioremap': 'breaks\n    // ioremap' in kboot,
    'source_maps_ram_normal_wb_then_unmaps_mcc_carveouts': 'MAIR_IDX_NORMAL, PERM_RWX' in memory and 'mcc_unmap_carveouts()' in memory,
    'source_contains_normal_nc_firmware_or_framebuffer_mappings': 'MAIR_IDX_NORMAL_NC' in memory,
    'rtkit_owned_buffers_are_heap_allocations': 'bfr->bfr = memalign(SZ_16K, alloc_sz)' in rtkit,
    'per_actual_ans_buffer_cache_attributes_proven': False,
    'loaded_binary_source_binding_proven_by_this_audit': False,
}
base_sha = digest('m1n1-native/build/m1n1.bin')
facts['saved_boots'] = []
for n in (52, 56):
    folder = f'hardware-private/native-test-{n}'
    manifest_path = f'{folder}/m1n1-native-test{n}-candidate.json'
    log_path = f'{folder}/' + ('final-live-evidence.txt' if n == 52 else 'final-evidence.txt')
    dts_path = f'{folder}/j614s-ramtest.dts'
    manifest = json.loads(read(manifest_path));log = read(log_path);dts = read(dts_path)
    totals = re.findall(r'Memory: \d+K/(\d+)K available', log)
    facts['saved_boots'].append({'test': n, 'files': [{'path': x, 'sha256': digest(x)} for x in (manifest_path,log_path,dts_path)],
        'current_qualified_base_matches_manifest': manifest['base_sha256'] == base_sha,
        'linux_total_ram_kib': [int(v) for v in totals],
        'reserved_node_dmesg_count': len(re.findall(r'OF: reserved mem:',log)),
        'nvme_hello_initialization_log_count': len(re.findall(r'nvme-apple[^\n]*RTKit: Initializing \(protocol version 12\)',log)),
        'explicit_borrowed_buffer_mapping_success_log_count': len(re.findall(r'nvme-apple[^\n]*(?:borrowed buffer mapped|inherited buffer mapped)',log)),
        'saved_dts_memory_node_count': len(re.findall(r'\bmemory@[0-9a-f]+\s*\{',dts)),
        'saved_dts_has_inherited_buffer_bank': 'ans-inherited' in dts,
        'interpretation': 'old boot/storage evidence does not establish execution or cache safety of borrowed-buffer mapping path'})
archive = json.loads(read(paths[5]))
facts['old_storage_source_matches_archival_manifest'] = digest(paths[6]) == archive['files']['drivers/nvme/host/apple.c']
facts['claim_limit'] = 'The native source excludes predecessor RAM; this is a conditional mapping gap, not evidence the new probe must fail. ACK-only inherited logging may require no borrowed mapping.'
print(json.dumps(facts, indent=2))
