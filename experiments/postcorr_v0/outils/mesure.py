"""Métriques (§5) par strate, IC bootstrap par groupe documentaire. usage : python mesure.py LIGNES.jsonl SORTIES.jsonl [partition]"""
import json, sys, random, collections
from rapidfuzz.distance import Levenshtein as L
def wer(a, b): return L.distance(a.split(), b.split()) / max(1, len(b.split()))
def mesure(lignes, sorties, part='test', B=1000, graine=17):
    S = {}
    for l in open(sorties, encoding='utf-8'): x = json.loads(l); S[x['id']] = x['texte']
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]; R = [r for r in R if r['partition'] == part]
    res = {}
    for strate in ('propre', 'modere', 'lourd', 'tout'):
        X = [r for r in R if strate == 'tout' or r['strate'] == strate]
        if not X: continue
        par = collections.defaultdict(lambda: [0, 0, 0, 0, 0])            # éd. avant, éd. après, car GT, lignes dégradées, lignes
        bon = faux = laisse = 0; derive = []
        for r in X:
            h = S.get(r['id'], r['ocr']); a = L.distance(r['ocr'], r['gt']); b = L.distance(h, r['gt'])
            p = par[r['groupe']]; p[0] += a; p[1] += b; p[2] += len(r['gt']); p[3] += b > a; p[4] += 1
            derive.append(abs(len(h) - len(r['gt'])))
            # bilan des éditions : éditions du système (ocr→h) justes si elles rapprochent du GT
            e_sys = L.distance(r['ocr'], h)
            bon += max(0, a - b) if e_sys else 0; faux += max(0, b - a); laisse += min(a, b)
        G = list(par)
        def stat(gs):
            t = [sum(par[g][i] for g in gs) for i in range(5)]
            return t[0] / t[2], t[1] / t[2], t[3] / t[4]
        c0, c1, deg = stat(G); rng = random.Random(graine); bs = []
        for _ in range(B):
            s = [rng.choice(G) for _ in G]; x0, x1, d = stat(s); bs.append(((x0 - x1) / x0 if x0 else 0, d))
        bs.sort(key=lambda z: z[0]); red = [z[0] for z in bs]; dg = sorted(z[1] for z in bs)
        res[strate] = {'lignes': len(X), 'groupes': len(G), 'cer_avant': round(c0, 5), 'cer_apres': round(c1, 5),
                       'reduction_rel': round((c0 - c1) / c0, 4) if c0 else 0, 'ic95_reduction': [round(red[int(.025 * B)], 4), round(red[int(.975 * B)], 4)],
                       'taux_degradation': round(deg, 4), 'ic95_degradation': [round(dg[int(.025 * B)], 4), round(dg[int(.975 * B)], 4)],
                       'wer_avant': round(sum(wer(r['ocr'], r['gt']) for r in X) / len(X), 4), 'wer_apres': round(sum(wer(S.get(r['id'], r['ocr']), r['gt']) for r in X) / len(X), 4),
                       'editions_utiles': bon, 'editions_fausses': faux, 'erreurs_laissees': laisse, 'derive_longueur_p95': sorted(derive)[int(.95 * (len(derive) - 1))]}
    return res
if __name__ == '__main__':
    print(json.dumps(mesure(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'test'), ensure_ascii=False, indent=1))
