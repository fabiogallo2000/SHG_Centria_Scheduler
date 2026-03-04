import numpy as np
import json
import sys
from pathlib import Path

l= [ 1.17, 1.17, 0.79, 0.91, 0.65, 1.04, 1.22, 1.04, 0.91, 0.91, 0.91, 1.04, 1.22, 1.17, 1.17, 1.04, 0.65, 0.52, 0.26, 0.26, 0.26, 0.39, 0.26, 0.65]
vec = np.array(l)
vec_interp = np.interp(np.arange(0, 289, 1), np.arange(0, 24, 1), vec)


if getattr(sys, 'frozen', False):
# Caso ESEGUIBILE (.exe)
    base_dir = Path(sys.executable).parent
else:
# Caso SCRIPT (.py)
# __file__ è il percorso dello script corrente
    base_dir = Path(__file__).parent.resolve()
        
output_dir = base_dir / "risultati"
output_dir.mkdir(parents=True, exist_ok=True)
output_filename = output_dir / "output_simulazione.json"
with open(output_filename, 'w') as f:
    json.dump({"vec_interp": vec_interp.tolist()}, f, indent=2)

print (vec_interp)
print(len(vec_interp))