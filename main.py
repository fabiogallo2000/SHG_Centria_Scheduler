# -*- coding: utf-8 -*-
import sys
import warnings
warnings.filterwarnings("ignore")
import json
# import logging
import numpy as np
# import matplotlib.pyplot as plt
import pandas as pd
import time
from pathlib import Path
import datetime
import os

start_time = time.time()
# --- BLOCCO MAGICO PER PYINSTALLER ---
# Questo serve a capire se siamo in un EXE o in uno script normale
if getattr(sys, 'frozen', False):
    # Se siamo nell'eseguibile, la cartella base è quella temporanea (_MEIPASS)
    base_path = sys._MEIPASS
else:
    # Se siamo nello script python, la cartella base è quella del file
    base_path = os.path.dirname(os.path.abspath(__file__))

# Aggiungiamo questa cartella al percorso di sistema così Python trova i moduli
sys.path.append(base_path)

#from simulator.Photovoltaic import Photovoltaic
from simulator.Instance_SHG import Instance_SHG
from solver.shgso import SHGSO

if __name__ == '__main__':
    # log_name = "logs/hydromain.log"
    # logging.basicConfig(filename=log_name, format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO, datefmt="%H:%M:%S", filemode='w')
    start_time = time.time()
    # Secure the working dir
    
    if getattr(sys, 'frozen', False):
    # Caso ESEGUIBILE (.exe)
        base_dir = Path(sys.executable).parent
    else:
    # Caso SCRIPT (.py)
    # __file__ è il percorso dello script corrente
        base_dir = Path(__file__).parent.resolve()
        
    output_dir = base_dir / "risultati"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    input_json_path = base_dir / 'cfg' / 'input.json'
    # Importa il dizionario di configurazione da un file JSON, per esempio
    try:
        with open(input_json_path, 'r') as fp:
            param_dict = json.load(fp)
    except Exception as e:
        raise ValueError(f"Errore nella lettura del file input.json: {e}")
    
    # GUROBI parameters block
    # Extended info to console
    verbose = False
    # True if too much memory consumed
    NodefileStart = False
    
    #print("Starting...")
    # Instance creation in a dictinary for Guroby
    
    inst_shg = Instance_SHG(param_dict)

    # Solve
    problem = SHGSO(inst_shg)
    print("Solving Day-ahead scheduling...")

    all_simulation_results = []
    objective_values = []

    try:
        # 1. Esecuzione del solutore
        obj_funct, sol, comp_time = problem.solve(
            gap=inst_shg.gap,
            time_limit=inst_shg.time_limit, 
            verbose=True
        )
        
        # Controllo se il solutore ha restituito un errore interno (-1)
        if obj_funct == -1:
            raise ValueError("Il solutore Gurobi non è riuscito a trovare una soluzione ottimale (Stato Infeasible o Error).")

    except ValueError as e:
        # --- GESTIONE ERRORE CONFIGURAZIONE / INFEASIBILITY ---
        messaggio_errore = str(e)
        print(f"\n❌ ERRORE DI FATTIBILITÀ: {messaggio_errore}")
        
        error_json = {
            "status": "error",
            "error_type": "Infeasibility/Configuration",
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": messaggio_errore
        }

    # --- Vettori TOT dali sol (già aggregati correttamente) ---
    p_imp_values        = np.ravel(sol['P_imp'])[:problem.inst.T_steps+1]
    p_exp_values        = np.ravel(sol['P_exp'])[:problem.inst.T_steps+1]
    p_el_out_values     = np.ravel(sol['P_el_out'])[:problem.inst.T_steps+1]
    p_el_in_values      = np.ravel(sol['P_el_in'])[:problem.inst.T_steps+1]
    p_el_in_tot_values= np.ravel(sol['P_el_in_tot'])[:problem.inst.T_steps+1]
    h2_blend_values     = np.ravel(sol['H2_blend'])[:problem.inst.T_steps+1]
    h2_unmet_values     = np.ravel(sol['H2_unmet'])[:problem.inst.T_steps+1]
    S_warm = sol.get("s_warm", np.zeros((problem.inst.T_steps+1)))
    y_warm_up = sol.get("y_warm", np.zeros((problem.inst.T_steps+1)))
    y_run    = sol.get("y_run",     np.zeros((problem.inst.T_steps+1)))
    
    base_cols = {
        "Hour": np.arange(1, problem.inst.T_steps + 2).tolist(),
        "h2_blend_req": inst_shg.h2_blend[:problem.inst.T_steps+1].tolist(),
        "PV": inst_shg.p_pv[:problem.inst.T_steps+1].tolist(),
        "P_imp": p_imp_values.tolist(),
        "P_exp": p_exp_values.tolist(),
        "P_el_in": p_el_in_values.tolist(),
        "P_el_in_tot": p_el_in_tot_values.tolist(),
        "P_el_out": p_el_out_values.tolist(),
        "H2_to_blend": h2_blend_values.tolist(),
        "H2_unmet": h2_unmet_values.tolist(),
        "S_warm": S_warm.tolist(),
        "y_warm_up": y_warm_up.tolist(),
        "y_run": y_run.tolist()
    }

    sim_df = pd.DataFrame(base_cols)
    sim_df['Objective Function'] = obj_funct
    all_simulation_results.append(sim_df)
    
    # --- SALVATAGGIO IN EXCEL CON XLSXWRITER ---
    output_excel_path = output_dir / "Risultati_Scheduler.xlsx"
    
    h2_out_perc = (p_el_out_values/inst_shg.P_el_max_eq_h2) * 100
    
    def as_bool(a):
        a = np.asarray(a)
        return a.astype(float) != 0

    YW = as_bool(y_warm_up)   # shape: (T)
    YR = as_bool(y_run)       # shape: (T)
    SW = as_bool(S_warm)      # shape: (T)

    y_on_off_t = np.logical_or.reduce([YW, YR, SW]).astype(int)  # (T)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    output_json = {
        "status": "ok",
        "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "computation time": float(elapsed_time),
        "sampling_time": int(inst_shg.minutes),
        "Funzione Obiettivo": float(obj_funct),
        "Elettrolizzatore":{
            "Stato_Ely": y_on_off_t.tolist(),
            "h2_out_perc": h2_out_perc.tolist(),
        },
        "P_imp_grid": p_imp_values.tolist(),
        "P_exp_grid":p_exp_values.tolist()
        }
    
    try:
        # Usa xlsxwriter come motore invece di openpyxl
        sim_df.to_excel(output_excel_path, engine='xlsxwriter', index=False)
        print(f"\n✅ Excel creato con xlsxwriter: {output_excel_path}")
    except Exception as e:
        print(f"\n❌ Errore: {e}")
    
    # --- 9. SALVATAGGIO JSON FINALE ---
    output_filename = output_dir / "output_simulazione.json"
    try:
        with open(output_filename, 'w') as f:
            json.dump(output_json, f, indent=2)
    except Exception as e:
        print(f"\n❌ Errore: {e}")
