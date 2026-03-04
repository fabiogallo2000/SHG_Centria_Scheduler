# Usa un'immagine base di Python
FROM python:3.10-slim

# Imposta la directory di lavoro nel contenitore
WORKDIR /app

# Copia i file del progetto nella directory di lavoro
COPY . .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Espone la porta su cui gira Flask
EXPOSE 5000

# Comando per avviare l'applicazione
CMD ["python", "app.py"]