"""Диаг-7: вырожденность пространства — косинусы как функция длины/перекрытия."""
import math, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lab9

llm = lab9.model()

def cs(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return d / (na * nb)

def e(t):
    return llm.embed("passage: " + t)

p1 = e("Собака гуляет в парке")
tests = {
    "синоним ru": "Пёс гуляет по парку",
    "перевод en": "A dog walks in the park",
    "другая тема та же длина": "Кот спит на подоконнике",
    "идентичная +1 слово": "Собака гуляет в парке собака",
    "то же +10 слов": "Собака гуляет в парке и собака гуляет в парке и ещё гуляет",
    "короткий тот же смысл": "Пёс в парке",
    "столько же слов чужое": "Квантовая хромодинамика удерживает глюоны кварки",
}
for k, t in tests.items():
    print(f"{k}: {cs(p1, e(t)):.4f}")
