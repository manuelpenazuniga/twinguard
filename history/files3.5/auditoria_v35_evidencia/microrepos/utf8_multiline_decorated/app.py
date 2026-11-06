def deco(f): return f
def validate(x): pass
@deco
def run():
    café = "niño"; validate("""uno
dos""")  # comentario externo
    return café
