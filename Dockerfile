# For more information, please refer to https://aka.ms/vscode-docker-python
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-devel
LABEL authors="ismailalpaydemir"

EXPOSE 8051

# ---- Python Related ENV Variables ---- #
# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

ENV CUDA_HOME=/usr/local/cuda

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install -r requirements.txt




WORKDIR /app
COPY . /app


## Creates a non-root user with an explicit UID and adds permission to access the /app folder
## For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
#RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
#USER appuser

# Run uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8051"]
#CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8051"]


