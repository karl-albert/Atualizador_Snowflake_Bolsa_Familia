# ❄️ Ingestão Bolsa Família no Snowflake Data Cloud (Modelo Power BI)

Este diretório contém a esteira automatizada de ingestão em massa (**Bulk Loading**) do projeto **Bolsa Família** para o **Snowflake**, modelada exatamente para atender o **Power BI Desktop**.

---

## 📊 Tabelas Físicas Carregadas no Snowflake

| Tabela no Snowflake | Origem Local | Descrição |
| :--- | :--- | :--- |
| **`FATO_BOLSA_FAMILIA_REDZ`** | `Fato_Bolsa_Familia_Redz.parquet` (~4.3 MB) | Tabela Fato reduzida com 456.531 registros agregados por Data, Gênero (*Feminino/Masculino*), Município, UF, Mês, Total de Beneficiários e Valor Total Pago. |
| **`DIM_POPULACAO_UF_MUNICIPIOS`** | `fato_Populacao_UF_Municipios.parquet` (~131 KB) | Tabela Dimensão com os 5.570 municípios do IBGE (Nome do Município, Código SIAFI, UF, Homens, Mulheres e Total). |

> **Nota de Arquitetura:** Tabelas como `Medidas`, `Semaforo_Carga` e `dCalendario` não são enviadas para a nuvem porque são mantidas nativamente dentro do arquivo `.pbix` do Power BI Desktop.

---

## 📁 Arquivos do Projeto

| Arquivo | Função |
| :--- | :--- |
| **`Subir_Para_Snowflake.bat`** | Executável Desktop (duplo clique) para abrir a interface gráfica. |
| **`app_upload_snowflake_gui.py`** | Aplicação Desktop moderna com teste de conexão em tempo real, barra de progresso e terminal de logs ao vivo. |
| **`upload_bolsa_familia_snowflake.py`** | Motor Python de Bulk Loading via comandos atômicos `PUT` + `COPY INTO`. |
| **`snowflake_config.json`** | Arquivo de credenciais e parâmetros locais. |
| **`Guia_Tecnico_Snowflake_Python_Ingestao.md`** | Documentação técnica completa da arquitetura Snowflake. |

---

## 🚀 Como Executar a Carga

1. Dê um duplo clique em **`Subir_Para_Snowflake.bat`**.
2. Digite seu **Usuário** e **Senha** do Snowflake.
3. Clique em **`🔄 Testar Conexão Snowflake`** para validar o acesso.
4. Clique em **`🚀 INICIAR INGESTÃO NO SNOWFLAKE`**.
5. Em poucos segundos as duas tabelas estarão prontas no Snowflake.

---

## 🔗 Conectando o Power BI Desktop ao Snowflake

1. No **Power BI Desktop**, vá em: **Obter Dados** ➔ **Snowflake**.
2. **Servidor:** `enqwqoj-dm29490.snowflakecomputing.com`
3. **Warehouse:** `COMPUTE_WH`
4. **Modo:** Escolha **DirectQuery** ou **Import**.
5. Faça login com suas credenciais do Snowflake.
6. Navegue até o banco **`BOLSA_FAMILIA`** ➔ Schema **`PUBLIC`**.
7. Selecione as tabelas:
   * `FATO_BOLSA_FAMILIA_REDZ`
   * `DIM_POPULACAO_UF_MUNICIPIOS`
8. Pronto! Seu dashboard se conectará com máxima performance.
