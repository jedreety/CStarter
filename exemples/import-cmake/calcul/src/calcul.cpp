#include "calcul.h"

#ifndef CALCUL_INTERNE
#error "CALCUL_INTERNE manque : le define de CMake n'a pas été repris"
#endif

int doubler(int valeur)
{
    return valeur * 2;
}
