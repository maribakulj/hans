"""S2 — étiqueteur d'éditions au caractère (CANINE-s), GECToR-like (L57).
Étiquette par caractère source (position 0 = [CLS] pour les insertions en tête) : base ∈ {K, D, R:c} + ajout optionnel « +A:chaîne ».
usage : python s2.py entraine LIGNES.jsonl MODELE_DIR ; python s2.py predit LIGNES.jsonl MODELE_DIR PARTITION SEUIL SORTIE.jsonl"""
import json, sys, time, random, collections, os
import torch, torch.nn as nn
from rapidfuzz.distance import Levenshtein as L
from transformers import CanineModel
C = '/tmp/claude-0/-home-user-BBVLM/84210bd8-ec20-5b45-a7f8-f35608b01c8d/scratchpad/pc/modeles/canine-s'
CLS, SEP, PAD = 0xE000, 0xE001, 0
def etiquettes(s, t):
    """une étiquette par position : 0 = tête, i+1 = caractère s[i]"""
    base = ['K'] * (len(s) + 1); ajout = [''] * (len(s) + 1)
    for op in L.opcodes(s, t):
        a, b, c, d = op.src_start, op.src_end, op.dest_start, op.dest_end
        if op.tag == 'equal': continue
        if op.tag == 'insert': ajout[a] += t[c:d]; continue         # après s[a-1] (ou en tête si a = 0)
        if op.tag == 'delete':
            for i in range(a, b): base[i + 1] = 'D'
            continue
        n = min(b - a, d - c)                                         # replace : 1:1 puis surplus
        for k in range(n): base[a + k + 1] = 'R:' + t[c + k]
        for i in range(a + n, b): base[i + 1] = 'D'
        if d - c > n: ajout[a + n] += t[c + n:d]
    return [b + ('+A:' + x if x else '') for b, x in zip(base, ajout)]
def applique(s, labs):
    out = [labs[0].split('+A:', 1)[1] if '+A:' in labs[0] else '']
    for ch, l in zip(s, labs[1:]):
        b, _, x = l.partition('+A:')
        out.append('' if b == 'D' else b[2:] if b.startswith('R:') else ch); out.append(x)
    return ''.join(out)
def codes(s): return [CLS] + [ord(c) for c in s] + [SEP]
class Etiqueteur(nn.Module):
    def __init__(self, n):
        super().__init__(); self.enc = CanineModel.from_pretrained(C); self.tete = nn.Linear(self.enc.config.hidden_size, n)
    def forward(self, ids, masque): return self.tete(self.enc(input_ids=ids, attention_mask=masque).last_hidden_state)
def lot(textes):
    X = [codes(s) for s in textes]; n = max(len(x) for x in X); n = max(n, 4)
    ids = torch.tensor([x + [PAD] * (n - len(x)) for x in X]); m = (ids != PAD).long(); return ids, m
def entraine(lignes, dossier, K_cov=0.95, epoques=3, lr=5e-5, bs=32, graine=17):
    torch.manual_seed(graine); random.seed(graine); torch.set_num_threads(int(os.environ.get('FILS', '4')))
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]; tr = [r for r in R if r['partition'] == 'train']
    E = [etiquettes(r['ocr'], r['gt']) for r in tr]
    cnt = collections.Counter(l for e in E for l in e if l != 'K'); tot = sum(cnt.values()); voc = ['K']; acc = 0
    for l, c in cnt.most_common():
        if acc / tot >= K_cov: break
        voc.append(l); acc += c
    idx = {l: i for i, l in enumerate(voc)}
    couv = sum(c for l, c in cnt.items() if l in idx) / tot
    os.makedirs(dossier, exist_ok=True); json.dump({'vocabulaire': voc, 'couverture': couv, 'editions_train': tot}, open(dossier + '/voc.json', 'w'), ensure_ascii=False)
    print('vocabulaire', len(voc), 'couverture', round(couv, 4), flush=True)
    mod = Etiqueteur(len(voc)); debut = 0
    if os.path.exists(dossier + '/epoques.json'):                     # reprise après redémarrage du conteneur
        debut = json.load(open(dossier + '/epoques.json'))['faites']
        mod.enc = CanineModel.from_pretrained(dossier + '/enc'); mod.tete.load_state_dict(torch.load(dossier + '/tete.pt'))
        print('reprise à l époque', debut, flush=True)
    opt = torch.optim.AdamW(mod.parameters(), lr=lr)
    ordre = list(range(len(tr))); t0 = time.time(); pas = 0
    for ep in range(debut, epoques):
        random.Random(graine + ep).shuffle(ordre); mod.train()
        for k in range(0, len(ordre), bs):
            B = ordre[k:k + bs]; ids, m = lot([tr[i]['ocr'] for i in B]); n = ids.shape[1]
            y = torch.full((len(B), n), -100, dtype=torch.long)
            for j, i in enumerate(B):
                e = E[i]; y[j, :len(e)] = torch.tensor([idx.get(l, 0) for l in e])
            loss = nn.functional.cross_entropy(mod(ids, m).reshape(-1, len(voc)), y.reshape(-1), ignore_index=-100)
            opt.zero_grad(); loss.backward(); opt.step(); pas += 1
            if pas % 50 == 0: print(f'ep {ep} pas {pas} perte {loss.item():.4f} {time.time() - t0:.0f}s', flush=True)
        torch.save(mod.tete.state_dict(), dossier + '/tete.pt'); mod.enc.save_pretrained(dossier + '/enc')
        json.dump({'faites': ep + 1}, open(dossier + '/epoques.json', 'w'))
    json.dump({'pas': pas, 's_entrainement': round(time.time() - t0)}, open(dossier + '/entrainement.json', 'w'))
def predit(lignes, dossier, part, seuil, sortie, passes=3, bs=64):
    torch.set_num_threads(int(os.environ.get('FILS', '4')))
    voc = json.load(open(dossier + '/voc.json'))['vocabulaire']
    mod = Etiqueteur(len(voc)); mod.enc = CanineModel.from_pretrained(dossier + '/enc'); mod.tete.load_state_dict(torch.load(dossier + '/tete.pt')); mod.eval()
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]; X = [r for r in R if r['partition'] == part]
    cur = [r['ocr'] for r in X]; t0 = time.time()
    for _ in range(passes):
        chg = 0
        for k in range(0, len(cur), bs):
            ids, m = lot(cur[k:k + bs])
            with torch.no_grad(): p = mod(ids, m).softmax(-1)
            pr, am = p.max(-1)
            for j in range(len(ids)):
                s = cur[k + j]; labs = []
                for q in range(len(s) + 1):
                    l = voc[am[j, q]] if pr[j, q] >= seuil else 'K'; labs.append(l)
                n = applique(s, labs)
                if n != s: chg += 1; cur[k + j] = n
        if not chg: break
    with open(sortie, 'w', encoding='utf-8') as f:
        for r, t in zip(X, cur): f.write(json.dumps({'id': r['id'], 'texte': t}, ensure_ascii=False) + '\n')
    print(json.dumps({'lignes': len(X), 's_par_1000_lignes': round((time.time() - t0) / len(X) * 1000, 1)}))
if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'entraine': entraine(a[2], a[3])
    else: predit(a[2], a[3], a[4], float(a[5]), a[6])
