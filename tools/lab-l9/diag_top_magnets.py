import sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import lab9, sqlite3

# H1: реально ли embed зависит от входа (на warm-модели)
a = lab9.embed("рецепт пасты фокачча с розмарином и спаржей", "query:")
b = lab9.embed("sqlite-vec локальный векторный индекс", "query:")
dot = sum(x*y for x, y in zip(a, b))
print("H1 cosine(query1,query2) =", round(dot, 4), "(высокий ~0.99 => embed не зависит от текста)")

# что это за магниты
db = sqlite3.connect(lab9.DB)
for rid, path, line, txt in db.execute(
    "select rowid, path, line, substr(text,1,120) from doc where rowid in"
    " (select rowid from doc where path in"
    " ('04-Memory/session-log/2026-07-12.md','04-Memory/session-log/2026-06-29.md','99-Inbox.md')"
    " and line in (1,22,596)) limit 6"):
    print(rid, path, line, repr(txt))
# распределение размеров чанков
sizes = [len(t) for (t,) in db.execute("select text from doc")]
import statistics
print("чанков:", len(sizes), "median:", statistics.median(sizes),
      "мин:", min(sizes), "<200 симв.:", sum(1 for s in sizes if s < 200))
