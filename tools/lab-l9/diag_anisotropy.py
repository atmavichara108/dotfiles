import math, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lab9

llm = lab9.model()

def emb(t):
    return llm.embed(t)

def cs(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return d / (na * nb)

# 1) англоязычный контроль: если англ. пары различаются — модель жива, дело в кириллице/токен.
en1 = emb("query: The cat sleeps on the windowsill")
en2 = emb("query: Quantum chromodynamics confines gluons")
ru1 = emb("query: Кот спит на подоконнике")
ru2 = emb("query: Квантовая хромодинамика конфайнмент глюонов")
print("EN пара:", round(cs(en1, en2), 4), " RU пара:", round(cs(ru1, ru2), 4))
print("EN-RU:", round(cs(en1, ru1), 4))

# 2) латинская транслитерация RU-запроса (проверка токенизации кириллицы)
tr = emb("query: Kot spit na podokonnike")
print("RU vs транслит:", round(cs(ru1, tr), 4), "(высокий => кириллица токенизируется/ретьюнится как латиница)")

# 3) спэйс-дегенерация: попарные косинусы 12 коротких тематически разных passage
texts = [
    "passage: борщ с говядиной рецепт", "passage: векторный индекс sqlite",
    "passage: протокол писем двойной ack", "passage: погодный виджет дождь",
    "passage: сборка ядра linux pacman", "passage: квантовая запутанность фотонов",
    "passage: японская грамматика дзю-дзюцу", "passage: стейк рибай температура прожарки",
    "passage: git rebase интерактивный коммит", "passage: фотоаппарат диафрагма выдержка",
    "passage: марксистская политэкономия стоимость", "passage: аквариум неон сомики вода",
]
vs = [emb(t) for t in texts]
pairs = [cs(vs[i], vs[j]) for i in range(len(vs)) for j in range(i + 1, len(vs))]
print("RU- passage: min", round(min(pairs), 3), "median", round(sorted(pairs)[len(pairs)//2], 3), "max", round(max(pairs), 3))
