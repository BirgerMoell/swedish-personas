"""Check the surname tilt against SCB's own numbers.

Usage: python3 src/test_surname_tilt.py
For the 25 surnames in SCB's landsdel table, compares the regional factor the sampler implies with the
measured one, checks that national frequencies do not move, and lists what the look-alike rule does to
other names. Exits with an error if a measured name is off by more than 15%.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from structure import Structure
from surname_tilt import SurnameTilt, LANDSDEL

s, t = Structure(), SurnameTilt()
tables = s.surnames_by_landsdel
tot = {k: tables[k].cum[-1] for k in LANDSDEL}
base = s.surname_counts["SV"]
btot = sum(base.values())
def p(k, name):
    i = tables[k].items.index(name); w = tables[k].cum[i] - (tables[k].cum[i - 1] if i else 0)
    return w / tot[k]
names = {n.casefold(): n for n in base}
bad = 0
print(f"{'name':12} {'measured G/S/N':>22} {'sampled G/S/N':>22}")
for key, f in t.measured.items():
    name = names.get(key)
    if not name:
        print(key, "missing from the national surname list"); continue
    nat = sum(t.share[k] * p(k, name) for k in LANDSDEL)
    got = {k: p(k, name) / nat for k in LANDSDEL}
    drift = nat / (base[name] / btot) - 1
    off = max(abs(got[k] / f[k] - 1) for k in LANDSDEL)
    bad += off > 0.15
    print(f"{name:12} {f['G']:6.2f}{f['S']:7.2f}{f['N']:7.2f}   {got['G']:6.2f}{got['S']:7.2f}{got['N']:7.2f}   national share drift {drift:+.1%}")
print("\nlook-alike names (assumption, half strength):")
for name in ("Lindström", "Bergström", "Lundgren", "Edlund", "Forslund", "Gustafsson", "Svensson", "Andersson", "Eriksson", "Karlsson", "Persson"):
    if name in base:
        f = t.factors(name); print(f"{name:12} G {f['G']:.2f}  S {f['S']:.2f}  N {f['N']:.2f}")
print("\nclass strength: nature-north", {k: round(2.718 ** v, 2) for k, v in t.north.items()})
sys.exit(1 if bad else 0)
