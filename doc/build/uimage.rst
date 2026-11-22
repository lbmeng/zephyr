.. SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
.. SPDX-License-Identifier: Apache-2.0

.. _build_output_uimage:

U-Boot legacy images
####################

Zephyr can package its raw binary as an uncompressed U-Boot legacy image during
the normal build. Install the host ``mkimage`` utility from U-Boot, then enable
:kconfig:option:`CONFIG_BUILD_OUTPUT_UIMAGE` in the application configuration::

   CONFIG_BUILD_OUTPUT_UIMAGE=y

This also enables the raw BIN output needed by ``mkimage``.

For example:

.. code-block:: console

   west build -b qemu_cortex_a53 samples/hello_world -- -DCONFIG_BUILD_OUTPUT_UIMAGE=y

The build produces :file:`build/zephyr/zephyr.uImage` alongside the ELF and BIN
files. The basename follows :kconfig:option:`CONFIG_KERNEL_BIN_NAME`. The
``uimage`` build target can also regenerate this file:

.. code-block:: console

   west build -t uimage

``mkimage`` is required only when this output is enabled. If it is outside
``PATH``, pass ``-DMKIMAGE=/absolute/path/to/mkimage`` to CMake.

Image metadata
**************

The default architecture is derived from the final ELF machine type and class.
The entry point comes from the ELF header, including the Thumb state bit on
ARM targets. The default load address is the lowest load memory address of the
file-backed allocated sections copied into the BIN file. ELF headers, debug
sections and zero-initialized sections do not determine that address. Load
addresses are used even when a section has a different virtual address.

The BIN size must match the inferred load address range. If the binary has a
different layout, provide an explicit load address. An address of zero is a
valid override; an empty string selects automatic detection::

   CONFIG_BUILD_OUTPUT_UIMAGE_LOAD_ADDRESS="0x80100000"
   CONFIG_BUILD_OUTPUT_UIMAGE_ENTRY_POINT="0x80101000"

The architecture, description, image type and operating system can also be
set by an application or through board/SoC Kconfig defaults::

   CONFIG_BUILD_OUTPUT_UIMAGE_ARCH="arm64"
   CONFIG_BUILD_OUTPUT_UIMAGE_NAME="Zephyr application"
   CONFIG_BUILD_OUTPUT_UIMAGE_TYPE="kernel"
   CONFIG_BUILD_OUTPUT_UIMAGE_OS="linux"

The operating system defaults to ``linux``, the image type to ``kernel``, and
the description to ``Zephyr``. The OS and type fields select U-Boot's boot
handler and calling convention; they do not change the Zephyr application.
Choose values compatible with the platform's boot firmware. A Linux handler
may require a separate DTB even though Zephyr uses its compiled-in devicetree.
The load address specifies the BIN payload destination, not the address at
which the uImage header is loaded for ``bootm``.

Limitations
***********

This output supports one uncompressed BIN payload, not FIT images, multiple
components, or ``mkimage -x`` execute-in-place packaging. Legacy image load
and entry addresses are 32-bit fields, including on 64-bit architectures.
Addresses or payload ranges that do not fit are rejected instead of truncated.
Generating an image does not establish that a particular U-Boot boot handler
supports the board or application.

See the `U-Boot bootm documentation`_ for the firmware command syntax.

.. _U-Boot bootm documentation: https://docs.u-boot.org/en/latest/usage/cmd/bootm.html
