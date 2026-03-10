from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union
import numpy as np
import uvicorn
from datetime import datetime
import time
import warnings

# Import dei tuoi moduli
from simulator.Instance_SHG import Instance_SHG
from solver.shgso import SHGSO

warnings.filterwarnings("ignore")

app = FastAPI(
    title="Digital Twin Simulation API",
    description="API per ottimizzazione e simulazione Digital Twin",
    version="1.1.0"
)

# --- 1. Definizione Modello Dati (Pydantic) ---
class SimulationInput(BaseModel):
    # Usiamo alias per mappare esattamente i nomi del tuo JSON di input
    datetime_str: Optional[str] = Field(None, alias="datetime")
    forecast_data: Dict[str, List[float]] = Field(..., alias="Forecast Data")
    user_inputs: Dict[str, Any] = Field(..., alias="User inputs")
    static_data: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="Static Data")
    instance_name: Optional[str] = Field(default="Techfem", alias="Instance_name")

    class Config:
        populate_by_name = True

# --- 2. Logica Core ---
def run_model_logic(input_data: Dict[str, Any]):
    start_time = time.time()

    # Parsing data
    start_datetime_str = input_data.get("datetime")
    if start_datetime_str:
        try:
            start_dt_obj = datetime.fromisoformat(start_datetime_str)
        except ValueError:
            start_dt_obj = datetime.now().replace(microsecond=0)
    else:
        start_dt_obj = datetime.now().replace(microsecond=0)
            
    # Inizializzazione Istanza
    inst_shg = Instance_SHG(input_data)
    problem = SHGSO(inst_shg)


    # 1. Esecuzione del solutore
    obj_funct, sol, comp_time_solver = problem.solve(
        gap=inst_shg.gap,
        time_limit=inst_shg.time_limit, 
        verbose=False # Solitamente False in produzione/API
    )

    # 3. Estrazione Dati (Solo se successo)
    T_steps = problem.inst.T_steps + 1
    p_imp_values    = np.ravel(sol['P_imp'])[:T_steps]
    p_exp_values    = np.ravel(sol['P_exp'])[:T_steps]
    p_el_out_values = np.ravel(sol['P_el_out'])[:T_steps]
    y_warm_up       = np.ravel(sol['y_warm'])[:T_steps]
    y_run           = np.ravel(sol['y_run'])[:T_steps]
    s_warm          = np.ravel(sol['s_warm'])[:T_steps]
    
    # Calcolo percentuale di carico
    h2_out_perc = (p_el_out_values / inst_shg.P_el_max_eq_h2) * 100
    
    # Calcolo Stato_Ely (ON se Warm, Run o S_warm)
    y_on_off_t = np.logical_or.reduce([
        y_warm_up.astype(bool), 
        y_run.astype(bool), 
        s_warm.astype(bool)
    ]).astype(int)
    
    elapsed_time = time.time() - start_time
    
    return {
        "status": "ok",
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "computation_time": float(elapsed_time),
        "sampling_time": int(inst_shg.minutes),
        "Funzione Obiettivo": float(obj_funct),
        "Elettrolizzatore": {
            "Stato_Ely": y_on_off_t.tolist(),
            "h2_out_perc": h2_out_perc.tolist(),
        },
        "P_imp_grid": p_imp_values.tolist(),
        "P_exp_grid": p_exp_values.tolist()
    }

# --- 3. Endpoint FastAPI ---

@app.post("/run_simulation")
async def run_simulation(input_model: SimulationInput):
    # Convertiamo il modello Pydantic in dizionario per la logica esistente
    input_dict = input_model.model_dump(by_alias=True)
    try:
        # Eseguiamo la logica
        result = run_model_logic(input_dict)
        return result
    except ValueError as e:
        # Recuperiamo il contenuto dell'errore
        error_content = e.args[0] if e.args else "Errore sconosciuto"
        
        # Se shgso ha passato un dizionario (es. diagnosi di infattibilità)
        if isinstance(error_content, dict):
            # Restituiamo un 422 (Unprocessable Entity) o 400 (Bad Request) con il JSON pulito
            return JSONResponse(status_code=422,content=error_content)
        
        # Se è un altro tipo di ValueError (stringa semplice)
        return JSONResponse(
            status_code=400,
            content={"status": "Error", "message": str(e)}
        )
        
    except Exception as e:
        # Cattura errori imprevisti (bug del codice, problemi di memoria, ecc.)
        return JSONResponse(
            status_code=500,
            content={"status": "Critical Error", "message": str(e)}
        )

if __name__ == '__main__':
    # Lancio dell'app su porta 5000
    uvicorn.run(app, host="0.0.0.0", port=5000)