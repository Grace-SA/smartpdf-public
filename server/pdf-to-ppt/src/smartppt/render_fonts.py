"""Use exactly the approved static variant in local rendering and the PPT file."""
import hashlib
import struct
import zipfile
from pathlib import Path
from lxml import etree as ET
from .font_embedding import bundled_payloads,CMU_FACES

from .base_font import FAMILY as BASE_FAMILY
from .termes_font import FAMILY as TERMES_FAMILY
from .light_font import FAMILY as LIGHT_FAMILY
VARIANTS=('SmartPDF Sans100','SmartPDF Serif200',BASE_FAMILY,TERMES_FAMILY,LIGHT_FAMILY,*CMU_FACES)

def materialize_variant_fonts(files,folder):
    required=set()
    for path in files:
        with zipfile.ZipFile(path) as package:
            for name in package.namelist():
                if name.startswith('ppt/slides/') and name.endswith('.xml'):
                    data=package.read(name)
                    root=ET.fromstring(data,ET.XMLParser(resolve_entities=False,no_network=True))
                    required.update(node.get('typeface') for node in root.iter() if node.get('typeface') in VARIANTS)
    if not required:return None
    directory=Path(folder)/'approved-static-fonts';directory.mkdir(exist_ok=True)
    for family in sorted(required):
        payloads=(bundled_payloads(False,family,styles={'regular','bold','italic','boldItalic'})
                  if family==TERMES_FAMILY or family in CMU_FACES else bundled_payloads(False,family))
        for payload in payloads.values():
            size=struct.unpack_from('<I',payload,4)[0];data=payload[-size:]
            target=directory/(hashlib.sha256(data).hexdigest()+'.ttf')
            if not target.exists():target.write_bytes(data)
    return directory


def variant_fontconfig_rules():
    # PPT represents these static weights as regular faces of distinct families.
    # Fontconfig's default regular weight otherwise selects the variable 400
    # instance even when the requested family is the static thin variant.
    return ''.join('<match target="pattern"><test name="family" compare="eq"><string>'+family+
        '</string></test><edit name="weight" mode="assign" binding="strong"><int>'+str(weight)+
        '</int></edit></match>' for family,weight in [('SmartPDF Sans100',0),('SmartPDF Serif200',40)])

