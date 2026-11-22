# SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
# SPDX-License-Identifier: Apache-2.0

"""Check legacy image metadata against ELF load and virtual addresses."""

import importlib.util
import io
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from elftools.elf.elffile import ELFFile

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/build/uimage.py'
SPEC = importlib.util.spec_from_file_location('uimage', SCRIPT)
uimage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uimage)


def elf_data(*, bits=64, machine=183, load=0x80100000, entry=0x40000100, endian='<'):
    """Include ELF headers, separate data LMA/VMA, BSS and debug data."""
    names = b'\0.text\0.data\0.bss\0.debug\0.shstrtab\0'
    offsets = {
        name: names.index(name.encode())
        for name in ['.text', '.data', '.bss', '.debug', '.shstrtab']
    }
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (offsets['.text'], 1, 6, 0x40000100, 0x100, 4, 0, 0, 4, 0),
        (offsets['.data'], 1, 3, 0x90000000, 0x180, 4, 0, 0, 4, 0),
        (offsets['.bss'], 8, 3, 0x1000, 0x184, 32, 0, 0, 4, 0),
        (offsets['.debug'], 1, 0, 0, 0x1C0, 8, 0, 0, 1, 0),
        (offsets['.shstrtab'], 3, 0, 0, 0x200, len(names), 0, 0, 1, 0),
    ]
    # type, flags, offset, VMA, LMA, file size, memory size, alignment
    segments = [
        (1, 5, 0, 0x40000000, load - 0x100, 0x104, 0x104, 0x1000),
        (1, 6, 0x180, 0x90000000, load + 0x10, 4, 4, 4),
        (1, 6, 0x184, 0x1000, 0x1000, 0, 32, 4),
    ]
    ehsize, phsize, shsize = (64, 56, 64) if bits == 64 else (52, 32, 40)
    ident = b'\x7fELF' + bytes([2 if bits == 64 else 1, 1 if endian == '<' else 2, 1]) + bytes(9)
    header = struct.pack(
        endian + ('HHIQQQIHHHHHH' if bits == 64 else 'HHIIIIIHHHHHH'),
        2,
        machine,
        1,
        entry,
        ehsize,
        0x300,
        0,
        ehsize,
        phsize,
        3,
        shsize,
        len(sections),
        5,
    )
    result = bytearray(0x300 + shsize * len(sections))
    result[:ehsize] = ident + header
    for index, segment in enumerate(segments):
        if bits == 64:
            data = struct.pack(endian + 'IIQQQQQQ', *segment)
        else:
            kind, flags, offset, vma, lma, size, memory, align = segment
            data = struct.pack(
                endian + 'IIIIIIII', kind, offset, vma, lma, size, memory, flags, align
            )
        start = ehsize + index * phsize
        result[start : start + phsize] = data
    for index, section in enumerate(sections):
        start = 0x300 + index * shsize
        result[start : start + shsize] = struct.pack(
            endian + ('IIQQQQIIQQ' if bits == 64 else 'IIIIIIIIII'), *section
        )
    result[0x100:0x104] = b'TEXT'
    result[0x180:0x184] = b'DATA'
    result[0x1C0:0x1C8] = b'DEBUG123'
    result[0x200 : 0x200 + len(names)] = names
    return bytes(result)


@pytest.mark.parametrize('bits', [32, 64])
@pytest.mark.parametrize('endian', ['<', '>'])
def test_infer_binary_lma(bits, endian):
    elf = ELFFile(io.BytesIO(elf_data(bits=bits, endian=endian)))
    assert uimage.load_address(elf, 20) == 0x80100000
    with pytest.raises(ValueError, match='BIN size'):
        uimage.load_address(elf, 19)


@pytest.mark.parametrize(
    'machine,bits,expected',
    [
        (40, 32, 'arm'),
        (183, 64, 'arm64'),
        (243, 32, 'riscv'),
        (243, 64, 'riscv'),
        (3, 32, 'x86'),
        (62, 64, 'x86_64'),
        (8, 32, 'mips'),
        (8, 64, 'mips64'),
        (94, 32, 'xtensa'),
        (113, 32, 'nios2'),
        (189, 32, 'microblaze'),
        (45, 32, 'arc'),
        (93, 32, 'arc'),
        (195, 32, 'arc'),
        (92, 32, 'or1k'),
        (20, 32, 'powerpc'),
        (2, 32, 'sparc'),
        (43, 64, 'sparc64'),
        (4, 32, 'm68k'),
    ],
)
def test_architecture(machine, bits, expected):
    elf = ELFFile(io.BytesIO(elf_data(machine=machine, bits=bits)))
    assert uimage.architecture(elf) == expected


def test_unknown_architecture():
    elf = ELFFile(io.BytesIO(elf_data(machine=247)))
    with pytest.raises(ValueError, match='BUILD_OUTPUT_UIMAGE_ARCH'):
        uimage.architecture(elf)


@pytest.mark.parametrize('value', [0, 1, 0xFFFFFFFF])
def test_legacy_address(value):
    assert uimage.address32(value) == value


@pytest.mark.parametrize('value', [-1, 0x100000000, 0xFFFFFFFF80000000])
def test_legacy_address_overflow(value):
    with pytest.raises(ValueError, match='32-bit'):
        uimage.address32(value)


@pytest.fixture
def image_args(tmp_path):
    elf = tmp_path / 'input kernel.elf'
    binary = tmp_path / 'input kernel.bin'
    elf.write_bytes(elf_data())
    binary.write_bytes(b'TEXT' + b'\xff' * 12 + b'DATA')
    return SimpleNamespace(
        elf=elf,
        bin=binary,
        output=tmp_path / 'output kernel.uImage',
        mkimage='mkimage',
        arch=None,
        os='linux',
        type='kernel',
        name='Zephyr',
        load_address=None,
        entry_point=None,
    )


def test_default_arguments(image_args, monkeypatch):
    image_args.elf.write_bytes(elf_data(machine=40, bits=32, entry=0x40000101))

    def run(command, *, check):
        assert check
        assert command[1:-1] == [
            '-A',
            'arm',
            '-O',
            'linux',
            '-T',
            'kernel',
            '-C',
            'none',
            '-a',
            '80100000',
            '-e',
            '40000101',
            '-n',
            'Zephyr',
            '-d',
            str(image_args.bin),
        ]
        Path(command[-1]).write_bytes(b'image')

    monkeypatch.setattr(uimage.subprocess, 'run', run)
    uimage.create_image(image_args)
    assert image_args.output.read_bytes() == b'image'


def test_explicit_overrides(image_args, monkeypatch):
    image_args.elf.write_bytes(elf_data(machine=247))
    image_args.bin.write_bytes(b'header and payload')
    image_args.arch = 'arm'
    image_args.os = 'u-boot'
    image_args.type = 'standalone'
    image_args.name = 'A name with spaces'
    image_args.load_address = 0
    image_args.entry_point = 0

    def run(command, *, check):
        assert check
        assert command[1:-1] == [
            '-A',
            'arm',
            '-O',
            'u-boot',
            '-T',
            'standalone',
            '-C',
            'none',
            '-a',
            '0',
            '-e',
            '0',
            '-n',
            'A name with spaces',
            '-d',
            str(image_args.bin),
        ]
        Path(command[-1]).write_bytes(b'override')

    monkeypatch.setattr(uimage.subprocess, 'run', run)
    uimage.create_image(image_args)
    assert image_args.output.read_bytes() == b'override'


def test_failed_mkimage_preserves_output(image_args, monkeypatch):
    image_args.output.write_bytes(b'previous')

    def fail(command, *, check):
        Path(command[-1]).write_bytes(b'incomplete')
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(uimage.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        uimage.create_image(image_args)
    assert image_args.output.read_bytes() == b'previous'
    assert not list(image_args.output.parent.glob('uimage-*'))


@pytest.mark.parametrize(
    'field,value',
    [
        ('load_address', 0x100000000),
        ('entry_point', 0x100000000),
        ('load_address', 0xFFFFFFFE),
        ('name', 'x' * 33),
        ('name', 'é' * 17),
    ],
)
def test_invalid_header(image_args, field, value):
    setattr(image_args, field, value)
    with pytest.raises(ValueError):
        uimage.create_image(image_args)
    assert not image_args.output.exists()


def test_empty_payload(image_args):
    image_args.bin.write_bytes(b'')
    with pytest.raises(ValueError, match='payload'):
        uimage.create_image(image_args)


@pytest.mark.skipif(shutil.which('mkimage') is None, reason='requires U-Boot mkimage')
def test_real_mkimage_header(image_args, monkeypatch):
    monkeypatch.setenv('SOURCE_DATE_EPOCH', '1700000000')
    subprocess.run(
        [
            'python3',
            str(SCRIPT),
            '--elf',
            str(image_args.elf),
            '--bin',
            str(image_args.bin),
            '--output',
            str(image_args.output),
        ],
        check=True,
    )
    image = image_args.output.read_bytes()
    magic, hcrc, timestamp, size, load, entry, dcrc, os_id, arch, kind, comp, name = struct.unpack(
        '>7I4B32s', image[:64]
    )
    assert magic == 0x27051956
    assert timestamp == 1700000000
    assert size == 20
    assert load == 0x80100000
    assert entry == 0x40000100
    assert (os_id, arch, kind, comp) == (5, 22, 2, 0)
    assert name.rstrip(b'\0') == b'Zephyr'
    assert image[64:] == image_args.bin.read_bytes()
    assert dcrc == zlib.crc32(image[64:])
    assert hcrc == zlib.crc32(image[:4] + bytes(4) + image[8:64])
