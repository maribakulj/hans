from __future__ import annotations

from pathlib import Path

import pytest

ALTO_V4 = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Layout><Page ID="P1" WIDTH="1000" HEIGHT="200"><PrintSpace>
  <TextLine ID="L1" HPOS="100" VPOS="10" WIDTH="300" HEIGHT="40">
   <String CONTENT="de" HPOS="100" VPOS="10" WIDTH="18" HEIGHT="40"/>
   <SP/>
   <String CONTENT="la" HPOS="124" VPOS="10" WIDTH="17" HEIGHT="40"/>
   <SP/>
   <String CONTENT="Republique" HPOS="147" VPOS="10" WIDTH="253" HEIGHT="40"/>
  </TextLine>
  <TextLine ID="L2" HPOS="100" VPOS="60" WIDTH="200" HEIGHT="40">
   <String CONTENT="orphan" HPOS="100" VPOS="60" WIDTH="80" HEIGHT="40"/>
  </TextLine>
  <TextLine ID="L3" HPOS="100" VPOS="110" WIDTH="200" HEIGHT="40">
   <String CONTENT="no" VPOS="110" HEIGHT="40"/>
   <String CONTENT="geometry" HPOS="150" VPOS="110" WIDTH="50" HEIGHT="40"/>
  </TextLine>
 </PrintSpace></Page></Layout>
</alto>
"""

# Same content, no namespace at all -- corpus/37-GT-BNL ships like this and a
# prefix-bound reader silently returns zero lines for it.
ALTO_BARE = ALTO_V4.replace(' xmlns="http://www.loc.gov/standards/alto/ns-v4#"', "")


@pytest.fixture
def alto_v4(tmp_path: Path) -> Path:
    p = tmp_path / "v4.xml"
    p.write_text(ALTO_V4, encoding="utf-8")
    return p


@pytest.fixture
def alto_bare(tmp_path: Path) -> Path:
    p = tmp_path / "bare.xml"
    p.write_text(ALTO_BARE, encoding="utf-8")
    return p
