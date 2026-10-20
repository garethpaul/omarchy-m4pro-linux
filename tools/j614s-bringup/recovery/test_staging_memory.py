# SPDX-License-Identifier: MIT
import copy
import struct
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from staging_memory import decode_ranges, validate_heap
from read_staging_memory import resident_symbols, sections_from_tree

SOURCES=('/chosen/memory-map','/chosen/carveout-memory-map')
def sections():
    return {SOURCES[0]: [('name',b'memory-map\0'),('boot',struct.pack('<QQ',0x1000,0x4000))],
            SOURCES[1]: [('region-id-24',struct.pack('<QQ',0x1000,0x10000)),('sentinel',struct.pack('<QQ',2**64-1,2**64-1)),('zero',struct.pack('<QQ',0x1800,0))]}
def memory():
    return dict(usable_base=0x1000,usable_size=0x10000,resident_base=0x2000,
                resident_end=0x5000,heap_base=0x8001,heap_limit=0,bootargs_top=0x6000)
def metadata():
    return [dict(name='live-bootargs',base=0x1800,size=0x100),dict(name='live-adt',base=0x6000,size=0x500)]

class StagingMemory(unittest.TestCase):
    def test_direct_target_calls_are_only_metadata_and_ram_reads(self):
        tree=ast.parse(Path(__file__).with_name('read_staging_memory.py').read_text())
        calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id in ('proxy','interface')}
        self.assertEqual(calls,{'nop','get_chipid','get_exc_count','get_bootargs','get_base','readmem'})
    def test_required_symbol_ambiguity_refused_without_rejecting_other_aliases(self):
        wanted=['_end','heap_base','heap_limit','boot_cpu_idx','boot_cpu_mpidr','ram_base','mem_size_actual','wfe_mode','spin_table','boot_args_addr','cur_boot_args']
        lines=[f'{i:x} 8 B {n}' for i,n in enumerate(wanted)]
        resident_symbols(lines+['0 8 b irrelevant','1 8 b irrelevant'])
        for bad in (lines[:-1],lines+lines[:1]):
            with self.assertRaises(ValueError):resident_symbols(bad)
    def test_only_unambiguous_memory_sections_extracted(self):
        def node(name,children=(),props=()):return NS(properties=[NS(name='name',value=name.encode()+b'\0')]+[NS(name=k,value=v) for k,v in props],children=children)
        mem=node('memory-map',props=[('x',b'x'*16)])
        carve=node('carveout-memory-map')
        root=node('device-tree',[node('chosen',[mem,carve]),node('other',[node('memory-map')])])
        self.assertEqual(set(sections_from_tree(root)),set(SOURCES))
        root.children[0].children.append(mem)
        with self.assertRaisesRegex(ValueError,'ambiguous'):sections_from_tree(root)
    def test_all_16_byte_ranges_preserved_without_exemption(self):
        rows=decode_ranges(sections())
        self.assertEqual(len(rows),4)
        self.assertEqual([r['name'] for r in rows],['boot','region-id-24','sentinel','zero'])
        self.assertEqual(rows[2]['base'],2**64-1)
        self.assertEqual(rows[3]['size'],0)
        self.assertEqual(rows[0]['raw_hex'],struct.pack('<QQ',0x1000,0x4000).hex())
    def test_duplicate_names_not_silently_overwritten(self):
        s=sections();s[SOURCES[0]].append(s[SOURCES[0]][1])
        with self.assertRaisesRegex(ValueError,'Duplicate'):decode_ranges(s)
    def test_missing_or_extra_source_refused(self):
        for s in ({SOURCES[0]:[]},{**sections(),'/other':[]}):
            with self.assertRaises(ValueError):decode_ranges(s)
    def test_overflow_refused_but_double_sentinel_kept(self):
        s=sections();s[SOURCES[0]].append(('overflow',struct.pack('<QQ',2**64-2,8)))
        with self.assertRaisesRegex(ValueError,'overflow'):decode_ranges(s)
    def test_invalid_property_types_refused(self):
        for pair in [('',b'1234567890123456'),('bad\0name',b''),('x','text'),(True,b'')]:
            s=sections();s[SOURCES[0]].append(pair)
            with self.assertRaises(ValueError):decode_ranges(s)
    def test_unaligned_high_water_is_not_rounded_or_changed(self):
        m=memory();before=copy.deepcopy(m);validate_heap(m,metadata());self.assertEqual(m,before)
    def test_heap_limit_zero_means_no_explicit_limit(self):
        validate_heap(memory(),metadata())
        m=memory();m['heap_limit']=0x9000;validate_heap(m,metadata())
    def test_bad_heap_and_ram_extents_refused(self):
        for key,val in [('heap_base',0x5000),('heap_base',0x11001),('heap_limit',0x7000),('heap_limit',0x12000),('bootargs_top',0x12000),('resident_end',0x1000),('usable_size',2**64),('heap_base',True)]:
            m=memory();m[key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):validate_heap(m,metadata())
    def test_exact_metadata_names_and_bounds_required(self):
        for rows in ([],metadata()*2,[dict(name='live-adt',base=0,size=1),metadata()[0]],[dict(name='live-adt',base=0x1000,size=0),metadata()[0]]):
            with self.assertRaises(ValueError):validate_heap(memory(),rows)

if __name__=='__main__':unittest.main()
