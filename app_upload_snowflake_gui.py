"""
========================================================================================
Projeto: Dashboard Bolsa Família (Power BI / Snowflake Data Cloud)
Aplicativo: Ingestão de Dados no Snowflake (Modelo Estrela Power BI: Redz + População)
Autor: Karl / Antigravity Assistant
========================================================================================
"""

import sys
import os
import glob
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

try:
    import snowflake.connector
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "snowflake-connector-python"])
    import snowflake.connector

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "snowflake_config.json")

BASE_D = r"D:\1_Bases_Parquet"
BASE_C = r"C:\000 - Karl\116 - Dashbords\Projetos_Power_BI\Bolsa_Familia\0_Bases_de_Dados"

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def find_redz_default():
    candidates = [
        os.path.join(BASE_D, "Fato_Bolsa_Familia_Redz.parquet"),
        os.path.join(BASE_C, "Fato_Bolsa_Familia_Redz.parquet")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

def find_pop_default():
    candidates = [
        os.path.join(BASE_D, "dimensoes", "fato_Populacao_UF_Municipios.parquet"),
        os.path.join(BASE_C, "dimensoes", "fato_Populacao_UF_Municipios.parquet")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

class AppUploadSnowflake(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("❄️ Ingestão Bolsa Família para Snowflake (Modelo Power BI)")
        self.geometry("950x860")
        self.minsize(900, 750)
        self.configure(bg="#f4f6f9")

        self.center_window()

        # Parâmetros de Conexão
        self.var_account = tk.StringVar(value="enqwqoj-dm29490")
        self.var_user = tk.StringVar(value="")
        self.var_password = tk.StringVar(value="")
        self.var_warehouse = tk.StringVar(value="COMPUTE_WH")
        self.var_database = tk.StringVar(value="BOLSA_FAMILIA")
        self.var_schema = tk.StringVar(value="PUBLIC")
        self.var_role = tk.StringVar(value="ACCOUNTADMIN")
        self.var_stage = tk.StringVar(value="STAGE_BOLSA_FAMILIA")
        self.var_file_format = tk.StringVar(value="FORMAT_PARQUET_GENERIC")

        # Caminhos dos 2 Arquivos Exatos do Power BI
        self.var_path_redz = tk.StringVar(value=find_redz_default())
        self.var_path_pop = tk.StringVar(value=find_pop_default())

        # Checkboxes de Carga
        self.var_sync_redz = tk.BooleanVar(value=True)
        self.var_sync_pop = tk.BooleanVar(value=True)
        self.var_clean_stage = tk.BooleanVar(value=True)

        self.show_password = False
        self.is_running = False

        self.load_settings()
        self.create_widgets()

        if self.var_user.get().strip() and self.var_password.get().strip():
            self.check_connection_async()

    def center_window(self):
        self.update_idletasks()
        w, h = 950, 860
        x = max(0, (self.winfo_screenwidth() // 2) - (w // 2))
        y = max(0, (self.winfo_screenheight() // 2) - (h // 2) - 15)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.var_account.set(cfg.get("account", "enqwqoj-dm29490"))
                    self.var_user.set(cfg.get("user", ""))
                    self.var_password.set(cfg.get("password", ""))
                    self.var_warehouse.set(cfg.get("warehouse", "COMPUTE_WH"))
                    self.var_database.set(cfg.get("database", "BOLSA_FAMILIA"))
                    self.var_schema.set(cfg.get("schema", "PUBLIC"))
                    self.var_role.set(cfg.get("role", "ACCOUNTADMIN"))
                    self.var_stage.set(cfg.get("stage", "STAGE_BOLSA_FAMILIA"))
            except Exception:
                pass

    def save_settings(self, show_msg=True):
        cfg = {
            "account": self.var_account.get().strip(),
            "user": self.var_user.get().strip(),
            "password": self.var_password.get().strip(),
            "warehouse": self.var_warehouse.get().strip(),
            "database": self.var_database.get().strip(),
            "schema": self.var_schema.get().strip(),
            "role": self.var_role.get().strip(),
            "stage": self.var_stage.get().strip(),
            "file_format": self.var_file_format.get().strip()
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
            if show_msg:
                messagebox.showinfo("Configurações Salvas", f"Configurações gravadas com sucesso em:\n{CONFIG_FILE}")
        except Exception as e:
            if show_msg:
                messagebox.showerror("Erro", f"Não foi possível salvar:\n{e}")

    # Thread-safe Helpers
    def safe_log(self, msg):
        def _u():
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
        self.after(0, _u)

    def safe_status(self, text, progress=None):
        def _u():
            self.lbl_status.config(text=text)
            if progress is not None:
                self.progress_bar["value"] = progress
        self.after(0, _u)

    def safe_enable_buttons(self):
        def _u():
            self.is_running = False
            if hasattr(self, 'btn_ddl'):
                self.btn_ddl.config(state="normal", bg="#0f766e", text="📐 CRIAR APENAS TABELAS VAZIAS (DDL)")
            self.btn_iniciar.config(state="normal", bg="#0284c7", text="🚀 INICIAR INGESTÃO COMPLETA (DADOS)")
            self.btn_test_conn.config(state="normal")
            self.btn_save.config(state="normal")
        self.after(0, _u)

    def create_widgets(self):
        # Top Header
        header = tk.Frame(self, bg="#0f172a", height=78)
        header.pack(fill="x")

        lbl_title = tk.Label(
            header,
            text="❄️ Carga Bolsa Família para Snowflake (Modelo Power BI)",
            font=("Segoe UI", 15, "bold"),
            fg="#ffffff",
            bg="#0f172a"
        )
        lbl_title.pack(anchor="w", padx=25, pady=(12, 2))

        lbl_sub = tk.Label(
            header,
            text="Ingestão Otimizada: Fato_Bolsa_Familia_Redz + Dim_Populacao_UF_Municipios | Sem poluição de tabelas no Snowflake",
            font=("Segoe UI", 9),
            fg="#38bdf8",
            bg="#0f172a"
        )
        lbl_sub.pack(anchor="w", padx=25, pady=(0, 12))

        # Container
        container = tk.Frame(self, bg="#f4f6f9", padx=20, pady=10)
        container.pack(fill="both", expand=True)

        # ---------------------------------------------------------------------
        # SEÇÃO 1: Credenciais & Conexão Snowflake
        # ---------------------------------------------------------------------
        sec_snw = tk.LabelFrame(
            container,
            text=" ❄️ 1. Parâmetros e Credenciais da Conta Snowflake ",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#1e293b",
            padx=15,
            pady=6,
            relief="groove"
        )
        sec_snw.pack(fill="x", pady=(0, 8))

        grid_conn = tk.Frame(sec_snw, bg="#ffffff")
        grid_conn.pack(fill="x")

        # Conta e Warehouse
        tk.Label(grid_conn, text="Conta (Account):", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=0, column=0, sticky="w", pady=2)
        tk.Entry(grid_conn, textvariable=self.var_account, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=28).grid(row=0, column=1, sticky="w", padx=(6, 20), pady=2)

        tk.Label(grid_conn, text="Warehouse:", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=0, column=2, sticky="w", pady=2)
        tk.Entry(grid_conn, textvariable=self.var_warehouse, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=18).grid(row=0, column=3, sticky="w", padx=(6, 0), pady=2)

        # Usuário e Senha
        tk.Label(grid_conn, text="Usuário (Login):", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=1, column=0, sticky="w", pady=2)
        tk.Entry(grid_conn, textvariable=self.var_user, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=28).grid(row=1, column=1, sticky="w", padx=(6, 20), pady=2)

        tk.Label(grid_conn, text="Senha:", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=1, column=2, sticky="w", pady=2)
        frame_pwd = tk.Frame(grid_conn, bg="#ffffff")
        frame_pwd.grid(row=1, column=3, sticky="w", pady=2)

        self.ent_pwd = tk.Entry(frame_pwd, textvariable=self.var_password, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, show="*", width=14)
        self.ent_pwd.pack(side="left", padx=(6, 4))
        self.btn_toggle_pwd = tk.Button(frame_pwd, text="👁️", command=self.toggle_pwd_visibility, font=("Segoe UI", 7), bg="#f1f5f9", relief="groove", padx=3)
        self.btn_toggle_pwd.pack(side="left")

        # Database e Role
        tk.Label(grid_conn, text="Database / Schema:", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=2, column=0, sticky="w", pady=2)
        frame_db = tk.Frame(grid_conn, bg="#ffffff")
        frame_db.grid(row=2, column=1, sticky="w", padx=(6, 20), pady=2)
        tk.Entry(frame_db, textvariable=self.var_database, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=14).pack(side="left")
        tk.Label(frame_db, text=".", font=("Segoe UI", 9, "bold"), bg="#ffffff").pack(side="left")
        tk.Entry(frame_db, textvariable=self.var_schema, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=10).pack(side="left")

        tk.Label(grid_conn, text="Role:", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#475569").grid(row=2, column=2, sticky="w", pady=2)
        tk.Entry(grid_conn, textvariable=self.var_role, font=("Segoe UI", 9), bg="#f8fafc", relief="solid", bd=1, width=18).grid(row=2, column=3, sticky="w", padx=(6, 0), pady=2)

        # Barra de status de conexão e botões
        frame_conn_bar = tk.Frame(sec_snw, bg="#ffffff")
        frame_conn_bar.pack(fill="x", pady=(8, 2))

        self.lbl_conn_status = tk.Label(frame_conn_bar, text="⚪ Status: Insira usuário e senha para testar", font=("Segoe UI", 8, "bold"), bg="#ffffff", fg="#64748b")
        self.lbl_conn_status.pack(side="left")

        self.btn_save = tk.Button(
            frame_conn_bar,
            text="💾 Salvar Configurações",
            command=lambda: self.save_settings(show_msg=True),
            bg="#f1f5f9",
            fg="#1e293b",
            font=("Segoe UI", 8, "bold"),
            relief="groove",
            padx=10
        )
        self.btn_save.pack(side="right", padx=(8, 0))

        self.btn_test_conn = tk.Button(
            frame_conn_bar,
            text="🔄 Testar Conexão Snowflake",
            command=self.check_connection_async,
            bg="#f0f9ff",
            fg="#0284c7",
            font=("Segoe UI", 8, "bold"),
            relief="groove",
            padx=10
        )
        self.btn_test_conn.pack(side="right")

        # ---------------------------------------------------------------------
        # SEÇÃO 2: Tabelas Exatas do Modelo Power BI
        # ---------------------------------------------------------------------
        sec_tabs = tk.LabelFrame(
            container,
            text=" 📊 2. Tabelas para Ingestão (Espelho Fiel do Power BI) ",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0369a1",
            padx=15,
            pady=8,
            relief="groove"
        )
        sec_tabs.pack(fill="x", pady=(0, 8))

        # Tabela 1: Fato_Bolsa_Familia_Redz
        f_t1 = tk.Frame(sec_tabs, bg="#ffffff")
        f_t1.pack(fill="x", pady=(0, 6))

        chk_t1 = tk.Checkbutton(
            f_t1,
            text="Fato_Bolsa_Familia_Redz  (~4.3 MB | 456k registros | 8 Colunas: SIAFI, Data, Gênero, Município, Total, Valor)",
            variable=self.var_sync_redz,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a"
        )
        chk_t1.pack(anchor="w")

        f_path1 = tk.Frame(f_t1, bg="#ffffff")
        f_path1.pack(fill="x", padx=(20, 0))
        tk.Entry(f_path1, textvariable=self.var_path_redz, font=("Segoe UI", 8), bg="#f8fafc", relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=2)
        tk.Button(f_path1, text="Procurar...", command=self.browse_redz, font=("Segoe UI", 7, "bold"), bg="#e2e8f0").pack(side="right", padx=(6, 0))

        # Tabela 2: Dim_Populacao_UF_Municipios
        f_t2 = tk.Frame(sec_tabs, bg="#ffffff")
        f_t2.pack(fill="x", pady=(4, 6))

        chk_t2 = tk.Checkbutton(
            f_t2,
            text="Dim_Populacao_UF_Municipios  (~131 KB | 5.570 municípios IBGE | 8 Colunas: SIAFI, População, Regiao_Macro, Regional)",
            variable=self.var_sync_pop,
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#0f172a"
        )
        chk_t2.pack(anchor="w")

        f_path2 = tk.Frame(f_t2, bg="#ffffff")
        f_path2.pack(fill="x", padx=(20, 0))
        tk.Entry(f_path2, textvariable=self.var_path_pop, font=("Segoe UI", 8), bg="#f8fafc", relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=2)
        tk.Button(f_path2, text="Procurar...", command=self.browse_pop, font=("Segoe UI", 7, "bold"), bg="#e2e8f0").pack(side="right", padx=(6, 0))

        # Nota informativa sobre o que fica no Power BI
        f_info = tk.Frame(sec_tabs, bg="#f8fafc", padx=8, pady=6, relief="solid", bd=1)
        f_info.pack(fill="x", pady=(4, 0))
        tk.Label(
            f_info,
            text="💡 Observação: Medidas, Semaforo_Carga e dCalendario não sobem para a nuvem pois são tratados diretamente dentro do Power BI Desktop.",
            font=("Segoe UI", 8, "italic"),
            bg="#f8fafc",
            fg="#475569"
        ).pack(anchor="w")

        # ---------------------------------------------------------------------
        # SEÇÃO 3: Ação & Barra de Progresso
        # ---------------------------------------------------------------------
        sec_action = tk.Frame(container, bg="#f4f6f9")
        sec_action.pack(fill="x", pady=(2, 6))

        frame_stat = tk.Frame(sec_action, bg="#f4f6f9")
        frame_stat.pack(fill="x", pady=(0, 2))

        self.lbl_status = tk.Label(frame_stat, text="Pronto para iniciar ingestão.", font=("Segoe UI", 9, "bold"), bg="#f4f6f9", fg="#1e293b")
        self.lbl_status.pack(side="left")

        tk.Checkbutton(
            frame_stat,
            text="🧹 Limpar stage após ingestão",
            variable=self.var_clean_stage,
            font=("Segoe UI", 8),
            bg="#f4f6f9",
            fg="#0369a1"
        ).pack(side="right")

        self.progress_bar = ttk.Progressbar(sec_action, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", ipady=3, pady=(0, 6))

        # Dois botões de ação: Criar Tabelas Vazias vs Ingestão Completa
        frame_action_btns = tk.Frame(sec_action, bg="#f4f6f9")
        frame_action_btns.pack(fill="x")

        self.btn_ddl = tk.Button(
            frame_action_btns,
            text="📐 CRIAR APENAS TABELAS VAZIAS (DDL)",
            command=self.start_ddl_thread,
            bg="#0f766e",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            pady=8,
            cursor="hand2"
        )
        self.btn_ddl.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_iniciar = tk.Button(
            frame_action_btns,
            text="🚀 INICIAR INGESTÃO COMPLETA (DADOS)",
            command=self.start_ingestion_thread,
            bg="#0284c7",
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            pady=8,
            cursor="hand2"
        )
        self.btn_iniciar.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # ---------------------------------------------------------------------
        # SEÇÃO 4: Terminal de Logs ao Vivo
        # ---------------------------------------------------------------------
        sec_log = tk.LabelFrame(
            container,
            text=" 🖥️ 3. Console de Execução & Logs Snowflake ao Vivo ",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#1e293b",
            padx=10,
            pady=6,
            relief="groove"
        )
        sec_log.pack(fill="both", expand=True)

        frame_txt = tk.Frame(sec_log, bg="#0f172a")
        frame_txt.pack(fill="both", expand=True)

        self.txt_log = tk.Text(
            frame_txt,
            bg="#0b132b",
            fg="#e0e7ff",
            font=("Consolas", 9),
            relief="flat",
            wrap="word"
        )
        self.txt_log.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        scrollbar = tk.Scrollbar(frame_txt, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=scrollbar.set)

        frame_log_btns = tk.Frame(sec_log, bg="#ffffff")
        frame_log_btns.pack(fill="x", pady=(4, 0))

        tk.Button(
            frame_log_btns,
            text="📋 Copiar Logs",
            command=self.copy_logs,
            bg="#f1f5f9",
            fg="#475569",
            font=("Segoe UI", 7, "bold"),
            relief="groove"
        ).pack(side="right", padx=(4, 0))

        tk.Button(
            frame_log_btns,
            text="🧹 Limpar Terminal",
            command=lambda: self.txt_log.delete("1.0", "end"),
            bg="#f1f5f9",
            fg="#475569",
            font=("Segoe UI", 7, "bold"),
            relief="groove"
        ).pack(side="right")

    # Handlers
    def toggle_pwd_visibility(self):
        if self.show_password:
            self.ent_pwd.config(show="*")
            self.btn_toggle_pwd.config(text="👁️")
            self.show_password = False
        else:
            self.ent_pwd.config(show="")
            self.btn_toggle_pwd.config(text="🔒")
            self.show_password = True

    def browse_redz(self):
        f = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.var_path_redz.get()),
            title="Selecione Fato_Bolsa_Familia_Redz.parquet",
            filetypes=[("Parquet Files", "*.parquet")]
        )
        if f:
            self.var_path_redz.set(f)

    def browse_pop(self):
        f = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.var_path_pop.get()),
            title="Selecione fato_Populacao_UF_Municipios.parquet",
            filetypes=[("Parquet Files", "*.parquet")]
        )
        if f:
            self.var_path_pop.set(f)

    def copy_logs(self):
        self.clipboard_clear()
        self.clipboard_append(self.txt_log.get("1.0", "end-1c"))
        messagebox.showinfo("Copiado", "Logs copiados para a área de transferência!")

    # Teste de Conexão
    def check_connection_async(self):
        self.lbl_conn_status.config(text="⏳ Testando conexão com Snowflake...", fg="#d97706")
        self.btn_test_conn.config(state="disabled")
        threading.Thread(target=self._worker_test_conn, daemon=True).start()

    def _worker_test_conn(self):
        cfg = {
            "account": self.var_account.get().strip(),
            "user": self.var_user.get().strip(),
            "password": self.var_password.get().strip(),
            "warehouse": self.var_warehouse.get().strip(),
            "database": self.var_database.get().strip(),
            "schema": self.var_schema.get().strip(),
            "role": self.var_role.get().strip()
        }
        if not cfg["user"] or not cfg["password"]:
            def _empty():
                self.lbl_conn_status.config(text="⚠️ Preencha Usuário e Senha para testar", fg="#b45309")
                self.btn_test_conn.config(state="normal")
            self.after(0, _empty)
            return

        try:
            t0 = time.time()
            conn = snowflake.connector.connect(
                account=cfg["account"],
                user=cfg["user"],
                password=cfg["password"],
                warehouse=cfg["warehouse"] or "COMPUTE_WH",
                role=cfg["role"] or "ACCOUNTADMIN",
                database=cfg["database"] or "BOLSA_FAMILIA",
                schema=cfg["schema"] or "PUBLIC",
                login_timeout=20,
                network_timeout=45
            )
            cur = conn.cursor()
            cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_VERSION()")
            row = cur.fetchone()
            ms = int((time.time() - t0) * 1000)
            conn.close()

            def _ok():
                self.lbl_conn_status.config(
                    text=f"✅ Conectado! (v{row[3]} | WH: {row[2]} | {ms}ms)",
                    fg="#15803d"
                )
                self.safe_log(f"✅ [SNOWFLAKE CONECTADO] Usuário: {row[0]} | Role: {row[1]} | Warehouse: {row[2]} | Versão: {row[3]} ({ms}ms)")
                self.btn_test_conn.config(state="normal")
                self.save_settings(show_msg=False)
            self.after(0, _ok)
        except Exception as e:
            err_msg = str(e)
            def _err():
                self.lbl_conn_status.config(text="❌ Falha na conexão com Snowflake", fg="#dc2626")
                self.safe_log(f"❌ [ERRO DE CONEXÃO SNOWFLAKE]: {err_msg}")
                self.btn_test_conn.config(state="normal")
            self.after(0, _err)

    # =========================================================================
    # CRIAÇÃO DE TABELAS VAZIAS (DDL ONLY)
    # =========================================================================
    def start_ddl_thread(self):
        if self.is_running:
            return

        if not self.var_user.get().strip() or not self.var_password.get().strip():
            messagebox.showwarning("Credenciais Incompletas", "Informe o Usuário e a Senha do Snowflake antes de criar as tabelas!")
            return

        self.save_settings(show_msg=False)
        self.is_running = True
        self.btn_ddl.config(state="disabled", bg="#64748b", text="⏳ CRIANDO TABELAS...")
        self.btn_iniciar.config(state="disabled", bg="#64748b")
        self.btn_test_conn.config(state="disabled")
        self.btn_save.config(state="disabled")
        self.progress_bar["value"] = 30

        threading.Thread(target=self._worker_ddl, daemon=True).start()

    def _worker_ddl(self):
        try:
            from upload_bolsa_familia_snowflake import get_connection, setup_ddls
        except ImportError:
            sys.path.insert(0, SCRIPT_DIR)
            from upload_bolsa_familia_snowflake import get_connection, setup_ddls

        cfg = {
            "account": self.var_account.get().strip(),
            "user": self.var_user.get().strip(),
            "password": self.var_password.get().strip(),
            "warehouse": self.var_warehouse.get().strip(),
            "database": self.var_database.get().strip(),
            "schema": self.var_schema.get().strip(),
            "role": self.var_role.get().strip(),
            "stage": self.var_stage.get().strip(),
            "file_format": self.var_file_format.get().strip()
        }

        self.safe_log("\n" + "=" * 80)
        self.safe_log(" >>> CRIANDO TABELAS VAZIAS NO SNOWFLAKE (DDL SETUP) 📐")
        self.safe_log(f" [CONTA]: {cfg['account']} | [DATABASE]: {cfg['database']}.{cfg['schema']}")
        self.safe_log("=" * 80)

        try:
            self.safe_status("Conectando ao Snowflake e criando estruturas DDL vazias...", 50)
            conn = get_connection(cfg)
            cur = conn.cursor()

            setup_ddls(cur, cfg, log_fn=self.safe_log)

            conn.close()
            self.safe_status("✨ Tabelas vazias criadas com sucesso no Snowflake!", 100)
            self.safe_log("\n🎉 [SUCESSO] Tabelas criadas no Snowflake:")
            self.safe_log("   1. FATO_BOLSA_FAMILIA_REDZ (Vazia - 0 registros)")
            self.safe_log("   2. DIM_POPULACAO_UF_MUNICIPIOS (Vazia - 0 registros)")
            self.safe_log("👉 Vá até o Snowflake, clique no botão 🔄 de atualizar a árvore e conecte o Power BI!")
            self.safe_log("=" * 80)
            messagebox.showinfo(
                "Tabelas Criadas com Sucesso!",
                "As estruturas das tabelas FATO_BOLSA_FAMILIA_REDZ e DIM_POPULACAO_UF_MUNICIPIOS foram criadas com sucesso (vazias, sem dados) no Snowflake!\n\n"
                "Você já pode dar Refresh no Snowflake e conectar o Power BI Desktop nelas para testar a conexão."
            )
        except Exception as e:
            self.safe_status("❌ Erro ao criar tabelas.", 0)
            self.safe_log(f"\n❌ [ERRO]: {e}")
            messagebox.showerror("Erro ao Criar Tabelas", f"Ocorreu um erro no Snowflake:\n\n{e}")
        finally:
            self.safe_enable_buttons()

    # Ingestão
    def start_ingestion_thread(self):
        if self.is_running:
            return

        if not self.var_user.get().strip() or not self.var_password.get().strip():
            messagebox.showwarning("Credenciais Incompletas", "Informe o Usuário e a Senha antes de iniciar!")
            return

        self.save_settings(show_msg=False)
        self.is_running = True
        self.btn_iniciar.config(state="disabled", bg="#64748b", text="⏳ EXECUTANDO INGESTÃO NO SNOWFLAKE...")
        self.btn_test_conn.config(state="disabled")
        self.btn_save.config(state="disabled")
        self.progress_bar["value"] = 0

        threading.Thread(target=self._worker_ingestion, daemon=True).start()

    def _worker_ingestion(self):
        try:
            from upload_bolsa_familia_snowflake import (
                get_connection, setup_ddls, upload_dim_populacao,
                upload_fato_redz
            )
        except ImportError:
            sys.path.insert(0, SCRIPT_DIR)
            from upload_bolsa_familia_snowflake import (
                get_connection, setup_ddls, upload_dim_populacao,
                upload_fato_redz
            )

        cfg = {
            "account": self.var_account.get().strip(),
            "user": self.var_user.get().strip(),
            "password": self.var_password.get().strip(),
            "warehouse": self.var_warehouse.get().strip(),
            "database": self.var_database.get().strip(),
            "schema": self.var_schema.get().strip(),
            "role": self.var_role.get().strip(),
            "stage": self.var_stage.get().strip(),
            "file_format": self.var_file_format.get().strip()
        }

        clean_stage = self.var_clean_stage.get()

        self.safe_log("\n" + "=" * 80)
        self.safe_log(" >>> INICIANDO PIPELINE DE CARGA NO SNOWFLAKE (MODELO POWER BI) 🚀")
        self.safe_log(f" [CONTA]: {cfg['account']} | [DATABASE]: {cfg['database']}.{cfg['schema']}")
        self.safe_log(f" [WAREHOUSE]: {cfg['warehouse']} | [STAGE]: @{cfg['stage']}")
        self.safe_log("=" * 80)

        try:
            self.safe_status("Conectando ao Snowflake e configurando DDLs...", 10)
            conn = get_connection(cfg)
            cur = conn.cursor()

            setup_ddls(cur, cfg, log_fn=self.safe_log)

            # 1. Dim_Populacao_UF_Municipios
            if self.var_sync_pop.get():
                self.safe_status("Carregando Dim_Populacao_UF_Municipios...", 30)
                upload_dim_populacao(cur, cfg, file_path=self.var_path_pop.get(), clean_stage=clean_stage, log_fn=self.safe_log)

            # 2. Fato_Bolsa_Familia_Redz
            if self.var_sync_redz.get():
                self.safe_status("Carregando Fato_Bolsa_Familia_Redz...", 65)
                upload_fato_redz(cur, cfg, file_path=self.var_path_redz.get(), clean_stage=clean_stage, log_fn=self.safe_log)

            conn.close()
            self.safe_status("✨ Ingestão finalizada com sucesso no Snowflake!", 100)
            self.safe_log("\n" + "=" * 80)
            self.safe_log("🎉 >>> CARGA FINALIZADA COM SUCESSO TOTAL NO SNOWFLAKE! 🚀")
            self.safe_log("👉 Suas 2 tabelas (Fato_Bolsa_Familia_Redz e Dim_Populacao_UF_Municipios) já estão disponíveis!")
            self.safe_log("=" * 80)
            messagebox.showinfo(
                "Sucesso Total",
                "Carga concluída com sucesso no Snowflake Data Cloud!\n\n"
                "As tabelas Fato_Bolsa_Familia_Redz e Dim_Populacao_UF_Municipios já estão disponíveis para consulta e atualização no Power BI."
            )
        except Exception as e:
            self.safe_status("❌ Erro durante a ingestão.", 0)
            self.safe_log(f"\n❌ [ERRO CRÍTICO]: {e}")
            messagebox.showerror("Erro na Carga", f"Ocorreu um erro durante a ingestão:\n\n{e}")
        finally:
            self.safe_enable_buttons()

if __name__ == "__main__":
    app = AppUploadSnowflake()
    app.mainloop()
