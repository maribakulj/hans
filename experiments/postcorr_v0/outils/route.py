"""S6 — routage : CER estimé < t1 → S0 (entrée) ; ≤ t2 → S2 ; sinon S4. usage : python route.py LIGNES CER_EST S2 S4 PARTITION t1 t2 SORTIE"""
import json, sys
L, C, s2, s4, part, t1, t2, out = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4], sys.argv[5], float(sys.argv[6]), float(sys.argv[7]), sys.argv[8]
lire = lambda f: {json.loads(l)['id']: json.loads(l)['texte'] for l in open(f, encoding='utf-8')}
A, B = lire(s2), lire(s4); n = {'S0': 0, 'S2': 0, 'S4': 0}
with open(out, 'w', encoding='utf-8') as f:
    for l in open(L, encoding='utf-8'):
        r = json.loads(l)
        if r['partition'] != part: continue
        c = C[r['id']]; k = 'S0' if c < t1 else 'S2' if c <= t2 else 'S4'; n[k] += 1
        f.write(json.dumps({'id': r['id'], 'texte': r['ocr'] if k == 'S0' else A[r['id']] if k == 'S2' else B[r['id']]}, ensure_ascii=False) + '\n')
print(json.dumps(n))
