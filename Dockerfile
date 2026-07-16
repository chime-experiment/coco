# Use an official Python runtime as a base image
FROM python:3.10-slim

## The maintainer name and email
LABEL maintainer="CHIME/FRB Collaboration"

ADD . /coco

RUN apt-get update && \
    apt-get install -y apt-utils git build-essential curl \
    libmariadb-dev libevent-dev && \
    pip install --use-deprecated=legacy-resolver flask && \
    pip install --use-deprecated=legacy-resolver /coco[cocod]

#-----------------------
# Minimize container size
#-----------------------
RUN apt-get remove -y git && \
    apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /tmp/build /coco
