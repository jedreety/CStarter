cmake_minimum_required(VERSION 3.20)
project(Calcul VERSION 1.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)

add_library(calcul STATIC calcul/src/calcul.cpp calcul/include/calcul.h)
target_include_directories(calcul PUBLIC calcul/include)
target_compile_definitions(calcul PRIVATE CALCUL_INTERNE)

add_executable(appli appli/main.cpp)
target_link_libraries(appli PRIVATE calcul)
target_compile_definitions(appli PRIVATE APPLI_VERSION="${PROJECT_VERSION}")

# Une cible sans compilation : l'import la signale.
add_custom_target(documentation COMMAND ${CMAKE_COMMAND} -E echo "documentation")
