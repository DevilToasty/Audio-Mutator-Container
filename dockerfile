FROM python:3.12-slim

# libsndfile1 is the audio-playback codec that Pedalboard uses at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \ 
	libsndfile1 && rm -rf /var/lib/apt/lists/*

# libtomic for audio rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# move working directory with Docker command
WORKDIR /app 

# copy requirements from requrements.txt and install them as dependency layers
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt 

# then copy application code
COPY app/ ./app/

# create the port for the web application viewer
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
