import boto3
from flask import Flask
from flask import render_template
from datetime import datetime
from dotenv import load_dotenv
import json
import os
import requests
import time

app = Flask(__name__)

load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')


def splitList(userList, split=3):
    for i in range(0, len(userList), split):
        yield userList[i:i + split]


def checkForImageJSON(json_list):
    for player in json_list:
        if not os.path.isfile(f"/static/images/faces/{player['username']}.png"):
            with open(f"{os.getenv('IMAGES')}faces/{player['username']}.png", 'wb') as image:
                image.write(requests.get(
                    f"https://skindentity.deta.dev/face/?player_name={player['username']}&upscale=8").content)
            with open(f"{os.getenv('IMAGES')}portraits/{player['username']}.png", 'wb') as image:
                image.write(requests.get(
                    f"https://skindentity.deta.dev/portrait/?player_name={player['username']}&upscale=8").content)


def checkForImageList(player_list):
    for player in player_list:
        if not os.path.isfile(f"{os.getenv('IMAGES')}faces/{player}.png"):
            with open(f"/static/images/faces/{player}.png", 'wb') as image:
                image.write(requests.get(f"https://skindentity.deta.dev/face/?player_name={player}&upscale=8").content)
            with open(f"{os.getenv('IMAGES')}portraits/{player}.png", 'wb') as image:
                image.write(requests.get(f"https://skindentity.deta.dev/portrait/?player_name={player}&upscale=8")
                            .content)


@app.route('/')
def hello():
    with open(os.getenv("JSON"), 'r') as readPlayerList:
        userList = json.load(readPlayerList)

    table = dynamodb.Table(os.getenv('TABLENAME'))
    response = table.scan()
    data = response['Items']
    data.sort(key=lambda date: datetime.strptime(date['last_seen'], "%d/%m/%Y %H:%M:%S"), reverse=True)
    checkForImageList(userList)
    checkForImageJSON(data)

    return render_template('main.html', users=list(splitList(userList)), ip=os.getenv("IP"), offlineList=data)


if __name__ == "__main__":
    app.run()

