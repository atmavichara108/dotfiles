import math, sys, struct
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lab9

llm = lab9.model()

def cs(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return d / (na * nb)

# A) эталонная пара sentence-transformers мульт. e5: перекрёстная языковая близость
ru = llm.embed("passage: Собака гуляет в парке")
en = llm.embed("passage: A dog walks in the park")
un = llm.embed("passage: Квантовая хромодинамика удерживает кварки")
print("ru-en перевод:", round(cs(ru, en), 4), " (ожидаемо >0.8 для живой модели)")
print("ru-un нерелев:", round(cs(ru, un), 4))

# B) diff-чанков: сколько токенов реально влияет (tokenizer-поведение)
tok_ru = llm.tokenize("Собака гуляет в парке", add_bos=False)
tok_en = llm.tokenize("A dog walks in the park", add_bos=False)
print("токенов RU:", len(tok_ru), "EN:", len(tok_en))

# C) сырой pooling: same text c разным регистром/длиной
v1 = llm.embed("passage: тест")
v2 = llm.embed("passage: тест тест тест тест")
print("косинус 'тест' vs 'тест четыре раза':", round(cs(v1, v2), 4))

# D) токен-'id' из vocab: есть ли кириллические подслова в bert-BPE vocab
p = str(__import__("pathlib").Path(__file__).resolve().parent / ".venv/models/multilingual-e5-small-Q8_0.gguf")
with open(p, "rb") as f:
    data = f.read(40 * 1024 * 1024)
cyrl = sum(1 for _ in __import__("re").finditer(rb"[\xd0-\xd1][\x80-\xbf]", data[:20_000_000]))
print("байт-пар UTF-8 кириллицы в первых 20 МБ GGUF:", cyrl, "(0 => vocab без кириллицы — конверт битый)")
