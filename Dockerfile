FROM python:3-alpine

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN rm -rf .dockerignore .git .gitignore Dockerfile *.zip

CMD [ "python", "./app.py" ]