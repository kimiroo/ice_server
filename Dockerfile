FROM python:3.13-alpine

ENV HOST=0.0.0.0
ENV PORT=28080

COPY . /app
WORKDIR /app

RUN apk add --no-cache curl build-base python3-dev
RUN pip install -r requirements.txt

EXPOSE $PORT

HEALTHCHECK --interval=5s --timeout=3s CMD curl -f http://127.0.0.1:$PORT/api/v1/health || exit 1

CMD ["python", "-u", "/app/app.py"]