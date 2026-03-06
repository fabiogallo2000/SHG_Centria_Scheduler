# -*- coding: utf-8 -*-
import numpy as np

class Instance_SHG():
    def __init__(self, param_dict):
        
        self.grafici_finali = param_dict.get("User inputs", {}).get("grafici finali", False)
        
# ==================================== PUNTI PER INTERPOLAZIONE =====================================================
        self.z_el = [0, 1.00]
        self.theta_el = [0,  0.72261]

# =========================================== COMPONENT DYNAMICS =====================================================
        # Electrolizer/fuelcell params
        self.P_el_min = 0
        self.P_el_max = 50.4
        self.P_el_max_eq_h2 = self.P_el_max * self.theta_el [-1]
        
        self.HHV = 3.36 #kWh/sM3
        
        # Linear approximation params
        self.i_approximation = len(self.z_el)

        # Ausiliari
        self.P_standby = 0.7 #660W la pompa + altri ausiliari interni all'ele
        self.P_aux = 0.3 # Altri ausiliari esterni all'ele

# =========================================== STATIC DATA =====================================================
        self.inst_name = param_dict.get("input", "Centria P2G")
        self.gap = 0.01
        self.time_limit = 300
        self.H2_prod_ini_perc = param_dict.get("Static Data", {}).get("H2_prod_ini_perc", 0)
        self.T_amb = param_dict.get("Static Data", {}).get("T_amb_C", 25)
        self.Cert_Go = param_dict.get("Static Data", {}).get("Cert_Go", 0.075)
        self.Spread = param_dict.get("Static Data", {}).get("Spread", 0.08)

# ==================================== ORIZZONTE E RISOLUZIONE TEMPORALE =====================================================
        self.minutes = 5
        self.delta_t = self.minutes / 60.0 # Conversione di 5 minuti in ore, per la moltiplicazione da kW a kWh
        self.T_test = 24
        self.T_steps = int(self.T_test * 60 // self.minutes)  # 288
        if self.T_steps != 288:
            raise ValueError({"status":"Errore", "messaggio":
                                "Orizzonte non coerente con 'minutes' (attesi 288 step)."})

# =========================================== USER INPUTS =====================================================
        self.opex_ely = param_dict.get("User inputs", {}).get("Opex_ely_eur_per_kWh", 0)
        
        # Altri parametri
        self.P_max             = param_dict.get("User inputs", {}).get("P_max_allaccio_kW", 1000)
        self.t_warm_up         = 5  # min
        
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
        self.c_buy = self.c_buy + (self.Cert_Go + self.Spread)
        
        self.c_sell  = _to_vec("c_sell_eur_per_kWh",  self.T_steps+1)
        
        self.P_pv = _to_vec("P_pv_kW", self.T_steps+1)
        
        self.h2_blend = _to_vec("h2_blend_smc", self.T_steps+1)
        #print(self.h2_blend)

        # print("c_buy  " + str(self.c_buy))
        # print ("h2_blend " + str(self.h2_blend))
        # exit()