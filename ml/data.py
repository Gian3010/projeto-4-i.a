"""Gerador de avaliações sintéticas em português (cenário fictício: marketplace *Vitrine Aurora*).

Cada avaliação tem um sentimento (negativo | neutro | positivo) e um tópico principal
(entrega | produto | atendimento | preco). Os textos são compostos de blocos de frase com variações
lexicais, ruído (erros de digitação, emojis, caixa) e *fillers* neutros.

ATENÇÃO: dados sintéticos geram métricas otimistas. Por isso ``ml/evalset.py`` traz um conjunto
escrito à mão, com redação diferente dos modelos, para uma estimativa mais honesta.
"""
from __future__ import annotations

import random

SENTIMENTS = ["negativo", "neutro", "positivo"]
TOPICS = ["entrega", "produto", "atendimento", "preco"]

# (topico, sentimento) -> frases-base
PHRASES: dict[tuple[str, str], list[str]] = {
    ("entrega", "negativo"): [
        "o pedido chegou com {n} dias de atraso", "a entrega demorou muito mais que o prometido",
        "o entregador nunca apareceu e o prazo estourou", "ainda não recebi minha encomenda e já passou do prazo",
        "o rastreio ficou parado por dias", "o pacote chegou violado e fora do prazo",
        "a transportadora devolveu o pedido sem avisar", "esperei {n} dias e nada de chegar",
    ],
    ("entrega", "neutro"): [
        "o pedido chegou no endereço informado", "recebi o pacote na quarta-feira",
        "a entrega foi feita pela transportadora padrão", "o código de rastreio foi enviado por e-mail",
        "o prazo informado era de {n} dias úteis", "a encomenda veio em uma caixa de papelão",
    ],
    ("entrega", "positivo"): [
        "chegou antes do prazo, muito rápido", "entrega super rápida e bem embalada",
        "o pedido chegou em {n} dias, adorei a rapidez", "o rastreio funcionou perfeitamente e a entrega foi pontual",
        "pacote chegou intacto e adiantado", "entrega impecável, dentro do prazo",
    ],
    ("produto", "negativo"): [
        "o produto veio quebrado", "a qualidade é péssima, parece falsificado",
        "o item não funciona como anunciado", "veio com defeito logo na primeira semana",
        "o material é fraco e já estragou", "o produto é diferente da foto do anúncio",
        "a bateria dura quase nada", "chegou faltando peças",
    ],
    ("produto", "neutro"): [
        "o produto é do tamanho informado", "veio com manual e uma peça de reposição",
        "a cor é igual à do anúncio", "o item pesa cerca de {n} quilos",
        "comprei a versão básica do produto", "o produto veio lacrado na embalagem original",
    ],
    ("produto", "positivo"): [
        "o produto é excelente, superou minhas expectativas", "ótima qualidade, material resistente",
        "funciona perfeitamente, recomendo muito", "produto idêntico ao anúncio e muito bem acabado",
        "a qualidade é incrível pelo que se paga", "adorei o produto, uso todo dia",
    ],
    ("atendimento", "negativo"): [
        "o suporte demorou {n} dias para responder", "atendimento péssimo, ninguém resolve nada",
        "fui ignorado pela central e tive que abrir reclamação", "o atendente foi grosseiro e não resolveu meu problema",
        "chamei no chat várias vezes e não tive retorno", "o SAC me deixou esperando horas na linha",
    ],
    ("atendimento", "neutro"): [
        "falei com o suporte pelo chat", "abri um chamado pelo site",
        "o atendimento funciona de segunda a sexta", "recebi o protocolo de atendimento por e-mail",
        "o suporte pediu o número do pedido", "entrei em contato com a central ontem",
    ],
    ("atendimento", "positivo"): [
        "atendimento excelente, resolveram na hora", "o suporte foi muito atencioso e educado",
        "a atendente resolveu meu problema rapidinho", "ótimo atendimento, me ajudaram em tudo",
        "o SAC foi super prestativo", "equipe de suporte nota 10",
    ],
    ("preco", "negativo"): [
        "o preço está abusivo para o que entrega", "paguei caro e o valor não compensa",
        "o frete é absurdo, mais caro que o produto", "fui cobrado a mais no cartão",
        "o preço subiu depois que coloquei no carrinho", "muito caro comparado com a concorrência",
    ],
    ("preco", "neutro"): [
        "paguei {n} reais no pedido", "o valor foi parcelado em 3 vezes",
        "usei um cupom de desconto na compra", "o preço estava igual ao do site oficial",
        "o frete foi calculado no checkout", "o pagamento foi feito por pix",
    ],
    ("preco", "positivo"): [
        "preço justo e ótimo custo-benefício", "valeu cada centavo, muito barato pelo que oferece",
        "o preço estava abaixo de todas as lojas", "promoção excelente, economizei bastante",
        "frete grátis e preço ótimo", "custo-benefício imbatível",
    ],
}
FILLERS_PRE = ["", "", "", "No geral, ", "Olha, ", "Sinceramente, ", "Resumindo: ", "Comprei na semana passada e "]
FILLERS_POST = ["", "", "", ".", "!", "...", " 🙂", " 😡", " (compra #{n})"]
TYPO_SWAPS = [("ção", "cao"), ("ã", "a"), ("é", "e"), ("ç", "c"), ("á", "a"), ("ê", "e")]


def _noise(text: str, rng: random.Random) -> str:
    if rng.random() < 0.20:  # remove acentos (comum em celular)
        for a, b in rng.sample(TYPO_SWAPS, 3):
            text = text.replace(a, b)
    if rng.random() < 0.08:
        text = text.upper()
    if rng.random() < 0.10 and len(text) > 20:  # letra duplicada
        i = rng.randrange(5, len(text) - 5)
        text = text[:i] + text[i] + text[i:]
    return text


def make_review(topic: str, sentiment: str, rng: random.Random) -> str:
    base = rng.choice(PHRASES[(topic, sentiment)]).format(n=rng.randint(2, 20))
    text = rng.choice(FILLERS_PRE) + base + rng.choice(FILLERS_POST).format(n=rng.randint(1000, 9999))
    return _noise(text, rng)


def generate(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        topic = rng.choice(TOPICS)
        sentiment = rng.choices(SENTIMENTS, [0.38, 0.22, 0.40])[0]
        rows.append({"text": make_review(topic, sentiment, rng), "topic": topic, "sentiment": sentiment})
    return rows
