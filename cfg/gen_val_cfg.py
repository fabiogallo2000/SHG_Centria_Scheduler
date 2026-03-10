import json
import numpy as np
from pathlib import Path
import pandas as pd

base_dir = Path(__file__).parent.resolve()
actual_dir = base_dir / 'input.json'

with open (actual_dir, 'r') as js:
    f= json.load(js)
    
h2_blend = f ["Forecast Data"]['h2_blend_smc']
# p_pv = f ["Forecast Data"]['P_pv_kW']
# c_sell = f ["Forecast Data"]['c_sell_eur_per_kWh']
# c_buy = f ["Forecast Data"]['c_buy_eur_per_kWh']

# 2. Definisci l'asse temporale originale (289 punti distribuiti su 86400 secondi)
# Se i 289 punti coprono esattamente le 24 ore:
x_original = np.linspace(0, 86400, len(h2_blend))

# 3. Definisci il nuovo asse temporale (1440 punti, uno per ogni secondo)
x_new = np.arange(0, 1441)

# 4. Interpolazione
h2_blend_interp = np.interp(x_new, x_original, h2_blend)
# p_pv_interp = np.interp(x_new, x_original, p_pv)
# c_sell_interp = np.interp(x_new, x_original, c_sell)
# c_buy_interp = np.interp(x_new, x_original, c_buy)

f ["Forecast Data"]['h2_blend_smc'] = h2_blend_interp.tolist()
# f ["Forecast Data"]['P_pv_kW'] = p_pv_interp.tolist()
# f ["Forecast Data"]['c_sell_eur_per_kWh'] = c_buy_interp.tolist()
# f ["Forecast Data"]['c_buy_eur_per_kWh'] = c_buy_interp.tolist()

with open(actual_dir, 'w') as js:
    json.dump(f, js, indent=4)

