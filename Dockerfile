FROM python:3.7

# Tesseract
RUN apt-get update \
    && apt-get install tesseract-ocr -y \
    python3-pip \
    wget \
    && pip3 install --no-cache-dir pipenv \
    && mkdir /usr/local/share/tessdata \
    && wget 'https://github.com/tesseract-ocr/tessdata_best/blob/master/ces.traineddata?raw=true' -O ces.traineddata \
    && mv *.traineddata /usr/local/share/tessdata/

ENV TESSDATA_PREFIX=/usr/local/share/tessdata

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

ADD Pipfile Pipfile.lock /pylunch/
WORKDIR /pylunch
RUN /bin/bash -c "pip3 install --no-cache-dir -r <(pipenv lock -r)"

ADD . /pylunch
RUN pip3 install --no-cache-dir /pylunch

EXPOSE 8000
CMD ["./run_flask.sh"]

