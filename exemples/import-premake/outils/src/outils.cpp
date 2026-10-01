#include "outils.h"

#ifndef OUTILS_INTERNE
#error "OUTILS_INTERNE manque : le define de Premake n'a pas été repris"
#endif

int tripler(int valeur)
{
    return valeur * 3;
}
