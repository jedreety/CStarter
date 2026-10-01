workspace "Atelier"
   configurations { "Debug", "Release" }
   platforms { "x64" }
   location "build"

project "outils"
   kind "StaticLib"
   language "C++"
   cppdialect "C++17"
   files { "outils/include/**.h", "outils/src/**.cpp" }
   includedirs { "outils/include" }
   defines { "OUTILS_INTERNE" }
   filter "configurations:Debug"
      symbols "On"
   filter "configurations:Release"
      optimize "On"

project "demo"
   kind "ConsoleApp"
   language "C++"
   cppdialect "C++17"
   files { "demo/**.cpp" }
   includedirs { "outils/include" }
   links { "outils" }
   filter "configurations:Debug"
      symbols "On"
   filter "configurations:Release"
      optimize "On"
