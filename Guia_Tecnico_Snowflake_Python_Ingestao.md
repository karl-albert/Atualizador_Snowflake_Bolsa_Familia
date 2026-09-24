# 📘 Guia Técnico de Arquitetura: Ingestão de Dados no Snowflake via Python (Bulk Loading)

**Projeto:** Dashboard Bolsa Família & Modelagem Analítica em Nuvem  
**Autor / Engenharia:** Karl / Antigravity Assistant  
**Tecnologias:** Snowflake Data Cloud, Python 3.14, DuckDB, Parquet, Apache Arrow  
**Documentação de Referência:** Snowflake Official Documentation (docs.snowflake.com)

---

## 1. Visão Geral e Arquitetura de Ingestão

O Snowflake adota um padrão de arquitetura de ingestão de dados em larga escala (**Bulk Loading**) estruturado em **duas etapas atômicas**:

1. **Etapa 1 — Staging (Armazenamento Temporário):**  
   Os arquivos locais (no nosso caso, arquivos binários colunares `.parquet`) são transferidos do ambiente local (*on-premises* ou máquina do usuário) diretamente para uma área de preparação interna do Snowflake, denominada **Internal Stage** (hospedada nativamente no Object Storage subjacente da nuvem da conta — AWS S3, Azure Blob ou Google Cloud Storage). Essa transferência é efetuada pelo comando **`PUT`**.

2. **Etapa 2 — Loading (Processamento e Gravação em Tabela):**  
   O *Virtual Warehouse* (cluster computacional do Snowflake) lê os dados binários do Stage, valida o formato, descompacta os metadados colunares e grava os registros nas **Micro-partições** proprietárias da tabela relacional de destino. Essa transformação é efetuada pelo comando **`COPY INTO <table>`**.

```mermaid
flowchart LR
    A["💻 Arquivos Parquet Locais (D:\1_Bases_Parquet)"] -->|snowflake.connector (PUT)| B["☁️ Snowflake Internal Stage (@STAGE_BOLSA_FAMILIA)"]
    B -->|Virtual Warehouse (COPY INTO)| C["📊 Tabela Relacional Snowflake (FATO_BOLSA_FAMILIA)"]
    C -->|Consultas SQL / Power BI DirectQuery| D["📈 Power BI / Analytics"]
```

---

## 2. Por que o Upload via Python supera a Interface Web (Snowsight)?

| Característica | Upload Web (Snowsight - "Load Data into Table") | Upload via Python (`PUT` + `COPY INTO`) |
| :--- | :--- | :--- |
| **Limite de Tamanho** | **Máximo de 250 MB por arquivo** | **Suporta arquivos de até 5 GB (ou sem limite via multipart)** |
| **Consumo de Memória** | Trava a aba do Chrome (lê o Parquet no motor V8 JavaScript) | Leve: streaming em blocos via socket TCP nativo |
| **Conexão e Fila** | Sujeito a timeouts de sessão HTTP no browser | Resiliente com reconexão automática e retry |
| **Processamento** | Sequencial e manual (um a um na tela) | **Multi-threaded (PARALLEL = 4 ou 8)** |
| **Automação** | Nenhuma | 100% automatizado em lote para dezenas de meses |

---

## 3. Implementação Técnica Passo a Passo no Python

A biblioteca oficial utilizada é o **`snowflake-connector-python`** (desenvolvida e mantida pela própria Snowflake Inc.).

### 3.1. Estabelecendo a Conexão

```python
import snowflake.connector

conn = snowflake.connector.connect(
    user='SEU_USUARIO',
    password='SUA_SENHA',
    account='enqwqoj-dm29490',       # Formato oficial: <organizacao>-<conta>
    warehouse='COMPUTE_WH',          # Virtual Warehouse responsável pelo processamento
    database='BOLSA_FAMILIA',        # Banco de dados de destino
    schema='PUBLIC',                 # Schema padrão
    role='ACCOUNTADMIN',             # Perfil com privilégios de criação de objetos
    login_timeout=20,
    network_timeout=60
)
cur = conn.cursor()
```

---

### 3.2. Preparação dos Objetos no Snowflake (DDL)

Antes de receber os dados, o Snowflake precisa ter o **Formato de Arquivo** e o **Stage** declarados:

```sql
-- 1. Cria o banco e schema se não existirem
CREATE DATABASE IF NOT EXISTS BOLSA_FAMILIA;
USE DATABASE BOLSA_FAMILIA;
CREATE SCHEMA IF NOT EXISTS PUBLIC;
USE SCHEMA PUBLIC;

-- 2. Define o formato de leitura para arquivos colunares Parquet
CREATE FILE FORMAT IF NOT EXISTS FORMAT_PARQUET_GENERIC 
    TYPE = 'PARQUET' 
    COMPRESSION = 'AUTO';

-- 3. Cria a área de preparação interna (Internal Stage)
CREATE STAGE IF NOT EXISTS STAGE_BOLSA_FAMILIA 
    FILE_FORMAT = FORMAT_PARQUET_GENERIC;
```

---

### 3.3. Criação da Tabela com Tipagem Otimizada

Para armazenar os dados detalhados do Bolsa Família com a máxima compressão colunar e sem desperdício de memória:

```sql
CREATE TABLE IF NOT EXISTS FATO_BOLSA_FAMILIA (
    "mes_competencia"      NUMBER(38,0),
    "mes_referencia"       NUMBER(38,0),
    "uf"                   VARCHAR(10),
    "cod_municipio_siafi"  VARCHAR(20),
    "nome_municipio"       VARCHAR(255),
    "cpf_favorecido"       VARCHAR(50),
    "nis_favorecido"       NUMBER(38,0),
    "nome_favorecido"      VARCHAR(255),
    "valor_parcela"        NUMBER(12,2)
);
```

---

### 3.4. O Comando `PUT` (Upload Local para a Nuvem)

O comando `PUT` é executado através do cursor do Python. Ele aceita o protocolo de caminho local `file://`:

```python
caminho_local = "D:/1_Bases_Parquet/detalhado/202303_NovoBolsaFamilia_fato.parquet"

sql_put = f"""
    PUT 'file://{caminho_local}' 
    @STAGE_BOLSA_FAMILIA 
    AUTO_COMPRESS = FALSE 
    OVERWRITE = TRUE 
    PARALLEL = 4;
"""
cur.execute(sql_put)
```

**Parâmetros Oficiais do `PUT`:**
* **`file://<path>`:** Caminho absoluto do arquivo no disco local (utilizando barras normais `/`).
* **`@STAGE_BOLSA_FAMILIA`:** Nome do Stage de destino.
* **`AUTO_COMPRESS = FALSE`:** Impede que o Snowflake tente recompactar em `.gz` um arquivo que já possui compressão nativa Parquet (ZSTD ou Snappy).
* **`OVERWRITE = TRUE`:** Substitui o arquivo no stage caso ele já tenha sido enviado anteriormente.
* **`PARALLEL = 4`:** Número de threads simultâneas para acelerar o upload em partes.

---

### 3.5. O Comando `COPY INTO` (Carga do Stage para a Tabela)

Assim que o arquivo se encontra no Stage, o comando `COPY INTO` transfere os dados para a tabela física:

```sql
COPY INTO FATO_BOLSA_FAMILIA
FROM @STAGE_BOLSA_FAMILIA/202303_NovoBolsaFamilia_fato.parquet
FILE_FORMAT = (FORMAT_NAME = 'FORMAT_PARQUET_GENERIC')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
ON_ERROR = 'CONTINUE';
```

**Parâmetros Oficiais do `COPY INTO`:**
* **`MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE`:** Mapeia automaticamente os campos do arquivo Parquet para as colunas da tabela pelo nome, ignorando maiúsculas e minúsculas.
* **`ON_ERROR = 'CONTINUE'`:** Em caso de eventual inconsistência em uma linha pontual, ignora a linha e prossegue carregando os milhões de outros registros sem abortar a transação.

---

## 4. Auditoria e Validação dos Dados Carregados

Após o carregamento via Python, a validação no Snowflake Worksheet é realizada com consultas SQL de conferência:

```sql
-- 1. Conferir quantidade de arquivos armazenados no Stage
LIST @STAGE_BOLSA_FAMILIA;

-- 2. Conferir volume total de linhas carregadas na tabela
SELECT 
    COUNT(*) AS total_registros,
    COUNT(DISTINCT mes_competencia) AS qtd_meses,
    MIN(mes_competencia) AS primeiro_mes,
    MAX(mes_competencia) AS ultimo_mes,
    SUM(valor_parcela) AS total_recursos_pagos
FROM FATO_BOLSA_FAMILIA;

-- 3. Amostragem dos dados carregados
SELECT * 
FROM FATO_BOLSA_FAMILIA 
LIMIT 50;
```

---

## 5. Links e Referências da Documentação Oficial Snowflake

Para consulta e enriquecimento da documentação corporativa:

1. **Snowflake Connector for Python (Visão Geral da Biblioteca Oficial):**  
   🔗 [https://docs.snowflake.com/en/developer-guide/python-connector/python-connector](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector)

2. **Carregamento em Lote com Python (Staging and Loading Data):**  
   🔗 [https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-example#staging-data-files-on-an-internal-stage](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-example#staging-data-files-on-an-internal-stage)

3. **Referência Oficial do Comando `PUT`:**  
   🔗 [https://docs.snowflake.com/en/sql-reference/sql/put](https://docs.snowflake.com/en/sql-reference/sql/put)

4. **Referência Oficial do Comando `COPY INTO <table>`:**  
   🔗 [https://docs.snowflake.com/en/sql-reference/sql/copy-into-table](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)

5. **Carregamento Específico de Arquivos Parquet no Snowflake:**  
   🔗 [https://docs.snowflake.com/en/user-guide/data-load-parquet](https://docs.snowflake.com/en/user-guide/data-load-parquet)

6. **Arquitetura de Carregamento de Dados (Overview):**  
   🔗 [https://docs.snowflake.com/en/user-guide/data-load-overview](https://docs.snowflake.com/en/user-guide/data-load-overview)

---
*Documento gerado e homologado para o ecossistema analítico Power BI / Snowflake.*
