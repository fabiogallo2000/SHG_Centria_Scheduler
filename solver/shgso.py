# -*- coding: utf-8 -*-
import time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import math
"""

SmartHydroGrid Scheduling Optimization

"""

#simulate
class SHGSO():
    def __init__(self, inst):
        self.inst = inst

    def solve(self, gap=None, time_limit=False, verbose=False, lp_file_name=None, NodefileStart = False):
        
        self.problem_name="SHGSO"
        
        # **************************************************** PARAMETRI *******************************************************************

        # Define iterators
        self.hours = range(self.inst.T_steps+1) #288 + 1 per arrivare a 289
        self.steps_per_hour = (60 + self.inst.minutes - 1) // self.inst.minutes # 12
        
        # Durata warm espressa in step (ceil: garantisce almeno 5')
        self.L_warm = max(1, math.ceil(self.inst.t_warm_up / self.inst.minutes))
        
        self.i_approximation = range(self.inst.i_approximation)

        # Check max for power line
        self.P_max = self.inst.P_max
        #print(f"Problem: {self.problem_name},\nInstance : {self.inst.inst_name}")
        #logging.info("{}".format(self.problem_name))
        
        # ============================================== ELETTROLIZZATORE - APPROSSIMAZIONE LINEARE A TRATTI =====================================================

        # --- PREPARAZIONE CURVA ELETTROLIZZATORE (Gurobi Native) ---
        # Costruiamo i vettori dei punti della curva caratteristica
        el_pts_in_X  = [0.0]  # Potenza Elettrica (Input)
        el_pts_out_Y = [0.0]  # Potenza Idrogeno (Output)

        # Usiamo 'i_approximation' per prendere TUTTI i punti (non i segmenti)
        for i in self.i_approximation:
            # 1. Output Idrogeno (Y)
            # P_h2 = % carico * P_nominale_H2
            val_out_Y = self.inst.z_el[i] * self.inst.P_el_max_eq_h2
            
            # 2. Input Elettrico (X)
            # P_ele = P_h2 / rendimento
            # (Gestione divisione per zero se il primo punto è 0 e theta è 0)
            if self.inst.theta_el[i] > 0:
                val_in_X = val_out_Y / self.inst.theta_el[i]
            else:
                val_in_X = 0.0

            el_pts_in_X.append(val_in_X)
            el_pts_out_Y.append(val_out_Y)
        
        self.max_charge = self.inst.P_el_max * self.inst.delta_t
        # ============================================== CREAZIONE MODELLO Gurobi =====================================================
        
        self.model = gp.Model(self.problem_name)

        # ==== PARAMETRI DI SILENZIO Gurobi ====
        self.model.setParam('OutputFlag', 0)
        self.model.setParam('LogToConsole', 0)
        self.model.setParam('LogFile', "")

# **************************************************** VARIABILI *******************************************************************
        
        # P imported
        self.P_imp = self.model.addVars(self.hours,lb=0,ub= self.P_max,vtype= GRB.CONTINUOUS,name='P_imp')
        self.delta_P_imp = self.model.addVars(self.hours, lb= 0, ub= 1, vtype= GRB.BINARY, name='Delta_P_imp')
        
        # P exported
        self.P_exp = self.model.addVars(self.hours,lb=0,ub= self.P_max,vtype= GRB.CONTINUOUS,name='P_exp')
        self.delta_P_exp = self.model.addVars(self.hours, lb= 0, ub= 1, vtype= GRB.BINARY, name='Delta_P_exp')
        
        # P elecrolizer in
        self.P_el_in = self.model.addVars(self.hours,lb=0,ub= self.inst.P_el_max,vtype= GRB.CONTINUOUS,name='P_el_in')

        # P elecrolizer out
        self.P_el_out = self.model.addVars(self.hours,lb=0, ub= self.inst.P_el_max_eq_h2, vtype= GRB.CONTINUOUS, name='P_el_out')

        # H2 discharged for Blending
        self.H2_blend = self.model.addVars(self.hours, lb= 0, ub= GRB.INFINITY, vtype= GRB.CONTINUOUS,name='H2_blend')

        # ---- Stati elettrolizzatore (mutuamente esclusivi) ----
        self.y_off  = self.model.addVars(self.hours, vtype=GRB.BINARY, name="y_off")
        self.y_warm = self.model.addVars(self.hours, vtype=GRB.BINARY, name="y_warm")
        self.s_warm = self.model.addVars(self.hours, vtype=GRB.BINARY, name="s_warm")
        self.y_run  = self.model.addVars(self.hours, vtype=GRB.BINARY, name="y_run")   # PWA attiva
        self.y_prod = self.model.addVars(self.hours, vtype=GRB.BINARY, name="y_prod")  # = y_warm + y_run. E' il delta dell'elettrolizzatore
        
        # OBJECTIVE FUNCTION
        obj_funct = 0
        
        # Sfruttiamo il metodo .sum() delle tupledict di Gurobi che è velocissimo in C
        # Costo Opex Elettrolizzatori (somma su tutti i k e tutti i t)
        opex_ely_tot = self.inst.opex_ely * self.P_el_in.sum()
        
        # Per Import/Export che hanno prezzi variabili nel tempo [t], dobbiamo usare generator expression
        # ma possiamo farlo in un'unica riga ottimizzata senza loop esterni
        dt = self.inst.delta_t
        cost_imp_tot = gp.quicksum(self.inst.c_buy[t] * self.P_imp[t] for t in self.hours) * dt
        r_exp_tot = gp.quicksum(self.inst.c_sell[t] * self.P_exp[t] for t in self.hours) * dt
        
        #Penalità per la BU
        penalty_factor = 50
        diff_bu = gp.quicksum((self.H2_blend [t] - self.inst.h2_blend [t]) * self.inst.HHV * penalty_factor for t in self.hours)

        obj_funct = opex_ely_tot + cost_imp_tot  + diff_bu - r_exp_tot
        
        self.model.setObjective(obj_funct, GRB.MINIMIZE)

# **************************************************** CONSTRAINTS *******************************************************************

# =============================================== POWER BALANCE CONSTRAINTS ===========================================================
        
        # Bilancio AC:
        self.model.addConstrs((
            self.P_el_in [t] + (self.inst.P_aux) * self.y_prod[t] + self.inst.P_standby + self.P_exp[t]
            == self.P_imp[t] + self.inst.P_pv [t]
            for t in self.hours),
            name="power_balance_ac"
        )
        
        # Bilancio Idreogeno:
        self.model.addConstrs((
            self.P_el_out [t] * dt == self.H2_blend [t]* self.inst.HHV * dt
            for t in self.hours),
            name="power_balance_hydrogen"
        )

# ======================================= APPLICAZIONE DELLA PWA CON GUROBI PER ELE E FC ====================================================================

        for t in self.hours:
# ======================================== ELETTROLIZZATORE (PWA solo in RUN) ==================================================
            # (A) Nessuna produzione H2 fuori RUN
            self.model.addConstr(self.P_el_out[t] <= self.inst.P_el_max_eq_h2 * self.y_run[t],
                                f"el_out_only_run_ub_{t}")

            # (B) PWL per elettrolizzatore con step discreti

            # Nota: Assicurati che 'el_pts_in_X' e 'el_pts_out_Y' siano definiti (come nel codice originale)
            self.model.addGenConstrPWL(
                self.P_el_in[t],    # X: Input Elettrico
                self.P_el_out[t],   # Y: Output H2 (che ora è discreto)
                el_pts_in_X,           # Punti X della curva
                el_pts_out_Y,          # Punti Y della curva
                name=f"pwl_el_{t}"
            )
            
            # Vincoli di sicurezza per spegnere l'input se y_run=0 (ridondante ma utile)
            self.model.addConstr(self.P_el_in[t] <= self.inst.P_el_max * self.y_run[t], f"safety_off_in_{t}")
                
# =================================== DINAMICA DELL' ELETTROLIZZATORE =============================================

        for t in self.hours:
    
            #Stati di funzionamento dell'elettrolizzatore (esattamente uno stato per volta)
            self.model.addConstr(self.y_off[t] + self.y_warm[t] + self.y_run[t] == 1, f"one_state_{t}")

            # produzione = warm + run
            self.model.addConstr(self.y_prod[t] == self.y_warm[t] + self.y_run[t], f"yprod_{t}")

            self.model.addConstr(self.y_warm[t] <= self.y_prod[t], f"warm_ub1_{t}")
            
            if t == 0:
                self.model.addConstr(self.s_warm[t] >= self.y_warm[t], f"s_warm_lb_{t}")
                self.model.addConstr(self.s_warm[t] <= self.y_warm[t], f"s_warm_ub1_{t}")
            else:
                self.model.addConstr(self.s_warm[t] >= self.y_warm[t] - self.y_warm[t-1], f"s_warm_lb_{t}")
                self.model.addConstr(self.s_warm[t] <= self.y_warm[t], f"s_warm_ub1_{t}")
                self.model.addConstr(self.s_warm[t] <= 1 - self.y_warm[t-1], f"s_warm_ub2_{t}")
                self.model.addConstr(self.s_warm[t] <= self.y_off[t-1], f"s_warm_requires_off_{t}")

            # =========================================================
            # VINCOLO FISICO: DIVIETO SALTO OFF -> RUN
            # =========================================================
            if t > 0:
                # Se allo step precedente ero OFF (y_off=1),
                # allo step attuale NON posso essere in RUN (y_run deve essere 0).
                # Posso andare in WARM o restare OFF.
                
                # Matematica: y_run[t] + y_off[t-1] <= 1
                # Se y_off[t-1] è 1, allora y_run[t] è costretto a 0.
                # Se y_off[t-1] è 0 (ero Stby/Warm/Run), allora y_run[t] può essere 1.
                
                self.model.addConstr(
                    self.y_run[t] + self.y_off[t-1] <= 1,
                    f"block_direct_off_to_run_{t}"
                )

        L = self.L_warm

        for t in self.hours:

            #Il warming deve durare esattamente L step
            rhs = gp.quicksum(self.s_warm[t-j] for j in range(L) if t-j >= 0)

            self.model.addConstr(self.y_warm[t] <= rhs, f"warm_win_ub_{t}")
            self.model.addConstr(rhs <= L * self.y_warm[t], f"warm_win_lb_{t}")

            # Dopo il warm, devi entrare in RUN immediatamente
            if t >= self.L_warm:
                self.model.addConstr(self.y_run[t] >= self.s_warm[t - self.L_warm],
                                    f"run_immediately_after_warm_{t}")
                # Vieta OFF/STBY nello stesso step:
                self.model.addConstr(self.y_off[t]  <= 1 - self.s_warm[t - self.L_warm], f"no_off_after_warm_{t}")

            if t > 0 and t < L:
                self.model.addConstr(
                    self.y_run[t] <= self.y_run[t-1],
                    f"no_run_rise_before_warm_{t}"
                )
            else:
                if t >= L:
                    # puoi aumentare RUN al tempo t solo se c'è s_warm al tempo t-L
                    # y_run[t] <= y_run[t-1] + s_warm[t-L]
                    self.model.addConstr(
                        self.y_run[t] <= self.y_run[t-1] + self.s_warm[t-L],
                        f"run_rise_from_run_or_or_warm_{t}"
                    )

#============================================= VINCOLO IDROGENO PER BLENDING UNIT ========================================================================
        for t in self.hours:
            self.model.addConstr(
                self.H2_blend[t] >= self.inst.h2_blend[t],
                f"blend_limit_{t}"
            )
            
#============================================= VINCOLO SCAMBIO CON LA RETE ========================================================================
        for t in self.hours:
            self.model.addGenConstrIndicator(
                self.delta_P_exp[t],   # Variabile Binaria
                0,                     # Valore della binaria (0 = False)
                self.P_exp[t] == 0,    # Vincolo implicato
                name=f"Ind_Exp_{t}"
            )
            
            self.model.addGenConstrIndicator(
                self.delta_P_imp[t],   # Variabile Binaria
                0,                     # Valore della binaria (0 = False)
                self.P_imp[t] == 0,    # Vincolo implicato
                name=f"Ind_Imp_{t}"
            )
            
            self.model.addConstr(
                self.delta_P_exp[t] + self.delta_P_imp[t] <= 1,
                    f"Delta_EXP_IMP_{t}"
                    )

        self.model.update()
        
        return self._run_optimization(gap, time_limit, verbose, lp_file_name, NodefileStart)

#============================================= ESECUZIONE DELL' ALGORITMO MILP ========================================================================

    def _run_optimization(self, gap, time_limit, verbose, lp_file_name, NodefileStart):
        # For lazy constraints (with callback)
        self.model.Params.lazyConstraints = 0
        self.model.update()
        # Parametri per velocizzare il codice
        # Sposterà le risorse dal calcolo del BestBd (che ti interessa poco) alla ricerca di euristiche.
        # Probabilmente troverà quel valore "247" molto prima, magari al secondo 60 invece che al 280.
        #self.model.setParam('MIPFocus', 1)
        # Nel tuo log, tutte le soluzioni buone sono arrivate dalle righe con la "H".
        # Significa che l'albero di ricerca standard sta faticando, mentre gli algoritmi di
        # "intuizione" (euristiche) funzionano bene. Aumentiamoli.
        # Default è 0.05. Portiamolo a 0.2 o 0.3 (20-30% del tempo speso in euristiche)
        self.model.setParam('Heuristics', 0.5)
        #self.model.setParam('PumpPasses', 10)
        #self.model.setParam('RINS', 10)         # Attiva euristica RINS ogni 10 nodi (molto potente)
        # Il log mostra molti "Cutting planes" alla fine. A volte generare questi tagli richiede tempo che
        # potresti non avere. Se i primi due non bastano, prova a ridurre l'aggressività dei tagli:
        # Riduce la generazione di tagli per risparmiare tempo iterativo
        #self.model.setParam('Cuts', 0)
        # Presolve aggressivo (aiuta a eliminare variabili inutili)
        #self.model.setParam('Threads', 6)
        #self.model.setParam('VarBranch', 1)
        #self.model.setParam('IntFeasTol', 1e-4)
        if gap:
            self.model.setParam('MIPgap', gap)
        if time_limit:
            self.model.setParam(GRB.Param.TimeLimit, time_limit)
            hard_optimality = False
        else:
            hard_optimality = True
        if verbose:
            self.model.setParam('OutputFlag', 1)
        else:
            self.model.setParam('OutputFlag', 0)
        self.model.setParam('LogFile', './logs/gurobi.log')
        if lp_file_name:
            self.model.write(f"./logs/model_{lp_file_name}.lp")
        
        if NodefileStart:
            self.model.setParam('NodefileStart', 2)
        start = time.time()
        # print(f"--- STATISTICHE MODELLO ---")
        # print(f"Numero Variabili: {self.model.NumVars}")
        # print(f"Numero Vincoli Lineari: {self.model.NumConstrs}")
        # print(f"Numero Vincoli Quadratici: {self.model.NumQConstrs}") # Se ne hai
        # print(f"-------------------------")
        
        # Salva il modello matematico su file
        #self.model.write("scheduling_fc.mps")
        # exit()
        self.model.write("modello_completo.lp")
        self.model.optimize()
        
        if self.model.status == 3: # INFEASIBLE
            print("❌ ERRORE: Il modello è INFEASIBLE (Impossibile da risolvere).")
            print("Possibile causa: troppi punti di interpolazione troppo vicini.")
            self.model.computeIIS()
            self.model.write("model_debug.ilp")
            return -1, None, 0
        end = time.time()
        self.comp_time = end - start
        
        return self._get_solution(hard_optimality = hard_optimality)
    
#============================================= ESTRAZIONE DELLE SOLUZIONI ========================================================================

    def _get_solution(self, hard_optimality=True):

        # 1. Controllo Infeasibility
        if self.model.status == GRB.Status.INFEASIBLE:
            messaggio_utente = self._diagnose_infeasibility()
            raise ValueError({"status": "Errore", "messaggio": messaggio_utente})

        T = self.inst.T_steps + 1

        # 2. Inizializzazione Struttura Dati
        self.sol = {
            # --- Totali ---
            "P_imp":        np.zeros(T),
            "P_exp":        np.zeros(T),
            "P_el_in":      np.zeros(T),  # Elettrolizzzatore
            "P_el_in_tot":  np.zeros(T),  # Elettrolizzzatore + AUX
            "P_el_out":     np.zeros(T),  # H2 out (somma k)
            "y_off":          np.zeros(T),
            "y_warm":         np.zeros(T),
            "y_run":          np.zeros(T),
            "delta_el":       np.zeros(T),
            "s_warm":         np.zeros(T),
            "H2_blend":       np.zeros(T),
        }

        # 3. Estrazione Valori (Solo se c'è una soluzione disponibile)
        # Nota: status 2 = OPTIMAL, status 9 = TIME_LIMIT con soluzione
        has_solution = (self.model.solCount > 0)

        if has_solution:
            for t in self.hours:
                
                # --- A. Variabili Continue ---
                try: self.sol["P_imp"][t]    = self.P_imp[t].X
                except: pass
                
                try: self.sol["P_exp"][t]    = self.P_exp[t].X
                except: pass
                
                try: self.sol["P_el_in"][t]  = self.P_el_in[t].X + self.inst.P_standby
                except: pass
                
                try: self.sol["P_el_in_tot"][t]  = self.P_el_in[t].X + self.inst.P_aux * self.y_prod[t].X + self.inst.P_standby
                except: pass
                
                try: self.sol["P_el_out"][t] = self.P_el_out[t].X
                except: pass
                
                try:self.sol["H2_blend"][t] = self.H2_blend[t].X
                except: pass
                
                # --- B. Variabili Binare (Stati) ---
                try: self.sol["y_off"][t]    = self.y_off[t].X
                except: pass
                try: self.sol["y_warm"][t]   = self.y_warm[t].X
                except: pass
                try: self.sol["y_run"][t]    = self.y_run[t].X
                except: pass
                try: self.sol["s_warm"][t]   = self.s_warm[t].X
                except: pass
                

        # 4. Return Finale
        # Se volevamo hard_optimality e non è ottimale, ritorna errore
        if hard_optimality and self.model.status != GRB.Status.OPTIMAL:
            return -1, self.sol, self.comp_time
        
        # Altrimenti ritorna i risultati (anche se sub-ottimali o time limit)
        try:
            obj_val = self.model.getObjective().getValue()
        except:
            obj_val = -1

        return obj_val, self.sol, self.comp_time

#============================================= DIAGNOSI DEI MOTIVI PERR CUI E' INFEASIBLE ========================================================================

    def _diagnose_infeasibility(self):
            """
            Esegue una serie di test RAPIDI per diagnosticare la causa di un modello infattibile.
            Ogni test ha un tempo limite per evitare che il programma sembri bloccato.
            Restituisce un messaggio di errore specifico per l'utente finale.
            """
            #print("Il modello è infattibile. Avvio della diagnosi automatica...")
            
            # Imposta un tempo limite in secondi per ciascun test di diagnosi.
            # Questo valore deve essere abbastanza lungo da permettere a Gurobi di trovare una 
            # soluzione facile, ma abbastanza corto da non far attendere l'utente.

            # Se nessun test specifico ha avuto successo, restituisci un messaggio generico ma utile.
            #print("  - Nessun problema singolo individuato. Potrebbe essere una combinazione di fattori.")
            return (
                """Il modello è infattibile a causa di una combinazione complessa di vincoli."""
            )