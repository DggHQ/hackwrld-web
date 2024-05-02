#!/usr/bin/env python3
from flask import Flask, request, redirect, url_for, session, render_template, abort
from functools import wraps
import requests
import urllib.parse
from hashlib import sha256
import uuid
import base64
import string
import random
import json
import os
from datetime import timedelta
import redis

from k8s import *

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecretkey")
app.config['PERMANENT_SESSION_LIFETIME'] =  timedelta(minutes=1440)

callback_url_setting = os.getenv("CALLBACK_URL", "http://localhost:8888/callback")
app_id_setting = os.getenv("APP_ID")
app_secret_setting = os.getenv("APP_SECRET")
app_websocket_url = os.getenv("WS_URL", "ws://localhost:8080/ws")
app_namespace = os.getenv("NAMESPACE", "hackwrld")
app_nats_host = os.getenv("NATS_HOST")
app_etcs_endpoints = os.getenv("ETCD_ENDPOINTS")
app_maintenance = os.getenv("MAINTENANCE", "disabled")
app_valkey_host = os.getenv("VALKEY_HOST", "valkey.hackwrld.svc")





#CHALLENGES = {}
app_id = app_id_setting
secret = app_secret_setting
callback_url = urllib.parse.quote(callback_url_setting)
r = redis.Redis(host=app_valkey_host, port=6379, decode_responses=True)

@app.before_request
def check_under_maintenance():
    if app_maintenance == "enabled":  #this flag can be anything, read from file,db or anything
        abort(503)
    

@app.errorhandler(503)
def error_503(error):
    return render_template("maintenance.html") 


def b64_encode(code_verifier, hashed_secret):
    val = code_verifier + hashed_secret
    return_value_hex = sha256(val.encode('ascii')).hexdigest()
    return base64.b64encode(return_value_hex.encode('ascii')).decode('ascii')


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "userdata" not in session:
            return redirect(url_for('auth', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def root():
    if 'userdata' in session:
        return redirect(url_for("prepare", userID=str(session["userdata"]["userId"])))
    return redirect(url_for("auth"))

@app.route("/auth")
def auth():
    hashed_secret = sha256(secret.encode('ascii')).hexdigest()
    code_verifier = ''.join(random.choices(
        string.ascii_letters+string.digits,
        k=43))
    code_challenge = b64_encode(code_verifier, hashed_secret)
    state = str(uuid.uuid4())
    #CHALLENGES[state] = code_verifier
    r.set(state, code_verifier)
    url = f"https://www.destiny.gg/oauth/authorize?response_type=code&client_id={app_id}&redirect_uri={callback_url}&state={state}&code_challenge={code_challenge}"
    return redirect(url, code=302)


@app.route("/logout")
@login_required
def logout():
    session.pop("userdata")
    return "Logged out", 200


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    code_verifier = r.get(state) #CHALLENGES[state]
    auth_url = f"https://www.destiny.gg/oauth/token?grant_type=authorization_code&code={code}&client_id={app_id}&redirect_uri={callback_url}&code_verifier={code_verifier}"
    auth_response = requests.get(auth_url)
    data = auth_response.json()

    user_data_url = f"https://www.destiny.gg/api/userinfo?token={data['access_token']}"
    user_response = requests.get(user_data_url)
    userdata = user_response.json()
    session["userdata"] = userdata
    session.permanent = True
    r.delete(state)
    return redirect(url_for('prepare', userID=userdata["userId"]))


# API call only
@app.route("/cc/<userID>/create", methods=["POST"])
@login_required
def create_cc(userID):
    if str(session["userdata"]["userId"]) != userID:
        return json.dumps({"error": "unauthicated"}), 403
    '''
    Create command center deployment for user if it does not exist.
    '''
    ips = get_cc_ip(
        userId=userID,
        namespace=app_namespace
    )
    # Redirect directly if command center exists.
    if len(ips) > 0:
        return json.dumps({"success": "already exists"}), 200
    
    # Create deployment if no ips have been returned
    config.load_incluster_config()
    team = str(session["userdata"]["team"])
    if team == None:
        team = "none"
    deployment = create_deployment_object(
        requestor=userID,
        nick=str(session["userdata"]["nick"]),
        team=team,
        nats_host=app_nats_host,
        etcd_endpoints=app_etcs_endpoints,
        deployment_name=f"{userID}-commandcenter"
    )
    v1 = client.AppsV1Api()
    v1.create_namespaced_deployment(
        body=deployment, namespace=app_namespace
    )
    return json.dumps({"success": "created_deployment"}), 200

@app.route("/cc/<userID>/prepare")
@login_required
def prepare(userID):
    '''
    Endpoint that shows a loading screen while the containers
    are being started.
    Contains a website with a javascript that periodically
    should check connection.
    On manual retry it should just straight go to the game.
    '''
    if str(session["userdata"]["userId"]) != userID:
        return "Error: Unauthorized User", 403
    return render_template("getready.html", userid=userID)


@app.route("/state")
@login_required
def state():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/state"
    state = requests.get(commandCenterIP).json()
    return json.dumps(state)

@app.route("/upgrade/firewall", methods=["POST"])
@login_required
def upgrade_firewall():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/firewall"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/firewall/max", methods=["POST"])
@login_required
def upgrade_firewall_max():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/firewall/max"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/scanner", methods=["POST"])
@login_required
def upgrade_scanner():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/scanner"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/scanner/max", methods=["POST"])
@login_required
def upgrade_scanner_max():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/scanner/max"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/stealer", methods=["POST"])
@login_required
def upgrade_stealer():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/stealer"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/stealer/max", methods=["POST"])
@login_required
def upgrade_stealer_max():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/stealer/max"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/miner", methods=["POST"])
@login_required
def upgrade_miner():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/miner"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/miner/max", methods=["POST"])
@login_required
def upgrade_miner_max():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/miner/max"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode


@app.route("/scan/out", methods=["POST"])
@login_required
def init_scan():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/scan/out"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/steal", methods=["POST"])
@login_required
def init_steal():
    in_data = request.get_json()
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/steal"
    data = requests.post(
        url=commandCenterIP,
        json=in_data
        )
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/vault/store", methods=["POST"])
@login_required
def store_vault():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/vault/store"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/upgrade/vault", methods=["POST"])
@login_required
def upgrade_vault():
    # Query backend pod 
    # Get pod (with label selectors) ip via k8s api first then get the state
    ips = get_cc_ip(
        userId=str(session["userdata"]["userId"]),
        namespace=app_namespace
    )
    commandCenterIP = f"http://{ips[0]['ip']}/upgrade/vault"
    data = requests.post(commandCenterIP)
    state = data.json()
    statusCode = data.status_code
    return json.dumps(state), statusCode

@app.route("/cc/<userID>/home")
@login_required
def home(userID):
    if str(session["userdata"]["userId"]) != userID:
        return "Error: Unauthorized User", 403
    return render_template("idx.html", userid=userID, nick=str(session["userdata"]["nick"]), websocket_url=app_websocket_url)

@app.route("/cc/<userID>/info")
@login_required
def user_infos(userID):
    if str(session["userdata"]["userId"]) != userID:
        return "Error: Unauthorized User", 403
    return str(session["userdata"]), 200

@app.route("/debug")
def debug():
    return render_template("idx.html", userid="userID", nick="", websocket_url="app_websocket_url")


@app.route("/prevround")
def previous_round():
    ts = r.get("ts")
    return render_template("leaderboard.html", ts=ts)

@app.route("/help")
def help():
    return render_template("help.html")


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8888)
