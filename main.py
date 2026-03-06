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
from datetime import datetime, timedelta
import os

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
#from techfem_sim_json_5 import digital_twin

def f_interp(v):
    # 1. Creiamo l'asse temporale dei dati originali
    # Se v[0] è a 0s, v[1] a 300s, v[2] a 600s...
    # x_old saranno i "punti noti": [0, 300, 600, ..., (len(v)-1)*300]
    x_old = np.arange(len(v)) * 300
    
    # 2. Creiamo l'asse temporale di destinazione (ogni secondo della giornata)
    # x_new sono i punti dove vogliamo calcolare i valori: [0, 1, 2, ..., 86399]
    x_new = np.arange(86400)
    
    # 3. Eseguiamo l'interpolazione lineare
    # np.interp calcola i valori y corrispondenti a x_new basandosi sulla retta tra i punti di x_old
    vet_out = np.interp(x_new, x_old, v)
    
    return vet_out

# Converte eventuali array NumPy in liste Python serializzabili
def safe_tolist(data):
    """Converte numpy array in lista, lascia invariati gli altri tipi"""
    if isinstance(data, np.ndarray):
        return data.tolist()
    return data

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
        obj_funct, sol, comp_time = problem.solve(gap= inst_shg.gap,time_limit=inst_shg.time_limit, verbose=True)
        #exit()
    except ValueError as e:
        # Cattura l'eccezione con il messaggio di diagnosi e lo mostra al cliente
        print("\n========================= ERRORE DI CONFIGURAZIONE =========================")
        print(f"\nImpossibile trovare una soluzione fattibile. Causa probabile:\n")
        print(str(e)) # Stampa il messaggio dettagliato dalla nostra funzione di diagnosi
        print("\n============================================================================")
        print("\nEsecuzione interrotta. Modificare il file di input e riprovare.")
        exit()
    except Exception as e:
        # Cattura qualsiasi altro errore imprevisto
        print(f"\nSi è verificato un errore imprevisto: {e}")
        exit()


    # --- Vettori TOT dali sol (già aggregati correttamente) ---
    p_imp_values        = np.ravel(sol['P_imp'])[:problem.inst.T_steps+1]
    p_el_out_values     = np.ravel(sol['P_el_out'])[:problem.inst.T_steps+1]
    p_el_in_values      = np.ravel(sol['P_el_in'])[:problem.inst.T_steps+1]
    p_el_in_tot_values= np.ravel(sol['P_el_in_tot'])[:problem.inst.T_steps+1]
    h2_blend_values     = np.ravel(sol['H2_blend'])[:problem.inst.T_steps+1]
    
    S_warm = sol.get("s_warm", np.zeros((problem.inst.T_steps+1)))
    y_warm_up = sol.get("y_warm", np.zeros((problem.inst.T_steps+1)))
    y_run    = sol.get("y_run",     np.zeros((problem.inst.T_steps+1)))

    base_cols = {
        "Hour": np.arange(1, problem.inst.T_steps + 2),
        "P_PV": inst_shg.P_pv.tolist(),
        "P_imp": p_imp_values,
        "P_el_in": p_el_in_values,
        "P_el_in_tot": p_el_in_tot_values,
        "P_el_out": p_el_out_values,
        "H2_blend": h2_blend_values,
        "S_warm": S_warm,
        "y_warm_up": y_warm_up,
        "y_run": y_run
    }

    sim_df = pd.DataFrame(base_cols)
    sim_df['Objective Function'] = obj_funct
    all_simulation_results.append(sim_df)
    
# --- SALVATAGGIO IN EXCEL CON XLSXWRITER ---
    output_excel_path = output_dir / "Risultati_Scheduling.xlsx"
    
    try:
        # Usa xlsxwriter come motore invece di openpyxl
        sim_df.to_excel(output_excel_path, engine='xlsxwriter', index=False)
        print(f"\n✅ Excel creato con xlsxwriter: {output_excel_path}")
    except Exception as e:
        print(f"\n❌ Errore: {e}")
    # # Somma elemento-per-elemento delle potenze (se sono vettori)
    # P_ele_in_vec = (np.asarray(p_el_in_values))

    
    # # === ON/OFF per elettrolizzatore k e tempo t (1 se warm/run/stdby/s_warm attivo) ===
    # def as_bool(a):
    #     a = np.asarray(a)
    #     return a.astype(float) != 0

    # YW = as_bool(y_warm_up)   # shape: (n_ele, T)
    # YR = as_bool(y_run)       # shape: (n_ele, T)
    # YS = as_bool(y_stdby)     # shape: (n_ele, T)
    # SW = as_bool(S_warm)      # shape: (n_ele, T)

    # y_on_off_t = np.logical_or.reduce([YW, YR, YS, SW]).astype(int)  # (T)
    
    # # #Costrusisci il json di input per il digital twin
    # input_digital_twin = {
    #     "Ehss_start": float(E_h2_start),
    #     "P_ele_in":   safe_tolist(P_ele_in_vec),   # potenza ingresso elettrolizzatore (totale)
    #     "y_on_off_ele":  y_on_off_t.tolist(),     # stato ON-OFF
    #     "t_sim": len (P_ele_in_vec),
    #     "time_resolution": problem.inst.minutes,
    #     "H2_prod_ini_perc": inst_shg.H2_prod_ini_perc,
    #     "T_amb": inst_shg.T_amb,
    #     "z_el": inst_shg.z_el,
    #     "theta_el": inst_shg.theta_el,
    #     "P_el_max_eq_h2": inst_shg.P_el_max_eq_h2,
    #     "enable_plots": inst_shg.grafici_finali,
    #     'output_folder' : str(output_dir)
    # }

    # # --- 6. ESECUZIONE DIGITAL TWIN ---
    # output_finale, p_ausiliari_tot = digital_twin(input_digital_twin)

    # # --- 7. POST-PROCESSING RETE E FORMATTAZIONE (Stile API) ---
    # new_p_pv = f_interp(inst_shg.P_pv)
    # new_p_d = f_interp(inst_shg.P_d)
    
    # # Recupero dati grezzi dal DT per i calcoli
    # arr_fc = np.array(output_finale.get("fuel_cell", {}).get("potenza_erogata_kW", []), dtype=float)
    
    # # Somma verticale potenze elettrolizzatori
    # profili = [el["potenza_assorbita_kw"] for el in output_finale["elettrolizzatori"]]
    # matrice_ele = np.array(profili, dtype=float)
    # arr_ele_tot = np.sum(matrice_ele, axis=0)
    
    # # Debug delle dimensioni
    # # debug_vars = {
    # # "arr_fc": arr_fc,
    # # "eta_inv": inst_shg.eta_inv,
    # # "new_p_pv": new_p_pv,
    # # "p_ausiliari_tot": p_ausiliari_tot,
    # # "new_p_d": new_p_d,
    # # "arr_ele_tot": arr_ele_tot
    # # }

    # # for nome, var in debug_vars.items():
    # #     shape = getattr(var, 'shape', 'N/A (not an array/series)')
    # #     print(f"{nome}: shape = {shape}")
    #     # Delta > 0 (Surplus), Delta < 0 (Deficit)
    # Delta = arr_fc * inst_shg.eta_inv + new_p_pv - p_ausiliari_tot - new_p_d - arr_ele_tot

    # P_exp_fin = np.zeros(len(Delta))
    # P_imp_fin = np.zeros(len(Delta))
    
    # for t in range(len(Delta)):
    #     if Delta[t] >= 0:
    #         P_exp_fin[t] = Delta[t]
    #     if Delta[t] < 0:
    #         P_imp_fin[t] = -Delta[t]

    # # --- 8. CREAZIONE DIZIONARIO "PIATTO" (Come API) ---
    
    # # Estrazione liste
    # hss_pressure = safe_tolist(output_finale.get("serbatoio", {}).get("pressione_serbatoio_h2", []))

    # potenze_previste = {}
    # potenze_previste["P_fc_out"] = safe_tolist(arr_fc * 100 / inst_shg.P_fc_max) # percentuale
    # potenze_previste["p_hss"] = hss_pressure

    # # Ciclo per appiattire gli elettrolizzatori (P_ely_in_1, P_ely_in_2...)
    # if "elettrolizzatori" in output_finale:
    #     for i, el in enumerate(output_finale["elettrolizzatori"]):
            
    #         # 2. Gestione Stato Logico (Nuova aggiunta)
    #         key_stato = f"Stato_Ely_{i+1}"
    #         # Recupera la lista degli stati (0, 1, 2, 3)
    #         potenze_previste[key_stato] = el.get("stato_logico", [])
            
    #         key_h2_perc = f"h2_out_perc_{i+1}"
    #         potenze_previste[key_h2_perc] = el.get("carico_h2_percentuale", [])

    # # Aggiunta vettori rete
    # potenze_previste["P_imp_grid"] = np.round(P_imp_fin, 3).tolist()
    # potenze_previste["P_exp_grid"] = np.round(P_exp_fin, 3).tolist()

    # end_time = time.time()
    # elapsed_time = end_time - start_time
    
    # # Struttura finale identica alla response FastAPI
    # json_output_api_style = {
    #     "status": "Ok",
    #     "datetime": datetime.now().isoformat(),
    #     "computation time": elapsed_time,
    #     "sampling time": 5,
    #     "Funzione Obiettivo": obj_funct,
    #     "Risultati previsti": potenze_previste
    # }

    # # --- 9. SALVATAGGIO JSON FINALE ---
    # output_filename = output_dir / "output_simulazione.json"
    
    # with open(output_filename, 'w') as f:
    #     json.dump(json_output_api_style, f, indent=2)
    
    # print(f" Tempo di simulazione: {elapsed_time:.2f} secondi")
    # #print(f" File salvati in: {output_dir}")