import json
import numpy as np

with open("cfg/input.json", "r") as fp:
    mod = json.load(fp)

# Convert lists to numpy arrays
carico_gas = np.array(mod["Forecast Data"]["gas_blend_smc"]) * 100/20
pv = np.array(mod["Forecast Data"]["P_pv_kW"])
c_buy = np.array(mod["Forecast Data"]["c_buy_eur_per_kWh"])
c_sell = np.array(mod["Forecast Data"]["c_sell_eur_per_kWh"])

# Use slicing [start:stop:step] and limit to the first 96 points
mod["Forecast Data"]["gas_blend_smc"] = carico_gas[::15][:96].tolist()
mod["Forecast Data"]["P_pv_kW"] = pv[::15][:96].tolist()
mod["Forecast Data"]["c_buy_eur_per_kWh"] = c_buy[::15][:96].tolist()
mod["Forecast Data"]["c_sell_eur_per_kWh"] = c_sell[::15][:96].tolist()

# If you want to save the modified JSON back to the file:
with open("cfg/input.json", "w") as fp:
    json.dump(mod, fp, indent=4)
