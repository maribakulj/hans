"""B0 — pseudo-lignes OCR/GT alignées, découpage par groupe documentaire, strates. usage : python prepare.py HIPE_DATA SORTIE"""
import glob, hashlib, json, os, re, sys, collections
from rapidfuzz.distance import Levenshtein as L
def groupe(r):
    m = r['document_metadata']; f = m['primary_dataset_filename']
    g = re.search(r'(fr_[a-z]+-\d+)', f)
    return m['primary_dataset_name'] + ':' + (g.group(1) if g else m['document_id'])
def partition(g):
    v = int(hashlib.sha256(g.encode()).hexdigest(), 16) % 10
    return 'test' if v < 2 else 'dev' if v == 2 else 'train'
def pseudo_lignes(ocr, gt, mn=50, mx=80):
    """coupe gt aux espaces (50-80 car.) ; projette les coupures sur ocr via l'alignement d'édition"""
    ops = L.editops(gt, ocr)                       # transforme gt → ocr
    # carte position gt → position ocr (début de caractère)
    carte = []; i = j = 0; k = 0; ops = list(ops)
    while i <= len(gt):
        while k < len(ops) and ops[k].src_pos == i and ops[k].tag == 'insert': j += 1; k += 1
        carte.append(j)
        if i == len(gt): break
        if k < len(ops) and ops[k].src_pos == i and ops[k].tag == 'delete': i += 1; k += 1; continue
        if k < len(ops) and ops[k].src_pos == i and ops[k].tag == 'replace': k += 1
        i += 1; j += 1
    cuts, d = [0], 0
    while len(gt) - d > mx:
        e = gt.rfind(' ', d + mn, d + mx + 1)
        if e < 0: e = gt.find(' ', d + mx)
        if e < 0: break
        cuts.append(e + 1); d = e + 1
    cuts.append(len(gt))
    out = []
    for a, b in zip(cuts, cuts[1:]):
        g = gt[a:b].strip(); o = ocr[carte[a]:carte[b]].strip()
        if g: out.append((o, g))
    return out
def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    F = [f for f in glob.glob(src + '/icdar2017/fr/*.jsonl') + glob.glob(src + '/impresso-snippets/fr/*.jsonl') if 'masked' not in f]
    rows, ex = [], collections.Counter()
    for f in sorted(F):
        for l in open(f, encoding='utf-8'):
            r = json.loads(l); gt = r['ground_truth']['transcription_unit']; ocr = r['ocr_hypothesis']['transcription_unit']
            if not gt.strip(): ex['gt vide'] += 1; continue
            g = groupe(r); p = partition(g)
            for k, (o, t) in enumerate(pseudo_lignes(ocr, gt)):
                c = L.distance(o, t) / max(1, len(t)); ratio = len(o) / max(1, len(t))
                if not 0.5 <= ratio <= 2 or c > 0.6: ex['écartée (ratio/CER)'] += 1; continue
                s = 'propre' if c < 0.02 else 'modere' if c <= 0.15 else 'lourd'
                rows.append({'id': f"{r['document_metadata']['document_id']}_{k}", 'groupe': g, 'partition': p, 'date': r['document_metadata'].get('date'),
                             'ocr': o, 'gt': t, 'cer': round(c, 4), 'strate': s})
    with open(dst + '/lignes.jsonl', 'w', encoding='utf-8') as w:
        for x in rows: w.write(json.dumps(x, ensure_ascii=False) + '\n')
    st = collections.Counter((x['partition'], x['strate']) for x in rows); gp = collections.defaultdict(set)
    for x in rows: gp[x['partition']].add(x['groupe'])
    rep = {'exclusions': dict(ex), 'groupes': {k: len(v) for k, v in gp.items()},
           'lignes': {p: {s: st[(p, s)] for s in ('propre', 'modere', 'lourd')} for p in ('train', 'dev', 'test')},
           'cer_moyen_par_partition': {p: round(sum(x['cer'] for x in rows if x['partition'] == p) / max(1, sum(1 for x in rows if x['partition'] == p)), 4) for p in ('train', 'dev', 'test')}}
    json.dump(rep, open(dst + '/stats.json', 'w'), ensure_ascii=False, indent=1); print(json.dumps(rep, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
