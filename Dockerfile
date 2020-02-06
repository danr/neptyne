FROM python:3.8.1
RUN apt-get -y update && apt-get -y install python3-ipykernel
COPY . /tmp/neptyne
RUN pip install /tmp/neptyne
WORKDIR /workdir
CMD neptyne
