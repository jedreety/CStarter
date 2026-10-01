#include <lz4.h>

#include <iostream>

int main()
{
    std::cout << "lz4 " << LZ4_versionString() << ", importée de vcpkg.json.\n";
    return 0;
}
