#include <zlib.h>

#include <iostream>

int main()
{
    std::cout << "zlib " << zlibVersion() << ", importée de conanfile.txt.\n";
    return 0;
}
