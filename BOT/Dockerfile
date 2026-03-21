FROM python:3.11.5
 
WORKDIR /app

COPY ./requirements.txt requirements.txt 
RUN pip install -r requirements.txt

# ADD pkg_updates/logger.py /usr/local/lib/python3.11/site-packages/chainlit/logger.py

COPY . /app 

EXPOSE 5100

# Not sure wether base url path is required or Not
CMD ["chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "5100"]