# -*- coding: utf-8 -*-
import numpy as np

class Instance_SHG():
    def __init__(self, param_dict):
        
        self.grafici_finali = param_dict.get("User inputs", {}).get("grafici finali", False)
        
# ==================================== PUNTI PER INTERPOLAZIONE =====================================================
        self.z_el = [0, 1.00]
        self.theta_el = [0,  0.777]

# =========================================== COMPONENT DYNAMICS =====================================================
        # Electrolizer/fuelcell params
        self.P_el_min = 0
        self.P_el_max = 50.4
        self.P_el_max_eq_h2 = self.P_el_max * self.theta_el [-1]
        
        # Hydrogen storage params
        self.cap_h2_max = 58.613 #kWh
        self.loh_final = param_dict.get("User inputs", {}).get("LOH_final", 0.5)

        self.p_ini_st_h2 = param_dict.get("Static Data", {}).get("p_ini_st_h2", None)
        if self.p_ini_st_h2 is None:
            raise ValueError({"status":"Errore", "messaggio":
                                "p_ini_st_h2 mancante nell'input PLC"})
        self.HHV = 3.36 #kWh/sM3
        
        self.p_max_st_h2 = 30
        self.p_min_st_h2 = 0.5
        self.loh_min = self.p_min_st_h2 / self.p_max_st_h2
        self.loh_max = 1
        
        # Linear approximation params
        self.i_approximation = len(self.z_el)

        # Ausiliari
        self.P_standby = 0.7 #660W la pompa + altri ausiliari interni all'ele
        self.P_aux = 0.5 # Altri ausiliari esterni all'ele

# ==================================== ORIZZONTE E RISOLUZIONE TEMPORALE =====================================================
        self.minutes = 15
        self.delta_t = self.minutes / 60.0 # Conversione di 15 minuti in ore, per la moltiplicazione da kW a kWh
        self.T_test = 24
        self.T_steps = int(self.T_test * 60 // self.minutes)  # 1440
        if self.T_steps != 96:
            raise ValueError({"status":"Errore", "messaggio":
                                "Orizzonte non coerente con 'minutes' (attesi 96 steps)."})

# =========================================== USER INPUTS =====================================================
        self.opex_ely = param_dict.get("User inputs", {}).get("Opex_ely_eur_per_kWh", 0)
        self.control           = param_dict.get("User inputs", {}).get("control_loh_fin", False)
        # Altri parametri
        self.P_max             = param_dict.get("User inputs", {}).get("P_max_allaccio_kW", 1000)
        self.t_warm_up         = 5  # min
        self.h2_perc = param_dict.get("User inputs", {}).get("h2_percentage", 20) / 100.0
        
        self.Cert_Go = param_dict.get("User inputs", {}).get("Cert_Go", 0.075)
        self.Spread = param_dict.get("User inputs", {}).get("Spread", 0.08)
        
# =========================================== FORECAST DATA =====================================================
        def _to_vec(key, required_len):
            v = param_dict.get("Forecast Data", {}).get(key, None)
            if v is None or len(v) == 0:
                raise ValueError({"status":"Errore", "messaggio":
                                    f"Profilo '{key}' mancante o vuoto nell'input PLC"})
            arr = np.asarray(v, dtype=float)
            if arr.size != required_len:
                raise ValueError({"status":"Errore", "messaggio":
                                    f"Profilo '{key}' ha lunghezza {arr.size}, attesa {required_len}"})
            return arr

        self.c_buy  = _to_vec("c_buy_eur_per_kWh",  self.T_steps+1)

        self.c_sell  = _to_vec("c_sell_eur_per_kWh",  self.T_steps+1)
        
        self.gas_blend = _to_vec("gas_blend_smc", self.T_steps+1)
        self.h2_blend = self.gas_blend * self.h2_perc
        
        self.p_pv = _to_vec("P_pv_kW", self.T_steps+1)

# =========================================== STATIC DATA =====================================================
        self.inst_name = param_dict.get("input", "Centria P2G")
        self.gap = 0.01
        self.time_limit = 300
        self.H2_prod_ini_perc = self.h2_blend [0]
