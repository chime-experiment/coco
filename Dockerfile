# Use an official Python runtime as a base image
FROM python:3.7-slim

## The maintainer name and email
LABEL maintainer="CHIME/FRB Collaboration"

ADD . /coco

RUN apt-get update && \
    apt-get install -y apt-utils && \
    apt-get install -y software-properties-common && \
    apt-get install -y git && \
    apt-get install -y build-essential && \
    apt-get install -y libmariadb-dev && \
    apt-get install -y libevent-dev && \
    apt-get install -y libhdf5-dev && \
    pip install flask && \
    pip install -r /coco/requirements.txt && \
    pip install /coco && \

    #-----------------------
    # Minimize container size
    #-----------------------
    apt-get remove -y curl git && \
    apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /tmp/build
