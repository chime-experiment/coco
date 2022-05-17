# Use an official Python runtime as a base image
FROM python:3.7-slim

## The maintainer name and email
LABEL maintainer="CHIME/FRB Collaboration"

RUN apt-get update && \
    apt-get install -y apt-utils && \
    apt-get install -y software-properties-common && \
    apt-get install -y git && \
    apt-get install -y build-essential && \
    apt-get install -y libmariadb-dev && \
    apt-get install -y python3-sphinx && \
    apt-get install -y libevent-dev && \
    apt-get install -y libhdf5-dev && \
    apt-get install -y g++ && \
    pip install flask && \
    pip install coverage && \
    pip install pytest-cov && \
    pip install sphinx_rtd_theme && \
    git clone --branch aioredis_v2 https://github.com/chime-experiment/coco.git && \
    pip install -r /coco/requirements.txt && \
    pip install /coco 
