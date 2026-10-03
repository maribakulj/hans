"""S3 — ByT5-small affiné OCR → GT (seq2seq libre, L58). Reprise par époque.
usage : python s3.py entraine LIGNES.jsonl DOSSIER ; python s3.py predit LIGNES.jsonl DOSSIER PARTITION SORTIE.jsonl [ids.json]"""
import json, sys, os, time, random
import torch
from transformers import T5ForConditionalGeneration, AutoTokenizer
B5 = '/tmp/claude-0/-home-user-BBVLM/84210bd8-ec20-5b45-a7f8-f35608b01c8d/scratchpad/pc/modeles/byt5-small'
torch.set_num_threads(int(os.environ.get('FILS', '4')))
def entraine(lignes, d, epoques=2, lr=3e-4, bs=16, graine=17):
    torch.manual_seed(graine); tok = AutoTokenizer.from_pretrained(B5)
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]; tr = [r for r in R if r['partition'] == 'train']
    debut = json.load(open(d + '/epoques.json'))['faites'] if os.path.exists(d + '/epoques.json') else 0
    mod = T5ForConditionalGeneration.from_pretrained(d + '/modele' if debut else B5); os.makedirs(d, exist_ok=True)
    opt = torch.optim.AdamW(mod.parameters(), lr=lr); t0 = time.time(); pas = 0
    for ep in range(debut, epoques):
        o = list(range(len(tr))); random.Random(graine + ep).shuffle(o); mod.train()
        for k in range(0, len(o), bs):
            X = [tr[i]['ocr'] for i in o[k:k + bs]]; Y = [tr[i]['gt'] for i in o[k:k + bs]]
            x = tok(X, return_tensors='pt', padding=True, truncation=True, max_length=256)
            y = tok(Y, return_tensors='pt', padding=True, truncation=True, max_length=256).input_ids; y[y == tok.pad_token_id] = -100
            loss = mod(**x, labels=y).loss; opt.zero_grad(); loss.backward(); opt.step(); pas += 1
            if pas % 50 == 0: print(f'ep {ep} pas {pas} perte {loss.item():.4f} {time.time() - t0:.0f}s', flush=True)
        mod.save_pretrained(d + '/modele'); json.dump({'faites': ep + 1}, open(d + '/epoques.json', 'w'))
def predit(lignes, d, part, sortie, ids=None, bs=32):
    tok = AutoTokenizer.from_pretrained(B5); mod = T5ForConditionalGeneration.from_pretrained(d + '/modele').eval()
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]; X = [r for r in R if r['partition'] == part]
    if ids: S = set(json.load(open(ids))); X = [r for r in X if r['id'] in S]
    out = open(sortie, 'w', encoding='utf-8'); t0 = time.time()
    for k in range(0, len(X), bs):
        b = [r['ocr'] for r in X[k:k + bs]]; x = tok(b, return_tensors='pt', padding=True, truncation=True, max_length=256)
        with torch.no_grad(): g = mod.generate(**x, max_new_tokens=int(x.input_ids.shape[1] * 1.3) + 8, num_beams=1)
        for r, t in zip(X[k:k + bs], tok.batch_decode(g, skip_special_tokens=True)): out.write(json.dumps({'id': r['id'], 'texte': t}, ensure_ascii=False) + '\n')
        out.flush()
    print(json.dumps({'lignes': len(X), 's_par_1000_lignes': round((time.time() - t0) / max(1, len(X)) * 1000, 1)}))
if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'entraine': entraine(a[2], a[3])
    else: predit(a[2], a[3], a[4], a[5], a[6] if len(a) > 6 else None)
