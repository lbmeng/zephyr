# SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
# SPDX-License-Identifier: Apache-2.0

get_property(uimage_formats TARGET bintools PROPERTY elfconvert_formats)
if(NOT "binary" IN_LIST uimage_formats)
  message(FATAL_ERROR "U-Boot uImage output requires binary output support from the toolchain")
endif()

find_program(MKIMAGE NAMES mkimage REQUIRED)

set(uimage_script "${ZEPHYR_BASE}/scripts/build/uimage.py")
set(uimage_file "${PROJECT_BINARY_DIR}/${KERNEL_NAME}.uImage")
set(uimage_args
  --mkimage "${MKIMAGE}"
  --elf "${PROJECT_BINARY_DIR}/${KERNEL_ELF_NAME}"
  --bin "${PROJECT_BINARY_DIR}/${KERNEL_BIN_NAME}"
  --output "${uimage_file}"
  "--os=${CONFIG_BUILD_OUTPUT_UIMAGE_OS}"
  "--type=${CONFIG_BUILD_OUTPUT_UIMAGE_TYPE}"
  "--name=${CONFIG_BUILD_OUTPUT_UIMAGE_NAME}"
)

foreach(setting ARCH LOAD_ADDRESS ENTRY_POINT)
  if(NOT "${CONFIG_BUILD_OUTPUT_UIMAGE_${setting}}" STREQUAL "")
    string(TOLOWER "${setting}" option)
    string(REPLACE "_" "-" option "${option}")
    list(APPEND uimage_args "--${option}" "${CONFIG_BUILD_OUTPUT_UIMAGE_${setting}}")
  endif()
endforeach()

add_custom_command(
  OUTPUT "${uimage_file}"
  COMMAND "${PYTHON_EXECUTABLE}" "${uimage_script}" ${uimage_args}
  DEPENDS ${logical_target_for_zephyr_elf}
          "${PROJECT_BINARY_DIR}/${KERNEL_BIN_NAME}"
          "${uimage_script}"
          "${MKIMAGE}"
  COMMENT "Generating ${KERNEL_NAME}.uImage"
  VERBATIM
)

add_custom_target(uimage ALL DEPENDS "${uimage_file}")
set(BYPRODUCT_KERNEL_UIMAGE_NAME "${uimage_file}" CACHE FILEPATH "Kernel U-Boot legacy image" FORCE)
