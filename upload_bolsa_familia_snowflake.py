#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
PIPELINE DE CARGA BOLSA FAMÍLIA -> SNOWFLAKE (MODELO ESPELHO POWER BI)
========================================================================================
Destino: Snowflake (Database: BOLSA_FAMILIA | Schema: PUBLIC | Stage: @STAGE_BOLSA_FAMILIA)
Tabelas Físicas:
  1. FATO_BOLSA_FAMILIA_REDZ     (456k linhas | 4.3 MB Parquet | Gênero, Município, Mês)
  2. DIM_POPULACAO_UF_MUNICIPIOS (5.570 municípios IBGE | 131 KB Parquet)
========================================================================================
Observação: Medidas, Semáforo e dCalendário permanecem diretamente dentro do Power BI.
========================================================================================
"""

import os
import sys
import glob
import time
import json
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

# Forçar UTF-8 no terminal Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import snowflake.connector
except ImportError:
    print("❌ [ERRO] snowflake-connector-python não instalado. Execute: pip install snowflake-connector-python")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "snowflake_config.json")

# Caminhos das Bases
BASE_D = r"D:\1_Bases_Parquet"
BASE_C = r"C:\000 - Karl\116 - Dashbords\Projetos_Power_BI\Bolsa_Familia\0_Bases_de_Dados"

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def find_redz_file():
    candidates = [
        os.path.join(BASE_D, "Fato_Bolsa_Familia_Redz.parquet"),
        os.path.join(BASE_C, "Fato_Bolsa_Familia_Redz.parquet"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

def find_pop_file():
    candidates = [
        os.path.join(BASE_D, "dimensoes", "fato_Populacao_UF_Municipios.parquet"),
        os.path.join(BASE_C, "dimensoes", "fato_Populacao_UF_Municipios.parquet"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

def load_config(config_file=CONFIG_PATH):
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [AVISO] Falha ao ler {config_file}: {e}")
    return {
        "account": "enqwqoj-dm29490",
        "user": "",
        "password": "",
        "warehouse": "COMPUTE_WH",
        "database": "BOLSA_FAMILIA",
        "schema": "PUBLIC",
        "role": "ACCOUNTADMIN",
        "stage": "STAGE_BOLSA_FAMILIA",
        "file_format": "FORMAT_PARQUET_GENERIC"
    }

def get_connection(cfg):
    user = cfg.get("user", "").strip()
    pwd = cfg.get("password", "").strip()
    if not user or not pwd:
        raise ValueError("Usuário e Senha do Snowflake devem ser informados!")

    conn = snowflake.connector.connect(
        account=cfg.get("account", "enqwqoj-dm29490").strip(),
        user=user,
        password=pwd,
        warehouse=cfg.get("warehouse", "COMPUTE_WH").strip() or "COMPUTE_WH",
        role=cfg.get("role", "ACCOUNTADMIN").strip() or "ACCOUNTADMIN",
        database=cfg.get("database", "BOLSA_FAMILIA").strip() or "BOLSA_FAMILIA",
        schema=cfg.get("schema", "PUBLIC").strip() or "PUBLIC",
        login_timeout=25,
        network_timeout=60,
        autocommit=True
    )
    return conn

def test_connection(cfg, log_fn=print):
    log_fn("[*] Testando conexão com Snowflake...")
    t0 = time.time()
    try:
        conn = get_connection(cfg)
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_VERSION()")
        row = cur.fetchone()
        ms = int((time.time() - t0) * 1000)
        conn.close()
        info = {
            "user": row[0],
            "role": row[1],
            "warehouse": row[2],
            "database": row[3],
            "schema": row[4],
            "version": row[5],
            "elapsed_ms": ms
        }
        log_fn(f"✅ [OK] Conexão bem-sucedida em {ms}ms!")
        log_fn(f"   • Usuário: {info['user']} | Perfil: {info['role']}")
        log_fn(f"   • Warehouse: {info['warehouse']} | Snowflake: {info['version']}")
        log_fn(f"   • Banco / Schema: {info['database']}.{info['schema']}")
        return True, info
    except Exception as e:
        log_fn(f"❌ [FALHA DE CONEXÃO]: {e}")
        return False, str(e)

def setup_ddls(cur, cfg, log_fn=print):
    db = cfg.get("database", "BOLSA_FAMILIA")
    sc = cfg.get("schema", "PUBLIC")
    ff = cfg.get("file_format", "FORMAT_PARQUET_GENERIC")
    stg = cfg.get("stage", "STAGE_BOLSA_FAMILIA")

    log_fn("[*] Verificando Database, Schema, Format e Stage...")
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {db};")
    cur.execute(f"USE DATABASE {db};")
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {sc};")
    cur.execute(f"USE SCHEMA {sc};")

    cur.execute(f"CREATE FILE FORMAT IF NOT EXISTS {ff} TYPE = 'PARQUET' COMPRESSION = 'AUTO';")
    cur.execute(f"CREATE STAGE IF NOT EXISTS {stg} FILE_FORMAT = {ff};")

    # 1. Tabela Dim_Populacao_UF_Municipios (8 Colunas idênticas ao Power BI)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS DIM_POPULACAO_UF_MUNICIPIOS (
        "Cod_Municipio_Siafi" NUMBER(38,0),
        "Homens" NUMBER(38,0),
        "Mulheres" NUMBER(38,0),
        "nome_municipio" VARCHAR(255),
        "Regiao_Macro" VARCHAR(100),
        "Regional" VARCHAR(100),
        "Tipo_de_Local" VARCHAR(50),
        "Ano" NUMBER(38,0),
        "Total" NUMBER(38,0),
        "uf" VARCHAR(10)
    );
    """)
    # Garantir que se a tabela já existia com 6 colunas, as 2 novas sejam adicionadas
    cur.execute("ALTER TABLE DIM_POPULACAO_UF_MUNICIPIOS ADD COLUMN IF NOT EXISTS \"Regiao_Macro\" VARCHAR(100);")
    cur.execute("ALTER TABLE DIM_POPULACAO_UF_MUNICIPIOS ADD COLUMN IF NOT EXISTS \"Regional\" VARCHAR(100);")
    cur.execute("ALTER TABLE DIM_POPULACAO_UF_MUNICIPIOS ADD COLUMN IF NOT EXISTS \"Tipo_de_Local\" VARCHAR(50);")
    cur.execute("ALTER TABLE DIM_POPULACAO_UF_MUNICIPIOS ADD COLUMN IF NOT EXISTS \"Ano\" NUMBER(38,0);")

    # 2. Tabela Fato_Bolsa_Familia_Redz (8 Colunas idênticas ao Power BI)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS FATO_BOLSA_FAMILIA_REDZ (
        "Cod_Municipio_Siafi" NUMBER(38,0),
        "Data" DATE,
        "Genero" VARCHAR(50),
        "mes_competencia" NUMBER(38,0),
        "nome_municipio" VARCHAR(255),
        "total_beneficiarios" NUMBER(38,0),
        "uf" VARCHAR(10),
        "valor_total_pago" NUMBER(18,2)
    );
    """)
    # Garantir que se a tabela já existia com 7 colunas, Cod_Municipio_Siafi seja adicionado
    cur.execute('ALTER TABLE FATO_BOLSA_FAMILIA_REDZ ADD COLUMN IF NOT EXISTS "Cod_Municipio_Siafi" NUMBER(38,0);')

    log_fn("✅ [OK] DDLs conferidos: FATO_BOLSA_FAMILIA_REDZ e DIM_POPULACAO_UF_MUNICIPIOS prontas!")

def upload_dim_populacao(cur, cfg, file_path=None, clean_stage=True, log_fn=print):
    fpath = file_path or find_pop_file()
    if not os.path.exists(fpath):
        log_fn(f"❌ [ERRO] Arquivo de população não encontrado em: {fpath}")
        return

    stg = cfg.get("stage", "STAGE_BOLSA_FAMILIA")
    ff = cfg.get("file_format", "FORMAT_PARQUET_GENERIC")
    fname = os.path.basename(fpath)
    fsize = os.path.getsize(fpath)

    log_fn(f"\n[1/2] 📤 Carregando DIM_POPULACAO_UF_MUNICIPIOS ({format_bytes(fsize)})...")
    t0 = time.time()

    # Truncar para carga limpa (dimensão de 5.570 linhas)
    cur.execute("TRUNCATE TABLE IF EXISTS DIM_POPULACAO_UF_MUNICIPIOS;")

    norm_path = fpath.replace(chr(92), "/")
    # PUT
    cur.execute(f"PUT 'file://{norm_path}' @{stg}/dimensoes/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE PARALLEL = 4;")
    # COPY INTO
    cur.execute(f"""
        COPY INTO DIM_POPULACAO_UF_MUNICIPIOS
        FROM @{stg}/dimensoes/{fname}
        FILE_FORMAT = (FORMAT_NAME = '{ff}')
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        ON_ERROR = 'CONTINUE';
    """)

    if clean_stage:
        cur.execute(f"REMOVE @{stg}/dimensoes/{fname};")

    cur.execute("SELECT COUNT(*) FROM DIM_POPULACAO_UF_MUNICIPIOS;")
    cnt = cur.fetchone()[0]
    log_fn(f"    ✅ DIM_POPULACAO_UF_MUNICIPIOS: {cnt:,} municípios carregados em {time.time()-t0:.1f}s!")

def upload_fato_redz(cur, cfg, file_path=None, clean_stage=True, log_fn=print):
    fpath = file_path or find_redz_file()
    if not os.path.exists(fpath):
        log_fn(f"❌ [ERRO] Arquivo Fato_Bolsa_Familia_Redz.parquet não encontrado em: {fpath}")
        return

    stg = cfg.get("stage", "STAGE_BOLSA_FAMILIA")
    ff = cfg.get("file_format", "FORMAT_PARQUET_GENERIC")
    fname = os.path.basename(fpath)
    fsize = os.path.getsize(fpath)

    log_fn(f"\n[2/2] 📤 Carregando FATO_BOLSA_FAMILIA_REDZ ({format_bytes(fsize)})...")
    t0 = time.time()

    # Truncar para carga atômica completa do arquivo consolidado Redz (~4.3 MB)
    cur.execute("TRUNCATE TABLE IF EXISTS FATO_BOLSA_FAMILIA_REDZ;")

    norm_path = fpath.replace(chr(92), "/")
    # PUT
    cur.execute(f"PUT 'file://{norm_path}' @{stg}/fato/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE PARALLEL = 4;")
    # COPY INTO
    cur.execute(f"""
        COPY INTO FATO_BOLSA_FAMILIA_REDZ
        FROM @{stg}/fato/{fname}
        FILE_FORMAT = (FORMAT_NAME = '{ff}')
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        ON_ERROR = 'CONTINUE';
    """)

    if clean_stage:
        cur.execute(f"REMOVE @{stg}/fato/{fname};")

    cur.execute("SELECT COUNT(*), COUNT(DISTINCT \"mes_competencia\"), SUM(\"valor_total_pago\") FROM FATO_BOLSA_FAMILIA_REDZ;")
    row = cur.fetchone()
    total_linhas = row[0] or 0
    total_meses = row[1] or 0
    total_pago = row[2] or 0.0

    log_fn(f"    ✅ FATO_BOLSA_FAMILIA_REDZ: {total_linhas:,} linhas ({total_meses} meses) em {time.time()-t0:.1f}s!")
    log_fn(f"    💰 Volume Total Pago: R$ {total_pago:,.2f}")

def main():
    cfg = load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_connection(cfg)
        return

    print("=" * 80)
    print(" >>> INGESTÃO BOLSA FAMÍLIA -> SNOWFLAKE (MODELO POWER BI) 🚀")
    print(f" Conta: {cfg.get('account')} | Database: {cfg.get('database')}.{cfg.get('schema')}")
    print("=" * 80)

    try:
        conn = get_connection(cfg)
        cur = conn.cursor()

        setup_ddls(cur, cfg)
        upload_dim_populacao(cur, cfg)
        upload_fato_redz(cur, cfg)

        conn.close()
        print("\n" + "=" * 80)
        print("✨ [SUCESSO] Ambas as tabelas foram carregadas no Snowflake!")
        print("👉 Próximo Passo: Abra o Power BI e atualize a conexão.")
        print("=" * 80)
    except Exception as e:
        print(f"❌ [ERRO]: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
