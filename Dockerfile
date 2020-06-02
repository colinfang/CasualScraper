FROM python:3.8-slim-buster
RUN apt update && apt install -qy git

# Lint
RUN pip install mypy pylint
RUN pip install requests lxml pymongo dnspython

WORKDIR /src

ADD CasualScraper CasualScraper


