# Atualizador Mensal Bolsa Família — Snowflake

Repositório oficial para automação do pipeline mensal do **Bolsa Família Analytics** no **Snowflake Data Cloud**.

## 🎯  Arquitetura da Solução
* **Database / Schema**: `BOLSA_FAMILIA.PUBLIC`
* **Tabela Fato**: `FATO_BOLSA_FAMILIA_REDZ`
* **Coluna Virtual Dinâmica*: `"valor_total_pago_novo"` (aplica automaticamente reajuste de +15.04% a partir de 2026-07).
* **Motor Local**: DuckDB In-Memory (agrega 19M de transações em 2.9s para envio atômico ao Stage).

## 🚀 Como Executar
Basta dar duplo clique em `Subir_Mes_Snowflake.bat` ou executar via terminal:
```bash
python atualizador_mensal_snowflake.py
```
