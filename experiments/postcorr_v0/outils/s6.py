"""S6 — estimateur de CER par ligne (encodeur CANINE de S2 gelé + régression) et routeur.
usage : python s6.py estime LIGNES.jsonl S2_DIR SORTIE.json   (prédictions de CER pour train/dev/test ; régresseur entraîné sur train)"""
import json, sys, os, random
import numpy as np, torch, torch.nn as nn
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2 import lot
from transformers import CanineModel
from scipy.stats import spearmanr
torch.set_num_threads(int(os.environ.get('FILS', '1'))); torch.manual_seed(17)
lignes, d2, sortie = sys.argv[2:5]
R = [json.loads(l) for l in open(lignes, encoding='utf-8')]
enc = CanineModel.from_pretrained(d2 + '/enc').eval(); E = []
with torch.no_grad():
    for k in range(0, len(R), 64):
        ids, m = lot([r['ocr'] for r in R[k:k + 64]]); h = enc(input_ids=ids, attention_mask=m).last_hidden_state
        E.append(((h * m[..., None]).sum(1) / m.sum(1, keepdim=True)).numpy())
X = torch.tensor(np.concatenate(E)); y = torch.tensor([r['cer'] for r in R], dtype=torch.float32)
tr = [i for i, r in enumerate(R) if r['partition'] == 'train']; dv = [i for i, r in enumerate(R) if r['partition'] == 'dev']
reg = nn.Sequential(nn.Linear(X.shape[1], 1)); opt = torch.optim.AdamW(reg.parameters(), lr=1e-3); best, etat = 1e9, None
for ep in range(200):
    random.Random(ep).shuffle(tr)
    for k in range(0, len(tr), 256):
        b = tr[k:k + 256]; loss = (reg(X[b]).squeeze(-1).sigmoid() - y[b]).abs().mean(); opt.zero_grad(); loss.backward(); opt.step()
    with torch.no_grad(): v = float((reg(X[dv]).squeeze(-1).sigmoid() - y[dv]).abs().mean())
    if v < best: best, etat = v, {k: t.clone() for k, t in reg.state_dict().items()}
reg.load_state_dict(etat)
with torch.no_grad(): p = reg(X).squeeze(-1).sigmoid().numpy()
out = {r['id']: float(v) for r, v in zip(R, p)}; json.dump(out, open(sortie, 'w'))
strate = lambda c: 'propre' if c < .02 else 'modere' if c <= .15 else 'lourd'
for part in ('dev', 'test'):
    I = [i for i, r in enumerate(R) if r['partition'] == part]
    rho = spearmanr([R[i]['cer'] for i in I], [p[i] for i in I]).correlation
    cm = {(a, b): 0 for a in ('propre', 'modere', 'lourd') for b in ('propre', 'modere', 'lourd')}
    for i in I: cm[(R[i]['strate'], strate(p[i]))] += 1
    print(part, 'Spearman', round(rho, 3), 'MAE', round(float(np.abs(p[I] - y.numpy()[I]).mean()), 4), {f'{a}->{b}': v for (a, b), v in cm.items()})
