FROM alpine:latest
RUN apk update && \
    apk add --no-cache libstdc++ g++ make cmake libpng-dev tiff-dev libxml2-dev openssl-dev git && \
    git clone https://github.com/DCMTK/dcmtk.git
RUN mkdir dcmtk-build && \
    cd dcmtk-build && \
    cmake ../dcmtk && \
    make -j8 && \
    make install
RUN apk add --no-cache python3 py-pip
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt && rm requirements.txt
RUN rm -rf /dcmtk /dcmtk-build
RUN mkdir /in /out /reports
COPY . /app
RUN chmod a+x /app/receiver.sh
VOLUME ["/app/config", "/in", "/out", "/reports"]
ENV AETITLE="ANONYMIZER"
ENV RECEIVER_AET="STORESCP"
ENV RECEIVER_IP="dcmsorter 104"
CMD /usr/bin/python3 /app/anonymize.py /data