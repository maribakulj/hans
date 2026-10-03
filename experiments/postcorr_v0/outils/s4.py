"""S4 — S3 contraint : rejet (retour à l'entrée) si distance(entrée, sortie S3) > ceil(beta × CER_estimé × len) + 1.
usage : python s4.py LIGNES.jsonl S3_SORTIES.jsonl CER_EST.json BETA SORTIE.jsonl"""
import json, sys, math
from rapidfuzz.distance import Levenshtein as L
lignes, s3, est, beta, sortie = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
R = {json.loads(l)['id']: json.loads(l) for l in open(lignes, encoding='utf-8')}; C = json.load(open(est)); n = rej = 0
with open(sortie, 'w', encoding='utf-8') as f:
    for l in open(s3, encoding='utf-8'):
        x = json.loads(l); r = R[x['id']]; b = math.ceil(beta * C[x['id']] * len(r['ocr'])) + 1; n += 1
        t = x['texte'] if L.distance(r['ocr'], x['texte']) <= b else r['ocr']; rej += t != x['texte']
        f.write(json.dumps({'id': x['id'], 'texte': t}, ensure_ascii=False) + '\n')
print(json.dumps({'lignes': n, 'taux_rejet': round(rej / n, 4)}))
