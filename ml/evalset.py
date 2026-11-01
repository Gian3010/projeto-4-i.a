"""Conjunto de avaliação escrito à mão (36 frases), com redação diferente dos modelos do gerador.

Serve como estimativa mais honesta do que o conjunto sintético. É pequeno: 36 exemplos dão uma
margem de erro grande (alguns pontos percentuais por exemplo errado) — trate como diagnóstico, não
como benchmark.  Formato: (texto, sentimento, tópico)
"""

EVAL_SET: list[tuple[str, str, str]] = [
    # entrega
    ("Ainda estou esperando o meu pedido e o site diz que foi entregue, um absurdo", "negativo", "entrega"),
    ("A caixa chegou toda amassada e semanas depois do combinado", "negativo", "entrega"),
    ("Passaram duas vezes aqui e disseram que não tinha ninguém, mas eu estava em casa", "negativo", "entrega"),
    ("Recebi o pacote hoje de manhã, a portaria assinou", "neutro", "entrega"),
    ("O produto foi despachado pelos Correios e o código chegou por mensagem", "neutro", "entrega"),
    ("Veio no prazo que estava escrito no carrinho", "neutro", "entrega"),
    ("Nossa, chegou em dois dias! Muito mais rápido do que eu esperava", "positivo", "entrega"),
    ("Embalagem cuidadosa e o motoboy foi super pontual", "positivo", "entrega"),
    ("Logística de primeira, recebi antes de terminar a semana", "positivo", "entrega"),
    # produto
    ("Estragou depois de três usos, não compro mais dessa marca", "negativo", "produto"),
    ("O tecido é ralo e a costura abriu na primeira lavagem", "negativo", "produto"),
    ("Veio sem o carregador e a tela tem um risco enorme", "negativo", "produto"),
    ("É um fone preto com cabo de um metro e meio", "neutro", "produto"),
    ("Comprei o modelo de 500 gramas na cor azul", "neutro", "produto"),
    ("A caixa trazia o item e um folheto de instruções", "neutro", "produto"),
    ("Material robusto, acabamento caprichado, estou muito satisfeito", "positivo", "produto"),
    ("A câmera tira fotos lindas, melhor do que eu imaginava", "positivo", "produto"),
    ("Cumpre tudo o que promete, duradouro e bonito", "positivo", "produto"),
    # atendimento
    ("Mandei quatro mensagens e ninguém respondeu, descaso total", "negativo", "atendimento"),
    ("A moça do telefone desligou na minha cara quando pedi o estorno", "negativo", "atendimento"),
    ("Fiquei dias sendo transferido de setor em setor sem solução", "negativo", "atendimento"),
    ("Conversei com um atendente pelo aplicativo sobre a troca", "neutro", "atendimento"),
    ("O chat pediu meu CPF e o número do pedido para abrir o protocolo", "neutro", "atendimento"),
    ("Liguei para a central e me passaram um número de ticket", "neutro", "atendimento"),
    ("O rapaz do chat foi gentil e trocou o item sem burocracia", "positivo", "atendimento"),
    ("Fui muito bem atendida, resolveram tudo em poucos minutos", "positivo", "atendimento"),
    ("Suporte nota dez, educados e eficientes", "positivo", "atendimento"),
    # preco
    ("Cobraram o dobro do que estava anunciado, uma enganação", "negativo", "preco"),
    ("Achei caríssimo, em outro site encontrei bem mais em conta", "negativo", "preco"),
    ("O valor do frete saiu mais caro que a mercadoria, revoltante", "negativo", "preco"),
    ("Paguei no boleto com vencimento em três dias", "neutro", "preco"),
    ("O desconto do cupom foi aplicado no final da compra", "neutro", "preco"),
    ("O total ficou em cento e vinte reais com o frete", "neutro", "preco"),
    ("Preço excelente, comprei mais duas unidades aproveitando a oferta", "positivo", "preco"),
    ("Está baratíssimo perto das outras lojas, aproveitem", "positivo", "preco"),
    ("Ótima promoção, o desconto compensou demais", "positivo", "preco"),
]
