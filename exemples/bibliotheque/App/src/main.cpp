#include "core.h"

#include <iostream>

int main()
{
    std::cout << "App " PROJECT_VERSION " en " APP_CONFIG ", avec " << core_config() << ".\n";
    return 0;
}
