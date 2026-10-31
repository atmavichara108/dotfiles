"""Диаг-6 финал: токенизация кириллицы (обход utf8-дефекта привязки: bytes ОК)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lab9

llm = lab9.model()

def tok_ids(text):
    return llm.tokenize(text.encode("utf-8"), add_bos=False, special=True)

ru_s = "Собака гуляет в парке"
ru_ids = tok_ids(ru_s)
en_ids = tok_ids("A dog walks in the park")
pieces = [llm.detokenize([t]) for t in ru_ids]
print("RU:", ru_s, "->", len(ru_ids), "токенов:", pieces)
print("EN токенов:", len(en_ids), ":", [llm.detokenize([t]) for t in en_ids])
round_trip = llm.detokenize(ru_ids).decode("utf-8", "replace")
print("round-trip:", repr(round_trip), "точен:", round_trip == ru_s)
# вторая RU-фраза: в те же id?
ru2_ids = tok_ids("Кот спит на подоконнике")
print("RU2 pieces:", [llm.detokenize([t]) for t in ru2_ids])
overlap = len(set(ru_ids) & set(ru2_ids))
print("пересечение id RU1/RU2:", overlap, "из", len(set(ru_ids) | set(ru2_ids)))
