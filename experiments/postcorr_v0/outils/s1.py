"""S1 — canal bruité (§4) : candidats lexicaux à distance ≤ 2, P_canal (confusions train) + λ·LM caractères 6-gramme (Witten-Bell).
usage : python s1.py LIGNES.jsonl PARTITION SORTIE.jsonl [lambda] [seuil]"""
import json, sys, math, re, collections, time
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein as L
N = 6
class LM:
    def __init__(self, textes):
        self.c = collections.Counter(); self.ctx = collections.Counter(); self.typ = collections.defaultdict(set); V = set()
        for t in textes:
            t = '\x02' * (N - 1) + t + '\x03'; V.update(t)
            for i in range(N - 1, len(t)):
                for k in range(N):
                    h = t[i - k:i]; self.c[(h, t[i])] += 1; self.ctx[h] += 1; self.typ[h].add(t[i])
        self.V = len(V) + 1
    def p(self, h, ch):
        if not h: return (self.c[('', ch)] + 1) / (self.ctx[''] + self.V)
        n, T = self.ctx[h], len(self.typ.get(h, ()))
        lo = self.p(h[1:], ch)
        return (self.c[(h, ch)] + T * lo) / (n + T) if n else lo
    def logp(self, t):
        t = '\x02' * (N - 1) + t + '\x03'
        return sum(math.log(self.p(t[i - N + 1:i], t[i])) for i in range(N - 1, len(t)))
def canal(train):
    """log P(ocr_mot | gt_mot) ≈ somme des log-probabilités d'éditions de caractères estimées sur train"""
    sub = collections.Counter(); tot = collections.Counter(); ins = 0; dels = 0; n = 0
    for r in train:
        for op in L.editops(r['gt'], r['ocr']):
            if op.tag == 'replace': sub[(r['gt'][op.src_pos], r['ocr'][op.dest_pos])] += 1
            elif op.tag == 'insert': ins += 1
            else: dels += 1
        for ch in r['gt']: tot[ch] += 1; n += 1
    def lp(g, o):
        s = 0.0
        for op in L.editops(g, o):
            if op.tag == 'replace': s += math.log((sub[(g[op.src_pos], o[op.dest_pos])] + 0.1) / (tot[g[op.src_pos]] + 1))
            elif op.tag == 'insert': s += math.log((ins + 1) / (n + 1))
            else: s += math.log((dels + 1) / (n + 1))
        return s
    return lp
MOT = re.compile(r"[\wſ'’-]+")
def main(lignes, part, sortie, lam=1.0, seuil=0.0):
    R = [json.loads(l) for l in open(lignes, encoding='utf-8')]
    train = [r for r in R if r['partition'] == 'train']
    t0 = time.time(); lm = LM([r['gt'] for r in train]); lp = canal(train)
    lex = collections.Counter(w for r in train for w in MOT.findall(r['gt']))
    lexl = list(lex); cache = {}; t_prep = time.time() - t0; t0 = time.time()
    X = [r for r in R if r['partition'] == part]; out = open(sortie, 'w', encoding='utf-8')
    for r in X:
        s = r['ocr']; edits = []
        for m in MOT.finditer(s):
            w = m.group(0)
            if lex[w] >= 2 or len(w) < 3: continue
            if w not in cache:
                cache[w] = [c for c, d, _ in process.extract(w, lexl, scorer=L.distance, score_cutoff=2, limit=20) if c != w]
            if not cache[w]: continue
            a, b = max(0, m.start() - 20), min(len(s), m.end() + 20)
            base = lm.logp(s[a:b])
            best, bs = None, seuil
            for c in cache[w]:
                sc = lp(c, w) + math.log(lex[c] + 1) * 0 + lam * (lm.logp(s[a:m.start()] + c + s[m.end():b]) - base)
                if sc > bs: best, bs = c, sc
            if best: edits.append((m.start(), m.end(), best))
        t = s
        for a, b, c in sorted(edits, reverse=True): t = t[:a] + c + t[b:]
        out.write(json.dumps({'id': r['id'], 'texte': t, 'editions': [[a, b, c] for a, b, c in edits]}, ensure_ascii=False) + '\n')
    print(json.dumps({'lignes': len(X), 's_prep': round(t_prep, 1), 's_par_1000_lignes': round((time.time() - t0) / len(X) * 1000, 1)}))
if __name__ == '__main__':
    a = sys.argv; main(a[1], a[2], a[3], float(a[4]) if len(a) > 4 else 1.0, float(a[5]) if len(a) > 5 else 0.0)
