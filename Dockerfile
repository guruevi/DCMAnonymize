FROM ubuntu:latest
RUN apt update
RUN apt install -y python3 python3-pip dcmtk
COPY . /app
RUN pip install -r /app/requirements.txt
VOLUME ["/app/config"]
CMD /usr/bin/python3 /app/anonymize.py