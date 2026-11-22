import pathlib, xml.etree.ElementTree as ET
root=pathlib.Path("sdk/foobar2000/foo_sample")
(root/"dsp_sample.cpp").write_bytes(pathlib.Path("lns30/foobar/dsp_lns30.cpp").read_bytes())
(root/"lns30.hpp").write_bytes(pathlib.Path("lns30/lns30.hpp").read_bytes())
(root/"main.cpp").write_text('''#include "stdafx.h"
DECLARE_COMPONENT_VERSION("LNS30 Experimental", "0.1.0", "Experimental 20-bit PCM noise shaper; NOT validated against HQPlayer LNS15.");
VALIDATE_COMPONENT_FILENAME("foo_lns30.dll");
FOOBAR2000_IMPLEMENT_CFG_VAR_DOWNGRADE;
''',encoding="utf-8")
project=root/"foo_sample.vcxproj"
ET.register_namespace("", "http://schemas.microsoft.com/developer/msbuild/2003")
tree=ET.parse(project)
ns="{http://schemas.microsoft.com/developer/msbuild/2003}"
for group in tree.getroot().findall(f"{ns}ItemGroup"):
    for elem in list(group):
        if elem.tag in {f"{ns}ClCompile",f"{ns}ResourceCompile"}:
            name=elem.get("Include", "").lower().replace("\\","/")
            if name not in {"main.cpp","dsp_sample.cpp","pch.cpp"}:
                group.remove(elem)
tree.write(project,encoding="utf-8",xml_declaration=True)
print("Configured foo_sample project to include LNS30 DSP only.")
