# Use an official Python runtime as a base image
FROM python:3.8-slim

## The maintainer name and email
LABEL maintainer="CHIME/FRB Collaboration"

ADD . /coco

RUN apt-get update && \
    apt-get install -y apt-utils software-properties-common git build-essential \
    libmariadb-dev libevent-dev && \
    pip install flask && \
    pip install -r /coco/requirements.txt && \
    pip install /coco

#-----------------------
# Minimize container size
#-----------------------
RUN apt-get remove -y curl git && \
    apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /tmp/build
