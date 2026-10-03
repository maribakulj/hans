import json, sys, random
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from contrat import applique, editions, Edit
R = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
err = 0
for r in R:
    if r['partition'] != 'train': continue
    e = editions(r['ocr'], r['gt'])
    if applique(r['ocr'], e) != r['gt']: err += 1
    if any(a.end > b.start for a, b in zip(e, e[1:])): err += 1
try: applique('abc', [Edit(0, 2, 'x'), Edit(1, 3, 'y')]); err += 1
except AssertionError: pass
assert applique('abc', [Edit(1, 1, 'Z')]) == 'aZbc' and applique('abc', [Edit(0, 3, '')]) == ''
print('aller-retour source + éditions = cible sur train :', 'OK' if not err else f'{err} erreurs'); sys.exit(1 if err else 0)
