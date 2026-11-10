cmake_minimum_required(VERSION 3.16)
project(EDGECS_DERMS_CPP LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Threads REQUIRED)
find_package(nlohmann_json 3.2 REQUIRED CONFIG)
find_package(Drogon CONFIG REQUIRED)

find_path(PAHO_INCLUDE_DIR mqtt/async_client.h REQUIRED)
find_library(PAHO_CPP_LIBRARY NAMES paho-mqttpp3 REQUIRED)
find_library(PAHO_C_LIBRARY NAMES paho-mqtt3as paho-mqtt3a REQUIRED)
find_path(OPENDNP3_INCLUDE_DIR
    NAMES opendnp3/DNP3Manager.h
    HINTS "${CMAKE_SOURCE_DIR}/../opendnp3-install"
    PATH_SUFFIXES include
    REQUIRED
)

find_library(OPENDNP3_LIBRARY
    NAMES opendnp3
    HINTS "${CMAKE_SOURCE_DIR}/../opendnp3-install"
    PATH_SUFFIXES lib lib64
    REQUIRED
)

add_library(edgecs_core STATIC ../shared/common.cpp src/registry.cpp)
target_include_directories(edgecs_core PUBLIC src)
target_link_libraries(edgecs_core PUBLIC nlohmann_json::nlohmann_json)

add_executable(edgecs_master src/master.cpp)
target_include_directories(edgecs_master PRIVATE ${OPENDNP3_INCLUDE_DIR} ${PAHO_INCLUDE_DIR})
target_link_libraries(edgecs_master PRIVATE edgecs_core Drogon::Drogon
  ${OPENDNP3_LIBRARY} ${PAHO_CPP_LIBRARY} ${PAHO_C_LIBRARY} Threads::Threads)

include(CTest)
option(EDGECS_INTEGRATION_TESTS "Run real local HTTPS/DNP3/MQTT acceptance tests" OFF)
if(BUILD_TESTING AND EDGECS_INTEGRATION_TESTS)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_test(NAME configuration_driven_end_to_end
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../tests/integration.py
      --derms-build ${CMAKE_CURRENT_BINARY_DIR}
      --gateway-build ${CMAKE_CURRENT_SOURCE_DIR}/../Gateway/build)
  set_tests_properties(configuration_driven_end_to_end PROPERTIES TIMEOUT 180 RUN_SERIAL TRUE)
endif()
