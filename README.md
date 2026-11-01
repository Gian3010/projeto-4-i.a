# 🔎 Review Insight API — análise de sentimento e tópico servida por FastAPI

API REST que classifica **sentimento** (negativo/neutro/positivo) e **tópico** (entrega, produto, atendimento, preço) de avaliações de clientes em português, devolve um **risco de negatividade** para priorizar filas e marca as predições de baixa confiança para revisão humana. Inclui autenticação, rate limit, métricas Prometheus, logs estruturados, testes, Docker e deploy no Render.

> **Aviso de transparência.** O marketplace (*Vitrine Aurora*), o volume de avaliações e os usuários da seção 7 são **fictícios** e a volumetria é uma **simulação analítica**. O modelo foi treinado com **dados sintéticos**. Todas as demais métricas (testes, acurácia, latência, vazão) foram **medidas** rodando este código — com as ressalvas escritas ao lado de cada número. A API **não está em produção com usuários reais**; ela está *pronta para produção* no sentido de ter os controles operacionais básicos.

---

## 1. Situação-problema (cenário fictício)

A *Vitrine Aurora* recebe ~4.000 avaliações por dia. Três analistas leem uma a uma para separar elogios de reclamações e encaminhar ao time certo (logística, produto, SAC, comercial): **~15 s por avaliação** (premissa do cenário), ou ~17 h de leitura por dia. Reclamações graves ficam misturadas e demoram a chegar a quem resolve.

**Solução:** uma API que o sistema de avaliações chama a cada nova avaliação (ou em lote, de madrugada) e que devolve sentimento, tópico e `negative_risk`. O roteamento é automático; só o que o modelo duvida (`needs_human_review`) vai para um humano.

## 2. Endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `POST` | `/v1/analyze` | ✅ | Analisa uma avaliação |
| `POST` | `/v1/analyze/batch` | ✅ | Até 100 avaliações por chamada (inferência vetorizada) |
| `GET` | `/v1/model` | ✅ | Versão, rótulos e métricas do modelo (com ressalvas) |
| `GET` | `/health` | – | *Liveness* |
| `GET` | `/ready` | – | *Readiness* (modelo carregado) |
| `GET` | `/metrics` | – | Métricas Prometheus (proteja na borda em produção real) |
| `GET` | `/docs` · `/redoc` · `/openapi.json` | – | **Swagger UI**, ReDoc e especificação OpenAPI |

Exemplo:

```bash
curl -X POST http://localhost:8000/v1/analyze \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"text": "O pedido chegou com 10 dias de atraso e ninguém no suporte responde."}'
```

```json
{
  "request_id": "9f1c2e0a7b3d4a11",
  "model_version": "2026.11.01-2b12265b",
  "result": {
    "sentiment": "negativo", "sentiment_confidence": 0.93,
    "sentiment_probabilities": {"negativo": 0.93, "neutro": 0.04, "positivo": 0.03},
    "topic": "atendimento", "topic_confidence": 0.58,
    "negative_risk": 0.93, "needs_human_review": true
  }
}
```
*(valores ilustrativos de formato; os reais variam a cada treino)*

## 3. Arquitetura e decisões

```
cliente ─► [middleware: request-id · tempo · log JSON · métricas]
        ─► [auth X-API-Key (tempo constante)] ─► [rate limit por chave] ─► rota
        ─► ModelService (TF-IDF + Regressão Logística ×2: sentimento e tópico) ─► resposta tipada (Pydantic)
```

| Decisão | Motivo |
|---|---|
| Modelo **clássico** (TF-IDF + LR) em vez de LLM | ~1 ms/texto, custo ~zero, determinístico, sem dependência externa; serve de linha de base barata |
| Treino no **build** (`python -m ml.train`) | O artefato sempre casa com a versão do scikit-learn da imagem; sem `.joblib` no Git |
| Rotas `def` (síncronas) | O FastAPI as executa em *thread pool*; inferência é CPU-bound e não bloqueia o *event loop* |
| Endpoint em lote vetorizado | Uma chamada ao modelo para N textos: ~16× mais avaliações/s que chamadas unitárias (6.051 vs 366 por segundo na seção 6.3) |
| Comparação de chave em **tempo constante** | Evita *timing attacks*; logs usam hash da chave, nunca a chave |
| Métrica por **template da rota** | Evita explosão de cardinalidade (rotas inexistentes viram `unmatched`) |
| Erros padronizados (`error`, `detail`, `request_id`) | Cliente e suporte rastreiam a falha pelo mesmo ID (`X-Request-ID`) |
| `needs_human_review` | A API admite o que não sabe, em vez de forçar uma classe |

```
review-insight-api/
├── app/       main · config · schemas · model · security · ratelimit · metrics
├── ml/        data (gerador sintético) · evalset (36 frases à mão) · train
├── tests/     test_api.py (27 testes)
├── scripts/   loadtest.py · capacity_sim.py
├── Dockerfile · render.yaml · .github/workflows/ci.yml
```

## 4. Como rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ml.train                         # gera artifacts/model.joblib e metrics.json
python -m pytest -q                        # 27 testes
API_KEYS=dev-key uvicorn app.main:app --reload
# abra http://localhost:8000/docs  → botão "Authorize" → cole dev-key
```

Docker: `docker build -t review-insight-api . && docker run -p 8000:8000 -e API_KEYS=dev-key review-insight-api`

Variáveis: veja `.env.example` (`API_KEYS`, `RATE_LIMIT_PER_MIN`, `MAX_BATCH_SIZE`, `REVIEW_THRESHOLD`, `CORS_ORIGINS`...).

## 5. Deploy no Render, passo a passo

> Os nomes de botões do Render podem mudar um pouco com o tempo; a lógica é a mesma. Valide a documentação atual em render.com/docs se algo não bater.

**Pré-requisitos:** código no GitHub (repositório com `requirements.txt`, `app/`, `ml/` na raiz) e uma conta gratuita no Render.

**Opção A — Blueprint (mais rápido, usa o `render.yaml`)**

1. Acesse **https://dashboard.render.com** e entre com **GitHub** (autorize o Render a ler seus repositórios).
2. No canto superior direito, clique em **New +** e escolha **Blueprint**.
3. Em **Connect a repository**, selecione este repositório (use **Configure account** se ele não aparecer) e clique em **Connect**.
4. Dê um nome ao *Blueprint* (ex.: `review-insight`) e confira o serviço `review-insight-api` listado a partir do `render.yaml`. Clique em **Deploy Blueprint**.
5. Aguarde o build (cerca de 2–4 minutos; o log mostra a instalação e o treino do modelo). Quando aparecer **Live**, o deploy terminou.
6. Abra o serviço → aba **Environment** → localize `API_KEYS` → clique no ícone de **olho** para revelar o valor e **copie**. Essa é a sua chave.
7. No topo da página do serviço está a URL pública (`https://review-insight-api-xxxx.onrender.com`). Teste:
   ```bash
   curl https://SUA-URL.onrender.com/health
   curl -X POST https://SUA-URL.onrender.com/v1/analyze \
     -H "X-API-Key: SUA_CHAVE" -H "Content-Type: application/json" \
     -d '{"text":"Chegou rápido e bem embalado, adorei!"}'
   ```
8. Abra `https://SUA-URL.onrender.com/docs`, clique em **Authorize**, cole a chave e execute **Try it out** em `/v1/analyze`.

**Opção B — Manual**

1. **New +** → **Web Service** → **Build and deploy from a Git repository** → **Next**.
2. Selecione o repositório e clique em **Connect**.
3. Preencha: **Name** `review-insight-api`; **Region** a mais próxima dos seus usuários; **Branch** `main`; **Root Directory** (deixe vazio); **Runtime** `Python 3`.
4. **Build Command:** `pip install -r requirements.txt && python -m ml.train`
5. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers`
6. **Instance Type:** `Free` (para teste) ou um plano pago (para evitar *spin-down* e ter mais CPU).
7. Em **Advanced** → **Add Environment Variable**: `API_KEYS` = uma chave forte (gere com `python -c "import secrets; print(secrets.token_urlsafe(32))"`), `PYTHON_VERSION` = `3.12.8`, `RATE_LIMIT_PER_MIN` = `120`.
8. Em **Advanced** → **Health Check Path**, digite `/health`.
9. Clique em **Create Web Service** e siga do passo 5 da Opção A.

**Depois do deploy**

- **Deploy automático:** a cada `git push` na `main`, o Render refaz o build (`autoDeploy`). Para pausar, **Settings → Build & Deploy → Auto-Deploy → No**.
- **Rodar a chave:** em **Environment**, edite `API_KEYS` (várias chaves separadas por vírgula permitem trocar sem *downtime*: adicione a nova, migre os clientes, remova a antiga) e clique em **Save, rebuild, and deploy**.
- **Logs:** aba **Logs** (JSON, uma linha por requisição, com `request_id`, rota, status, ms e `client` = hash da chave).
- **Domínio próprio:** **Settings → Custom Domains → Add Custom Domain**, e crie o registro CNAME indicado no seu provedor de DNS.
- **Plano gratuito:** a instância costuma **hibernar após alguns minutos sem tráfego** (a primeira chamada seguinte demora) e tem CPU/RAM muito menores que o ambiente de teste da seção 6. **Remeça com `scripts/loadtest.py` na instância real** antes de prometer qualquer capacidade.
- **Segurança:** não publique a chave em README, front-end ou repositório; `/metrics` está aberto — em produção real restrinja na borda (IP allowlist ou autenticação no proxy).

Alternativas equivalentes: o mesmo `Dockerfile` roda em AWS App Runner, Google Cloud Run, Fly.io ou Railway sem alterações (a porta vem de `$PORT`).

## 6. Resultados medidos

### 6.1 Qualidade do modelo — leia com cuidado

| Conjunto | Sentimento (acurácia / F1 macro) | Tópico (acurácia / F1 macro) |
|---|---|---|
| Sintético (holdout, n = 1.500) | 100% / 1,00 | 100% / 1,00 |
| **Escrito à mão (n = 36)** | **72,2% / 0,72** | **66,7% / 0,67** |

- Os **100% no sintético não significam nada**: o modelo aprende os moldes do gerador. Mostro o número justamente para evidenciar a armadilha.
- A estimativa realista é a do conjunto escrito à mão (frases com redação diferente). **São só 36 exemplos**: cada erro mexe ~3 pontos percentuais; trate como diagnóstico, não *benchmark*. Não ajustei o modelo olhando esse conjunto, para não contaminá-lo.
- Com o limiar de confiança 0,60, o sistema marca **16 de 36 (44%)** para revisão humana. Nos 20 não marcados, a acurácia foi **90% (sentimento)** e **85% (tópico)**; nos marcados, 50% (sentimento). O sinal de confiança funciona, mas a amostra é pequena.
- Reclamações (12 no conjunto): o modelo identificou **8 de 12 (67%)** como negativas.
- **Próximo passo real:** treinar e avaliar com avaliações reais anonimizadas e rotuladas por humanos.

### 6.2 Software

| Verificação | Resultado |
|---|---|
| Testes automatizados | **27 passando** (auth, validação, lote, limites, rate limit, métricas, erro 500 sem vazamento, OpenAPI) |
| Rate limit em servidor real (limite 5/min) | 5 × `200`, depois `429` com `Retry-After` e `X-RateLimit-*` |
| Inferência isolada | **1,2 ms** (p50) por texto; **4,2 ms** para um lote de 50 textos |
| Docker / Render | **não executados** neste ambiente (sem daemon Docker nem conta Render); validar no primeiro deploy |

### 6.3 Carga (teste real, ambiente de desenvolvimento)

Ambiente: **sandbox de 2 vCPU, cliente de carga e servidor na mesma máquina** (disputam CPU, então os números são um **piso conservador** e **não** representam o Render). Reprodução: `scripts/loadtest.py`.

| Cenário | Vazão | Latência (cliente) p50 / p95 / p99 | Erros |
|---|---|---|---|
| 2 workers, 32 conexões, 1 avaliação por chamada, 15 s | **366 req/s** | 76 / 158 / 274 ms | 0% |
| 1 worker, 16 conexões, 12 s | **195 req/s** | 82 / 119 / 142 ms | 0% |
| 2 workers, 8 conexões, **lote de 50**, 10 s | 121 req/s = **6.051 avaliações/s** | 64 / 92 / 116 ms | 0% |

Observações: sob concorrência baixa, `curl` e `httpx` síncrono medem **~4 ms** por requisição; o cliente assíncrono do teste de carga disputa a CPU com o servidor, então os percentis acima incluem fila. Cada worker mantém suas próprias métricas e seu próprio *rate limit* em memória.

## 7. Simulação de volumetria de usuários (modelo analítico — não é medição)

`python scripts/capacity_sim.py` combina **hipóteses de uso** com a vazão medida por worker (180 req/s, arredondada para baixo a partir do teste acima). Premissas: 20 requisições por usuário por dia, pico 10× a média, utilização-alvo de 50%.

| Usuários ativos/dia | Requisições/dia | req/s médio | req/s pico | Workers necessários | Requisições simultâneas no pico |
|---|---|---|---|---|---|
| 1.000 | 20.000 | 0,23 | 2,3 | 1 | 0,01 |
| 10.000 | 200.000 | 2,31 | 23,1 | 1 | 0,12 |
| 100.000 | 2.000.000 | 23,15 | 231,5 | 3 | 1,16 |
| 1.000.000 | 20.000.000 | 231,48 | 2.314,8 | 26 | 11,57 |

Leitura: até ~10 mil usuários/dia um único worker basta; a partir daí a escala é **horizontal** (mais réplicas atrás de um balanceador). Para isso, o *rate limit* em memória precisa ir para **Redis** e `/metrics` deve ser coletado por réplica. Usar o endpoint em lote reduz o número de chamadas em ordens de grandeza. **Premissas de uso reais mudam tudo**: recalcule com `--req-per-user-day`, `--peak-factor` e a vazão medida na sua instância.

## 8. Impacto estimado do cenário (simulação)

Premissas hipotéticas: 4.000 avaliações/dia, 15 s manuais cada (16,7 h/dia). Com a API, só avaliações marcadas para revisão (44% com o limiar 0,60, medido no conjunto de 36 — **amostra pequena**) seriam lidas, a 15 s cada: 4.000 × 0,44 × 15 s ≈ **7,3 h/dia**, uma redução estimada de **≈ 56%** (~9,4 h/dia). Isso **supõe** que a classificação automática das não marcadas seja aceitável (90% de acerto na amostra); o ganho real depende da acurácia em dados reais e do custo de errar.

## 9. Limitações e próximos passos

- Dados de treino sintéticos; precisa de dados reais rotulados e avaliação por tópico/sentimento com mais exemplos.
- *Rate limit* e métricas por processo (use Redis/Prometheus *multiprocess* ao escalar).
- Sem persistência das predições e sem monitoramento de *drift*; próximo passo: registrar entradas anonimizadas e acompanhar distribuição e confiança ao longo do tempo.
- Sem versionamento múltiplo de modelos ou *shadow deploy*.
- Texto em português informal (gírias, ironia, emojis) é um ponto fraco de modelos de *bag-of-words*; comparar com um modelo *transformer* ajustado seria o passo natural (o `llm-prompt-lab` mostra como avaliar).
