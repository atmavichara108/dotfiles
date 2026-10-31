"""Минимальный тест итерации 2 (f16-конверт): БЕЗ построения индекса.
Шаг 1: vocab/tokenizer на кириллице (тот же diag_tokenizer).
Шаг 2: 6 скалярных косинусов (kill-criterion).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llama_cpp import Llama

MODEL = Path(__file__).resolve().parent / ".venv/models/e5-small-hdrrayan-f16.gguf"
llm = Llama(model_path=str(MODEL), embedding=True, n_threads=4, verbose=False)

print("=== VOCAB-тест (как в diag6c) ===")
def tok_ids(text):
    return llm.tokenize(text.encode("utf-8"), add_bos=False, special=True)

ru_s = "Собака гуляет в парке"
ru_ids = tok_ids(ru_s)
pieces = [llm.detokenize([t]) for t in ru_ids]
print("RU:", len(ru_ids), "куски:", pieces)
round_trip = llm.detokenize(ru_ids).decode("utf-8", "replace")
print("round-trip точен:", round_trip == ru_s)

def cs(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return d / (na * nb)

def e(t, prefix="passage: "):
    return llm.embed(prefix + t)

print("\n=== 6 косинусов (гипотеза: различимое RU-пространство) ===")
base = e("Собака гуляет в парке")
pairs = {
    "1 синоним ru (ожидаемо высоко)": e("Пёс гуляет по парку"),
    "2 перевод en (можно не высоко)": e("A dog walks in the park"),
    "3 нерелевантная тема той же длины": e("Квантовая хромодинамика удерживает глюоны кварки"),
    "4 кот спит на подоконнике": e("Кот спит на подоконнике"),
    "5 идентичная +1 слово (должен быть выше всех)": e("Собака гуляет в парке собака"),
    "6 аквариумный другой жанр": e("Аквариумные сомики дышат водой"),
}
for k, v in pairs.items():
    print(f"  {k}: cos={cs(base, v):.4f}")

q = e("sqlite-vec локальный векторный индекс", prefix="query: ")
a = e("векторный индекс sqlite над фактами сессий", prefix="query: ")
b = e("рецепт борща с говядиной", prefix="query: ")
print(f"\nquery-level: тематическая пара={cs(q, a):.4f} vs нерелевантная пара={cs(q, b):.4f}")
