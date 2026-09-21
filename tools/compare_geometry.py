import json, sys
sys.path.insert(0,"/Users/marcel/hans/src"); sys.path.insert(0,"/tmp")
from PIL import Image, ImageDraw
from hans.alto import read_page_lines
from hans.geometry import GeometryRequest
from hans.resolvers import ProportionalResolver, CTCCutsResolver
from hans.resolvers.proportional import is_space_token
from pagelib import lines_of

PAGE="Descartes1637_Discours_btv1b86069594_corrected_0015"
d=f"/Users/marcel/corpus-vt/raw/{PAGE}"
corr=json.load(open("/tmp/vt_corrected.json"))[PAGE]
L={l.line_id:l for l in read_page_lines(f"{d}/src.page.xml")}
SRC=dict(lines_of(f"{d}/src.page.xml"))
cor=dict(zip(corr["ids"], corr["lines"]))
ctc=CTCCutsResolver.from_cache(f"/tmp/cuts_vt/{PAGE}.json"); prop=ProportionalResolver()
im=Image.open(f"{d}/image.png").convert("RGB")

def boundaries(boxes):
    return [ (b.hpos+b.hpos+b.width)//2 for b in boxes if is_space_token(b.text) ]

rows=[]
for lid,ln in L.items():
    c=cor.get(lid)
    if not c or len(c.split())<=len(SRC[lid].split()): continue
    toks=[]
    for k,w in enumerate(c.split()):
        if k: toks.append(" ")
        toks.append(w)
    req=GeometryRequest(hpos=ln.hpos,width=ln.width,tokens=tuple(toks),line_id=lid,
                        vpos=ln.vpos,height=ln.height)
    try: bc,bp=ctc.resolve(req), prop.resolve(req)
    except Exception: continue
    rows.append((ln, boundaries(bc), boundaries(bp), c))

# ---------- A : superposition, un seul crop, regles verticales ----------
tiles=[]
for ln,cb,pb,c in rows[:4]:
    PAD=4
    crop=im.crop((ln.hpos-2,ln.vpos-PAD,ln.hpos+ln.width+2,ln.vpos+ln.height+PAD))
    t=Image.new("RGB",(crop.width,crop.height+16),"white"); t.paste(crop,(0,14))
    dr=ImageDraw.Draw(t); ox=ln.hpos-2; h=crop.height
    for x in cb: dr.line([(x-ox,14),(x-ox,14+h//2)], fill=(0,90,255), width=3)
    for x in pb: dr.line([(x-ox,14+h//2),(x-ox,14+h)], fill=(215,0,0), width=3)
    dr.text((3,2),"haut = CTC (bleu)   bas = proportionnel (rouge)",fill=(0,0,0))
    tiles.append(t)
W=max(t.width for t in tiles); H=sum(t.height+8 for t in tiles)
A=Image.new("RGB",(W,H),"white"); y=0
for t in tiles: A.paste(t,(0,y)); y+=t.height+8
A.save("/tmp/mode_A.png"); print("A:",A.size)

# ---------- B : zoom sur les DESACCORDS seulement ----------
wins=[]
for ln,cb,pb,c in rows:
    for xc,xp in zip(cb,pb):
        if abs(xc-xp) < 15: continue          # d'accord : rien a voir
        mid=(xc+xp)//2; half=max(70, abs(xc-xp))
        x0,x1=max(0,mid-half), min(im.size[0], mid+half)
        PAD=4
        crop=im.crop((x0,ln.vpos-PAD,x1,ln.vpos+ln.height+PAD))
        if crop.width<10: continue
        crop=crop.resize((crop.width*2, crop.height*2), Image.LANCZOS)
        t=Image.new("RGB",(crop.width,crop.height+16),"white"); t.paste(crop,(0,0))
        dr=ImageDraw.Draw(t); h=crop.height
        dr.line([((xc-x0)*2,0),((xc-x0)*2,h)], fill=(0,90,255), width=4)
        dr.line([((xp-x0)*2,0),((xp-x0)*2,h)], fill=(215,0,0), width=4)
        dr.text((3,h+2), f"ecart {abs(xc-xp)} px", fill=(0,0,0))
        wins.append(t)
wins=wins[:8]
if wins:
    cols=2; rowsn=(len(wins)+cols-1)//cols
    cw=max(t.width for t in wins); chh=max(t.height for t in wins)
    B=Image.new("RGB",(cw*cols+12, chh*rowsn+12*rowsn),"white")
    for i,t in enumerate(wins):
        B.paste(t, ((i%cols)*(cw+8), (i//cols)*(chh+12)))
    B.save("/tmp/mode_B.png"); print("B:",B.size,f"({len(wins)} desaccords)")
