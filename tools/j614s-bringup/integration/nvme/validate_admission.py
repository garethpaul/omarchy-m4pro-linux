#!/usr/bin/env python3
"""Check immutable admission wiring alongside executed selected-source fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def function(source, marker):
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]


def validate(source, rtkit, legacy):
    results = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        results.append(name)
    allocate = function(source, 'static struct apple_nvme *apple_nvme_alloc(')
    markers = ['apple_nvme_check_j614s_resources(', 'apple_nvme_controller_quarantined(',
               'apple_nvme_alloc_owner(', 'apple_nvme_map_retained_mmio(',
               'apple_nvme_read_handoff(', 'apple_nvme_can_adopt_rtkit(',
               'devm_apple_sart_get(', 'apple_nvme_queue_alloc(', 'devm_request_irq(',
               'apple_rtkit_init_adopted(', 'apple_nvme_free_rtkit,', 'nvme_init_ctrl(', 'kref_get(']
    positions = [allocate.index(marker) for marker in markers]
    check('metadata and no-reprobe precede allocation; measured state precedes supplier/DMA/RX/controller initialization', positions == sorted(positions))
    check('no blanket refusal or generic T6040 match replaces explicit diagnostic admission',
          'has not been ported' not in allocate and '"apple,t6040-nvme' not in source and
          '{ .compatible = "apple,j614s-nvme-diagnostic", .data = &apple_nvme_j614s_diagnostic_hw }' in source)
    for old_name, new_name in [('apple_nvme_reset_work','apple_nvme_reset_legacy_work'),
                               ('apple_nvme_timeout','apple_nvme_timeout_legacy')]:
        prefix = 'static void ' if 'reset' in old_name else 'static enum blk_eh_timer_return '
        original = function(legacy, prefix + old_name + '(')
        retained = function(source, prefix + new_name + '(').replace(new_name, old_name, 1)
        check(old_name + ' legacy body retained byte-for-byte', original == retained)
    reset = function(source, 'static void apple_nvme_reset_work(')
    check('inherited worker has no cold/PMGR reset, RTKit handshake replay, shutdown or DeleteSQ/CQ call',
          not any(marker in reset for marker in ['reset_control_', 'apple_rtkit_boot(', 'apple_rtkit_wake(',
                  'apple_rtkit_shutdown(', 'apple_rtkit_adopt_running(', 'apple_nvme_remove_sq(', 'apple_nvme_remove_cq(']))
    check('inherited worker dispatches legacy only before entering inherited phases',
          reset.index('if (!anv->inherited_rtkit)') < reset.index('mutex_lock('))
    poll = function(source, 'static int apple_nvme_poll(')
    check('poll quarantine test under CQ lock before DMA/CQ use',
          poll.index('spin_lock_irqsave(') < poll.index('READ_ONCE(anv->quarantined)') < poll.index('apple_nvme_poll_cq('))
    quarantine = function(source, 'static void apple_nvme_quarantine(')
    check('quarantine publication uses same CQ lock before module/resource pins',
          quarantine.index('spin_lock_irqsave(&anv->lock') < quarantine.index('WRITE_ONCE(anv->quarantined, true)') < quarantine.index('spin_unlock_irqrestore(') < quarantine.index('__module_get('))
    free = function(source, 'static void apple_nvme_free_rtkit(')
    check('failed stop quiesces retaining object before ordinary free paths',
          free.index('READ_ONCE(anv->quarantined)') < free.index('apple_rtkit_quiesce_retaining_state(') < free.index('apple_rtkit_free_retaining_buffers('))
    check('manual MMIO cleanup skips both unmap and region release on quarantine',
          function(source, 'static void apple_nvme_free_retained_mmio(').index('READ_ONCE(mapping->owner->quarantined)') < function(source, 'static void apple_nvme_free_retained_mmio(').index('iounmap('))
    retain = function(rtkit, 'void apple_rtkit_quiesce_retaining_state(')
    check('quiesce retains RTKit object, shared buffers and mailbox cookie reservation',
          'apple_rtkit_stop_rx(rtk)' in retain and not any(m in retain for m in ['kfree(', 'apple_rtkit_release_rx(', 'apple_rtkit_free_buffer(']))
    stop = function(rtkit, 'static void apple_rtkit_stop_rx(')
    check('RX drain destroys workqueue once and clears pointer', 'if (rtk->wq)' in stop and 'rtk->wq = NULL' in stop)
    return results


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--commit', required=True)
a = p.parse_args()
def blob(commit, path):
    return subprocess.check_output(['git', '-C', str(a.source), 'show', commit + ':' + path], text=True)
commit = subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', a.commit], text=True).strip()
source = blob(commit, 'drivers/nvme/host/apple.c')
rtkit = blob(commit, 'drivers/soc/apple/rtkit.c')
checks = validate(source, rtkit, blob('8acc4f6f70fa4b6b3da347cc7b19eb6cd8cf24ac', 'drivers/nvme/host/apple.c'))
print(json.dumps({'status': 'WORKS (source wiring assertions only)', 'source_commit': commit,
                  'apple_sha256': hashlib.sha256(source.encode()).hexdigest(),
                  'rtkit_sha256': hashlib.sha256(rtkit.encode()).hexdigest(), 'checks': checks,
                  'count': len(checks), 'hardware': 'UNTESTED', 'target_access': False}, indent=2))
