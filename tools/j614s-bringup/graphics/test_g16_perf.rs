// SPDX-License-Identifier: GPL-2.0-only
// The replay tool places the actual kernel source alongside this harness.
#[path = "g16_perf.rs"]
mod perf;
use perf::{DecodeError, Inputs};

fn fixture() -> (Vec<u8>, Vec<u8>) {
    // Wholly synthetic: deliberately repeated and descending state frequencies.
    let freq = [0, 100, 200, 190, 250, 250, 300, 330, 350, 400, 450, 430, 500, 540, 600, 620];
    let mut core = Vec::new();
    let mut sram = Vec::new();
    for bank in 0..2u32 {
        for (i, frequency) in freq.iter().enumerate() {
            core.extend_from_slice(&u32::to_le_bytes(*frequency));
            core.extend_from_slice(&(500 + bank * 10 + i as u32).to_le_bytes());
            sram.extend_from_slice(&u32::to_le_bytes(*frequency));
            sram.extend_from_slice(&(800 + bank * 10 + i as u32).to_le_bytes());
        }
    }
    (core, sram)
}

fn decode(core: &[u8], sram: &[u8]) -> Result<Inputs, DecodeError> {
    Inputs::decode(16, 15, 2, core, sram, &core[128..], &sram[128..], 200_000, 8, 15)
}

#[test]
fn preserves_state_order_both_voltage_banks_and_fractional_sampling() {
    let (core, sram) = fixture();
    let p = decode(&core, &sram).expect("16-state, two-bank ADT inputs must decode");
    assert_eq!(p.core[0][2].frequency_hz, 200);
    assert_eq!(p.core[0][3].frequency_hz, 190);
    assert_eq!(p.core[0][4].frequency_hz, p.core[0][5].frequency_hz);
    assert_eq!(p.core[0][15].voltage_mv, 515);
    assert_eq!(p.core[1][15].voltage_mv, 525);
    assert_eq!(p.sram[1][15].voltage_mv, 825);
    assert_eq!(p.period_clocks, 200_000);
    assert_eq!(p.period_ms, 8);
    assert_ne!(p.period_clocks, p.period_ms * 24_000);
    assert_eq!(p.active_mcc_mask, 15);
}

#[test]
fn refuses_truncation_and_trailing_data() {
    let (core, sram) = fixture();
    for size in [0, 127, 128, 255, 257] {
        let mut bad = core.clone(); bad.resize(size, 0);
        assert!(matches!(Inputs::decode(16, 15, 2, &bad, &sram, &core[128..], &sram[128..], 200_000, 8, 15), Err(DecodeError::Length)));
    }
}

#[test]
fn refuses_count_alias_and_single_bank_substitution() {
    let (core, sram) = fixture();
    for counts in [(11, 10, 1), (16, 15, 1), (16, 16, 2), (0, 0, 0)] {
        assert!(matches!(Inputs::decode(counts.0, counts.1, counts.2, &core, &sram, &core[128..], &sram[128..], 200_000, 8, 15), Err(DecodeError::Shape)));
    }
}

#[test]
fn refuses_mismatched_second_bank_alias() {
    let (core, sram) = fixture();
    let mut mirror = core[128..].to_vec(); mirror[4] ^= 1;
    assert!(matches!(Inputs::decode(16, 15, 2, &core, &sram, &mirror, &sram[128..], 200_000, 8, 15), Err(DecodeError::Mirror)));
}

#[test]
fn refuses_misaligned_sram_frequencies_and_zero_active_state() {
    let (core, mut sram) = fixture(); sram[8] ^= 1;
    assert!(matches!(decode(&core, &sram), Err(DecodeError::Frequency)));
    let (mut core, mut sram) = fixture(); core[8..12].fill(0); sram[8..12].fill(0);
    assert!(matches!(decode(&core, &sram), Err(DecodeError::Frequency)));
}

#[test]
fn refuses_voltage_conversion_overflow() {
    let (mut core, sram) = fixture(); core[12..16].copy_from_slice(&u32::MAX.to_le_bytes());
    assert!(matches!(decode(&core, &sram), Err(DecodeError::Voltage)));
}

#[test]
fn refuses_inconsistent_sampling_and_empty_mcc() {
    let (core, sram) = fixture();
    for (clocks, ms, mask) in [(0, 0, 15), (192_000, 9, 15), (200_000, 8, 0)] {
        assert!(matches!(Inputs::decode(16, 15, 2, &core, &sram, &core[128..], &sram[128..], clocks, ms, mask), Err(DecodeError::Sampling)));
    }
}
