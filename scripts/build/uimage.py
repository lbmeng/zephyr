#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
# SPDX-License-Identifier: Apache-2.0

"""Wrap a Zephyr binary in an uncompressed U-Boot legacy image."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile


def architecture(elf):
    """Translate an ELF machine to a mkimage architecture name."""
    machine = elf['e_machine']
    if machine == 'EM_MIPS':
        return 'mips64' if elf.elfclass == 64 else 'mips'

    names = {
        'EM_386': 'x86',
        'EM_68K': 'm68k',
        'EM_AARCH64': 'arm64',
        'EM_ALTERA_NIOS2': 'nios2',
        'EM_ARC': 'arc',
        'EM_ARC_COMPACT': 'arc',
        'EM_ARC_COMPACT2': 'arc',
        'EM_ARM': 'arm',
        'EM_MICROBLAZE': 'microblaze',
        'EM_OPENRISC': 'or1k',
        'EM_PPC': 'powerpc',
        'EM_RISCV': 'riscv',
        'EM_SPARC': 'sparc',
        'EM_SPARCV9': 'sparc64',
        'EM_X86_64': 'x86_64',
        'EM_XTENSA': 'xtensa',
    }
    if machine not in names:
        raise ValueError(f'unsupported ELF machine {machine}; set BUILD_OUTPUT_UIMAGE_ARCH')
    return names[machine]


def load_address(elf, binary_size):
    """Find the LMA range of sections copied by the binary conversion."""
    segments = [segment for segment in elf.iter_segments() if segment['p_type'] == 'PT_LOAD']
    ranges = []
    for section in elf.iter_sections():
        if (
            not section['sh_flags'] & SH_FLAGS.SHF_ALLOC
            or section['sh_type'] == 'SHT_NOBITS'
            or section['sh_size'] == 0
            or section.name in ('.comment', 'COMMON')
        ):
            continue
        for segment in segments:
            if segment.section_in_segment(section):
                address = segment['p_paddr'] + section['sh_addr'] - segment['p_vaddr']
                ranges.append((address, address + section['sh_size']))
                break
        else:
            raise ValueError(
                f'cannot determine the load address of {section.name}; '
                'set BUILD_OUTPUT_UIMAGE_LOAD_ADDRESS'
            )

    if not ranges:
        raise ValueError('ELF has no file-backed allocated sections')
    first = min(start for start, _ in ranges)
    last = max(end for _, end in ranges)
    if last - first != binary_size:
        raise ValueError(
            'BIN size does not match the ELF load address range; '
            'set BUILD_OUTPUT_UIMAGE_LOAD_ADDRESS for this binary layout'
        )
    return first


def address32(value):
    """Check a legacy image address before mkimage can truncate it."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f'address {value:#x} does not fit in a 32-bit legacy uImage header')
    return value


def create_image(args):
    size = args.bin.stat().st_size
    if not 0 < size <= 0xFFFFFFFF:
        raise ValueError('legacy uImage payload must contain between 1 and 0xffffffff bytes')
    if len(args.name.encode('utf-8')) > 32:
        raise ValueError('uImage description exceeds 32 UTF-8 bytes')

    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        arch = args.arch or architecture(elf)
        load = args.load_address
        if load is None:
            load = load_address(elf, size)
        entry = elf['e_entry'] if args.entry_point is None else args.entry_point
    address32(load)
    address32(entry)
    address32(load + size - 1)

    # Publish the image only after mkimage succeeds
    with tempfile.TemporaryDirectory(prefix='uimage-', dir=args.output.parent) as temp:
        output = Path(temp) / args.output.name
        subprocess.run(
            [
                args.mkimage,
                '-A',
                arch,
                '-O',
                args.os,
                '-T',
                args.type,
                '-C',
                'none',
                '-a',
                f'{load:x}',
                '-e',
                f'{entry:x}',
                '-n',
                args.name,
                '-d',
                str(args.bin),
                str(output),
            ],
            check=True,
        )
        output.replace(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mkimage', default='mkimage')
    parser.add_argument('--arch')
    parser.add_argument('--os', default='linux')
    parser.add_argument('--type', default='kernel')
    parser.add_argument('--name', default='Zephyr')
    parser.add_argument('--load-address', type=lambda value: int(value, 0))
    parser.add_argument('--entry-point', type=lambda value: int(value, 0))
    args = parser.parse_args()
    try:
        create_image(args)
    except (ELFError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'uImage: {error}\n')


if __name__ == '__main__':
    main()
