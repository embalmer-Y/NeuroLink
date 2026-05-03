cmake_minimum_required(VERSION 3.20.0)

project(neuro_demo_net_event LANGUAGES C)

if(NOT DEFINED LLEXT_EDK_INSTALL_DIR)
	set(LLEXT_EDK_INSTALL_DIR $ENV{LLEXT_EDK_INSTALL_DIR})
endif()

if(NOT LLEXT_EDK_INSTALL_DIR)
	message(FATAL_ERROR "LLEXT_EDK_INSTALL_DIR must point to an extracted llext-edk directory")
endif()

if(NOT IS_ABSOLUTE "${LLEXT_EDK_INSTALL_DIR}")
	get_filename_component(LLEXT_EDK_INSTALL_DIR "${LLEXT_EDK_INSTALL_DIR}"
		ABSOLUTE BASE_DIR "${CMAKE_CURRENT_BINARY_DIR}")
endif()

include(${LLEXT_EDK_INSTALL_DIR}/cmake.cflags)

add_compile_options(${LLEXT_CFLAGS})
add_compile_options(-c)

get_property(COMPILE_OPTIONS_PROP DIRECTORY PROPERTY COMPILE_OPTIONS)

add_custom_command(
	OUTPUT ${PROJECT_BINARY_DIR}/${PROJECT_NAME}.llext
	COMMAND ${CMAKE_C_COMPILER} ${COMPILE_OPTIONS_PROP}
		-o ${PROJECT_BINARY_DIR}/${PROJECT_NAME}.llext
		${PROJECT_SOURCE_DIR}/src/main.c
	DEPENDS ${PROJECT_SOURCE_DIR}/src/main.c
	VERBATIM
)

add_custom_target(${PROJECT_NAME} ALL DEPENDS ${PROJECT_BINARY_DIR}/${PROJECT_NAME}.llext)