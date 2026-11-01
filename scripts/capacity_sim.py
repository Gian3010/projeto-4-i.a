"""Simulação de volumetria: quantos workers a API precisa para um certo número de usuários.

É um MODELO ANALÍTICO, não uma medição. As entradas de usuários e comportamento são hipóteses;
a vazão por worker vem do teste de carga (scripts/loadtest.py) e deve ser remedida no seu ambiente.

Fórmulas:
  req_dia          = DAU x req_por_usuario_dia
  rps_médio        = req_dia / 86400
  rps_pico         = rps_médio x fator_de_pico
  workers          = ceil(rps_pico / (rps_por_worker x utilização_alvo))
  concorrência     = rps_pico x latência_s            (Lei de Little: requisições simultâneas)
"""
from __future__ import annotations

import argparse
import math


def simulate(dau: int, req_per_user_day: float, peak_factor: float, rps_per_worker: float,
             target_util: float, service_ms: float) -> dict:
    req_day = dau * req_per_user_day
    avg = req_day / 86_400
    peak = avg * peak_factor
    workers = max(1, math.ceil(peak / (rps_per_worker * target_util)))
    return {"dau": dau, "req_dia": req_day, "rps_medio": avg, "rps_pico": peak, "workers": workers,
            "concorrencia_pico": peak * service_ms / 1000}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rps-per-worker", type=float, default=180.0, help="medido com loadtest.py (1 worker)")
    ap.add_argument("--req-per-user-day", type=float, default=20.0)
    ap.add_argument("--peak-factor", type=float, default=10.0, help="pico / média (horário de pico)")
    ap.add_argument("--target-util", type=float, default=0.5, help="deixe folga: 50% do máximo medido")
    ap.add_argument("--service-ms", type=float, default=5.0, help="tempo de serviço por requisição (1/rps)")
    ap.add_argument("--dau", type=int, nargs="+", default=[1_000, 10_000, 100_000, 1_000_000])
    a = ap.parse_args()

    print(f"Premissas: {a.req_per_user_day:g} req/usuário/dia · pico {a.peak_factor:g}x a média · "
          f"{a.rps_per_worker:g} req/s por worker · utilização-alvo {a.target_util:.0%}\n")
    print(f"{'DAU':>10} {'req/dia':>12} {'req/s médio':>12} {'req/s pico':>11} {'workers':>8} {'simultâneas':>12}")
    for dau in a.dau:
        s = simulate(dau, a.req_per_user_day, a.peak_factor, a.rps_per_worker, a.target_util, a.service_ms)
        print(f"{s['dau']:>10,} {s['req_dia']:>12,.0f} {s['rps_medio']:>12.2f} {s['rps_pico']:>11.1f} "
              f"{s['workers']:>8} {s['concorrencia_pico']:>12.2f}")


if __name__ == "__main__":
    main()
