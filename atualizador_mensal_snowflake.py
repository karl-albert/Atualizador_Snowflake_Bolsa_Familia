#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==================================================================================================
PROJETO: BOLSA FAMÍLIA ANALYTICS — ATUALIZADOR MENSAL SNOWFLAKE
==================================================================================================
Destino: Snowflake (Database: BOLSA_FAMILIA | Schema: PUBLIC | Stage: @STAGE_BOLSA_FAMILIA)
Tabela Alvo: FATO_BOLSA_FAMILIA_REDZ
Autor: Karl / Antigravity Assistant
Data: Setembro/2026
==================================================================================================
Fluxo de Execução:
  1. Conecta ao Snowflake e consulta o MAX(mes_competencia) gravado em FATO_BOLSA_FAMILIA_REDZ.
  2. Varre a pasta de arquivos Parquet detalhados locais procurando meses pendentes.
  3. Para cada novo mês:
     a) DuckDB agrega os 19M de linhas brutas em ~2.9s com regras de SIAFI, Gênero e Data.
     b) Envia o Parquet slice para o Snowflake Stage (@STAGE_BOLSA_FAMILIA/mensal/).
     c) Executa DELETE do mês (idempotência) e COPY INTO atômico na FATO_BOLSA_FAMILIA_REDZ.
     d) A coluna virtual 'valor_total_pago_novo' é calculada automaticamente pelo Snowflake!
     e) Remove os arquivos temporários do stage e do disco local.
==================================================================================================
"""

import os
import sys
import glob
import time
import json
import re
import duckdb
import snowflake.connector

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "snowflake_config.json")
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DETALHADO_DIR = os.path.join(BASE_DIR, "0_Bases_de_Dados", "detalhado")
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp_snowflake_upload")

def extract_yyyymm(filename):
    m = re.search(r'(\d{6})', filename)
    return int(m.group(1)) if m else None

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_connection(cfg):
    return snowflake.connector.connect(
        account=cfg.get("account", "enqwqoj-dm29490").strip(),
        user=cfg.get("user", "KAC").strip(),
        password=cfg.get("password", "").strip(),
        warehouse=cfg.get("warehouse", "COMPUTE_WH").strip() or "COMPUTE_WH",
        database=cfg.get("database", "BOLSA_FAMILIA").strip() or "BOLSA_FAMILIA",
        schema=cfg.get("schema", "PUBLIC").strip() or "PUBLIC",
        role=cfg.get("role", "ACCOUNTADMIN").strip() or "ACCOUNTADMIN",
        autocommit=True
    )

def obter_max_mes_snowflake(cur):
    try:
        cur.execute('SELECT MAX("mes_competencia") FROM FATO_BOLSA_FAMILIA_REDZ;')
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        print(f"[AVISO] Não foi possível obter MAX(mes_competencia): {e}")
        return 0

def gerar_slice_duckdb(parquet_bruto, ym, temp_dir=TEMP_DIR):
    os.makedirs(temp_dir, exist_ok=True)
    out_file = os.path.join(temp_dir, f"{ym}_redz.parquet")
    sql_in = parquet_bruto.replace("\\", "/")
    sql_out = out_file.replace("\\", "/")

    t0 = time.time()
    con = duckdb.connect()
    sql = f"""
    COPY (
        WITH raw_data AS (
            SELECT 
                mes_competencia,
                uf,
                nome_municipio,
                cod_municipio_siafi,
                SPLIT_PART(nome_favorecido, ' ', 1) AS primeiro_nome,
                nis_favorecido,
                valor_parcela
            FROM read_parquet('{sql_in}')
        )
        SELECT 
            TRY_STRPTIME(r.mes_competencia::VARCHAR || '01', '%Y%m%d')::DATE AS "Data",
            IF(UPPER(TRIM(r.primeiro_nome)) LIKE '%A', 'Feminino', 'Masculino')::VARCHAR AS "Genero",
            r.mes_competencia::INTEGER AS "mes_competencia",
            r.nome_municipio::VARCHAR AS "nome_municipio",
            r.cod_municipio_siafi::INTEGER AS "Cod_Municipio_Siafi",
            COUNT(r.nis_favorecido)::INTEGER AS "total_beneficiarios",
            r.uf::VARCHAR AS "uf",
            ROUND(SUM(r.valor_parcela), 2)::DECIMAL(18,2) AS "valor_total_pago"
        FROM raw_data r
        GROUP BY 1, 2, 3, 4, 5, 7
        ORDER BY "uf", "nome_municipio", "Genero"
    ) TO '{sql_out}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """
    con.execute(sql)
    con.close()
    elapsed = time.time() - t0
    fsize_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(f" [DuckDB] Slice agregado do mês {ym} gerado em {elapsed:.2f}s ({fsize_mb:.2f} MB)")
    return out_file

def main():
    print("=" * 80)
    print(" >>> PIPELINE DE ATUALIZAÇÃO MENSAL INCREMENTAL -> SNOWFLAKE <<<")
    print("=" * 80)

    cfg = load_config()
    print(f"[*] Conectando ao Snowflake (Conta: {cfg.get('account')}, User: {cfg.get('user')})...")
    conn = get_connection(cfg)
    cur = conn.cursor()

    try:
        max_mes_snow = obter_max_mes_snowflake(cur)
        print(f"[OK] Último mês presente no Snowflake (FATO_BOLSA_FAMILIA_REDZ): {max_mes_snow}")

        # Listar arquivos locais
        arquivos = sorted(glob.glob(os.path.join(DETALHADO_DIR, "*_NovoBolsaFamilia_fato.parquet")))
        if not arquivos:
            print(f"[ERRO] Nenhum arquivo encontrado em {DETALHADO_DIR}")
            return

        pendentes = []
        for f in arquivos:
            ym = extract_yyyymm(f)
            if ym and ym > max_mes_snow:
                pendentes.append((ym, f))

        if not pendentes:
            print(f"\n[TUDO ATUALIZADO] O Snowflake já possui todos os meses carregados até {max_mes_snow}!")
            resposta = input("Deseja forçar a recarga do último mês disponível? (s/N): ").strip().lower()
            if resposta == 's':
                ultimo_f = arquivos[-1]
                pendentes.append((extract_yyyymm(ultimo_f), ultimo_f))
            else:
                return

        stage_name = cfg.get("stage", "STAGE_BOLSA_FAMILIA")

        for ym, fpath in pendentes:
            print(f"\n--- Processando Mês: {ym} ---")
            temp_parquet = gerar_slice_duckdb(fpath, ym)

            # 1. PUT no Stage
            print(f"[*] Fazendo upload do slice para @{stage_name}/mensal/...")
            temp_sql = temp_parquet.replace("\\", "/")
            cur.execute(f"PUT 'file://{temp_sql}' @{stage_name}/mensal/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;")

            # 2. Idempotência: Limpar se existir
            print(f"[*] Deletando registros prévios do mês {ym} em FATO_BOLSA_FAMILIA_REDZ...")
            cur.execute(f'DELETE FROM FATO_BOLSA_FAMILIA_REDZ WHERE "mes_competencia" = {ym};')

            # 3. COPY INTO
            print(f"[*] Executando COPY INTO na FATO_BOLSA_FAMILIA_REDZ...")
            copy_sql = f"""
            COPY INTO FATO_BOLSA_FAMILIA_REDZ (
                "Data",
                "Genero",
                "mes_competencia",
                "nome_municipio",
                "Cod_Municipio_Siafi",
                "total_beneficiarios",
                "uf",
                "valor_total_pago"
            )
            FROM (
                SELECT 
                    $1:Data::DATE,
                    $1:Genero::VARCHAR,
                    $1:mes_competencia::NUMBER,
                    $1:nome_municipio::VARCHAR,
                    $1:Cod_Municipio_Siafi::NUMBER,
                    $1:total_beneficiarios::NUMBER,
                    $1:uf::VARCHAR,
                    $1:valor_total_pago::NUMBER(18,2)
                FROM @{stage_name}/mensal/{ym}_redz.parquet
            )
            FILE_FORMAT = (TYPE = 'PARQUET');
            """
            cur.execute(copy_sql)
            print(f"[OK] Mês {ym} carregado com sucesso no Snowflake!")

            # 4. Limpeza do Stage e Disco Local
            cur.execute(f"REMOVE @{stage_name}/mensal/{ym}_redz.parquet;")
            if os.path.exists(temp_parquet):
                try: os.remove(temp_parquet)
                except: pass

        # Validação final
        cur.execute("""
            SELECT 
                "mes_competencia", 
                COUNT(*) AS linhas, 
                SUM("total_beneficiarios") AS total_ben, 
                SUM("valor_total_pago") AS total_pago,
                SUM("valor_total_pago_novo") AS total_pago_novo
            FROM FATO_BOLSA_FAMILIA_REDZ
            GROUP BY "mes_competencia"
            ORDER BY "mes_competencia" DESC
            LIMIT 3;
        """)
        print("\n[AUDITORIA FINAL SNOWFLAKE - ÚLTIMOS MESES]:")
        for row in cur.fetchall():
            print(f"  Mês {row[0]}: {row[1]:,} linhas | Beneficiários: {row[2]:,} | Pago: R$ {row[3]:,.2f} | Pago Novo (Virtual): R$ {row[4]:,.2f}")

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
