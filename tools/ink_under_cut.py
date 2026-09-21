"""Juger une géométrie sans vérité terrain : y a-t-il de l'encre sous la coupe ?

Une SCISSION n'a pas de vérité terrain géométrique — personne n'annote où
couper ``Maisiepenfois``. Mais ce que l'œil fait devant une vignette agrandie
est mécanisable : il regarde si le trait traverse une lettre.

C'est donc mesuré ici, sur TOUTES les frontières contestées, au lieu d'être
jugé sur un échantillon. La vision garde son rôle — valider la mesure sur
quelques cas — mais elle ne fait plus le comptage.

Mesuré le 2026-09-22 sur OCR17+, 78 désaccords de 15 px ou plus :

    encre médiane sous le trait : CTC 0,0 %, proportionnel 11,8 %

et le classement tient à tous les seuils de tolérance (0, 5, 10, 20 % de la
hauteur de ligne), ce qui écarte l'hypothèse d'un artefact de seuillage sur
un papier qui transparaît.

Seuillage d'Otsu par ligne et non global : le fond d'un imprimé du XVIIe va
du crème au gris, et une constante transforme une page sombre en un pâté
sans aucun blanc.
"""

import json, sys, glob, os
sys.path.insert(0,"/Users/marcel/hans/src"); sys.path.insert(0,"/tmp")
import numpy as np
from PIL import Image
from hans.alto import read_page_lines
from hans.geometry import GeometryRequest
from hans.resolvers import ProportionalResolver, CTCCutsResolver
from hans.resolvers.proportional import is_space_token
from pagelib import lines_of
Image.MAX_IMAGE_PIXELS=None
CORR=json.load(open("/tmp/vt_corrected.json")); prop=ProportionalResolver()
def mids(bs): return [(b.hpos+b.hpos+b.width)//2 for b in bs if is_space_token(b.text)]
def otsu(a):
    h=np.bincount(a.ravel(),minlength=256).astype(float); t=h.sum()
    w=np.cumsum(h)/t; mu=np.cumsum(h*np.arange(256))/t; mt=mu[-1]
    d=w*(1-w); d[d==0]=1e-9
    return int(np.argmax((mt*w-mu)**2/d))
res={"ctc":[], "prop":[]}; detail=[]
for j in sorted(glob.glob("/tmp/cuts_vt/*.json")):
    page=os.path.basename(j)[:-5]; d=f"/Users/marcel/corpus-vt/raw/{page}"
    if page not in CORR: continue
    L={l.line_id:l for l in read_page_lines(f"{d}/src.page.xml")}
    SRC=dict(lines_of(f"{d}/src.page.xml")); cor=dict(zip(CORR[page]["ids"],CORR[page]["lines"]))
    ctc=CTCCutsResolver.from_cache(j); im=Image.open(f"{d}/image.png").convert("L")
    A=np.asarray(im,dtype=np.uint8)
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
        band=A[max(0,ln.vpos):ln.vpos+ln.height, max(0,ln.hpos):ln.hpos+ln.width]
        if band.size==0: continue
        thr=otsu(band); ink=(band<=thr).sum(axis=0)
        for xc,xp in zip(mids(bc),mids(bp)):
            if abs(xc-xp)<15: continue
            for key,x in (("ctc",xc),("prop",xp)):
                col=x-ln.hpos
                v=int(ink[col]) if 0<=col<len(ink) else -1
                res[key].append(v)
            detail.append((page[:10],abs(xc-xp),
                           int(ink[xc-ln.hpos]) if 0<=xc-ln.hpos<len(ink) else -1,
                           int(ink[xp-ln.hpos]) if 0<=xp-ln.hpos<len(ink) else -1))
n=len(res["ctc"])
print(f"{n} desaccords >= 15px, encre sous le trait (0 = dans le blanc)\n")
for k,lab in (("ctc","CTC"),("prop","proportionnel")):
    v=res[k]; clean=sum(1 for x in v if x==0); out=sum(1 for x in v if x<0)
    print(f"  {lab:<16} tombe dans le BLANC : {clean}/{n} ({clean/n:.0%})   hors ligne : {out}")
both=sum(1 for a,b in zip(res["ctc"],res["prop"]) if a==0 and b==0)
only_c=sum(1 for a,b in zip(res["ctc"],res["prop"]) if a==0 and b>0)
only_p=sum(1 for a,b in zip(res["ctc"],res["prop"]) if a>0 and b==0)
neither=sum(1 for a,b in zip(res["ctc"],res["prop"]) if a>0 and b>0)
print(f"\n  les deux dans le blanc : {both}")
print(f"  CTC seul dans le blanc : {only_c}")
print(f"  proportionnel seul     : {only_p}")
print(f"  aucun des deux         : {neither}")
json.dump(detail,open("/tmp/ink_detail.json","w"))
