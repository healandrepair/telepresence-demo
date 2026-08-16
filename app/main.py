import os
import socket

from flask import Flask

app = Flask(__name__)

TITLE = os.environ.get("TITLE", "Hello World")


@app.get("/")
def hello():
    response = app.make_response(f"{TITLE} (from pod: {socket.gethostname()})\n")
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.get("/healthz")
def healthz():
    return "ok\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
