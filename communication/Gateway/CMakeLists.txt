cmake_minimum_required(VERSION 3.16)
project(EDGECS_Gateway_CPP LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Threads REQUIRED)
find_package(CURL REQUIRED)
find_package(nlohmann_json 3.2 REQUIRED CONFIG)

# Paho MQTT C++ package (Debian: libpaho-mqttpp-dev).
find_path(PAHO_INCLUDE_DIR mqtt/async_client.h REQUIRED)
find_library(PAHO_CPP_LIBRARY NAMES paho-mqttpp3 REQUIRED)
find_library(PAHO_C_LIBRARY NAMES paho-mqtt3as paho-mqtt3a REQUIRED)

# OpenDNP3 C++ 3.1.2 install (git: dnp3/opendnp3 tag 3.1.2).
# CMAKE_PREFIX_PATH=/path/to/opendnp3/install peut etre utilise.
find_path(OPENDNP3_INCLUDE_DIR opendnp3/DNP3Manager.h
    HINTS "${CMAKE_CURRENT_SOURCE_DIR}/../opendnp3-install" PATH_SUFFIXES include REQUIRED)
find_library(OPENDNP3_LIBRARY NAMES opendnp3
    HINTS "${CMAKE_CURRENT_SOURCE_DIR}/../opendnp3-install" PATH_SUFFIXES lib lib64 REQUIRED)

add_library(edgecs_common STATIC ../shared/common.cpp)
target_include_directories(edgecs_common PUBLIC ../shared src)
target_link_libraries(edgecs_common PUBLIC nlohmann_json::nlohmann_json)

add_executable(edgecs_gateway src/outstation.cpp)
target_include_directories(edgecs_gateway PRIVATE ${OPENDNP3_INCLUDE_DIR} ${PAHO_INCLUDE_DIR})
target_link_libraries(edgecs_gateway PRIVATE edgecs_common ${OPENDNP3_LIBRARY}
    ${PAHO_CPP_LIBRARY} ${PAHO_C_LIBRARY} CURL::libcurl Threads::Threads)

foreach(simulator edgecs_der_sim edgecs_bess_sim)
  # Keep the historical executable name for existing launch scripts.
  add_executable(${simulator} src/simulated_der.cpp)
  target_include_directories(${simulator} PRIVATE ${PAHO_INCLUDE_DIR})
  target_link_libraries(${simulator} PRIVATE edgecs_common ${PAHO_CPP_LIBRARY} ${PAHO_C_LIBRARY} Threads::Threads)
endforeach()

include(CTest)
if(BUILD_TESTING)
  add_executable(test_common tests/test_common.cpp)
  target_link_libraries(test_common PRIVATE edgecs_common)
  add_test(NAME config_and_messages COMMAND test_common
    ${CMAKE_CURRENT_SOURCE_DIR}/config/outstation_config.json
    ${CMAKE_CURRENT_SOURCE_DIR}/config/generator_config.json)
endif()
