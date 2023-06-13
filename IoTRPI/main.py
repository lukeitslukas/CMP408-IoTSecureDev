import adafruit_ssd1306
import board
import boto3
import busio
import ctypes
from datetime import datetime
from dotenv import load_dotenv
import fcntl
import json
from mctools import RCONClient
import numpy
import os
import paramiko
from PIL import Image, ImageDraw, ImageFont
import re
import time

# setup environment files and database connection
load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')


# header file
class gpio_pins(ctypes.Structure):
    _fields_ = [
        ("pin", ctypes.c_uint),
        ("value", ctypes.c_int)
    ]


IOCTL_LEDCONTROLLER_GPIO_READ = 0x65
IOCTL_LEDCONTROLLER_GPIO_WRITE = 0x66

LED_ON = 1
LED_OFF = 0

DEVICE_NAME = "ledControllerDev"
CLASS_NAME = "ledControllerCLS"
DRIVER_NAME = "ledController.ko"
DRIVER_PARAMS = "led_gpios=23,24"

# end header file

# setup OLED screen
WIDTH = 128
HEIGHT = 64
BORDER = 0
CHAR_LENGTH = 24
FONT_SIZE = 12
FONT = ImageFont.truetype("W95FA.otf", size=FONT_SIZE)

i2c = busio.I2C(board.SCL, board.SDA)
display = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=0x3c)

# setup mc RCON client & ANSI Cleaner
ANSI_CLEANER = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]")

HOST = os.getenv("MINECRAFTIP")
PORT = 3870

rcon = RCONClient(HOST, port=PORT)

AUTH = rcon.login(os.getenv("RCONPASS"))

# setup paramiko for SSH with ec2

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(os.getenv("EC2HOST"), username=os.getenv("EC2USER"), key_filename=os.getenv("PAIRKEY"))

# setup dynamodb table
table = dynamodb.Table(os.getenv('TABLENAME'))


# clear screen and display
def clearScreen():
    display.fill(0)
    display.show()


# clear screen but don't display
def subtleClearScreen():
    display.fill(0)


# list players in server and parse response
def listServer():
    resp = None
    if AUTH:
        resp = rcon.command('list')  # run command list
    else:
        resp = "Auth Error"

    resp = ANSI_CLEANER.sub("", resp)  # clean ANSI from response
    resp = resp.split(": ")[1].strip().split(', ')  # split into users

    return resp


# writing to OLED
def writeMessage(msg):
    subtleClearScreen()
    image = Image.new("1", (display.width, display.height))
    draw = ImageDraw.Draw(image)
    draw.text((BORDER, BORDER), msg, font=FONT, fill=255)
    display.image(image)
    display.show()


# updating LED
def ledChange(pin, command):
    gpio = gpio_pins(pin, command)
    fcntl.ioctl(fd, IOCTL_LEDCONTROLLER_GPIO_WRITE, gpio)


# add player to DB
def addItem(username, last_seen):
    try:
        table.put_item(
            Item={
                'username': username,
                'last_seen': last_seen
            }
        )
    except Exception as error:
        print(e)


# remove player from db
def removeItem(username):
    try:
        table.delete_item(
            Key={
                'username': username
            }
        )
    except Exception as error:
        print(e)


# when player joins the server
def addPlayer(player):
    # open playerlist file and update
    with open(os.getenv("JSON"), 'r+') as updatePlayerList:
        playerList = json.load(updatePlayerList)
        playerList.append(player)
        updatePlayerList.seek(0)
        json.dump(playerList, updatePlayerList, indent=4)
        updatePlayerList.truncate()
    sftp = client.open_sftp()   # create ssh client
    sftp.put(os.getenv("JSON"), os.getenv("OFFSITEJSON"))   # upload updated json file
    sftp.close()    # close ssh client
    writeMessage(f"{player} joined.")   # print new player to oled and flash LED
    removeItem(player)
    ledChange(23, LED_ON)
    time.sleep(2)
    ledChange(23, LED_OFF)


# when player leaves the server
def removePlayer(player):
    # open playerlist file and update
    with open(os.getenv("JSON"), 'r+') as updatePlayerList:
        playerList = json.load(updatePlayerList)
        playerList.remove(player)
        updatePlayerList.seek(0)
        json.dump(playerList, updatePlayerList, indent=4)
        updatePlayerList.truncate()
    sftp = client.open_sftp()                               # create ssh client
    sftp.put(os.getenv("JSON"), os.getenv("OFFSITEJSON"))   # upload updated json file
    sftp.close()                                            # close ssh client
    writeMessage(f"{player} left.")                         # print new player to old and flash led
    addItem(player, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    ledChange(24, LED_ON)
    time.sleep(2)
    ledChange(24, LED_OFF)


def main():
    serverList, oldServerList = None, None                      # create blank server lists

    serverList = listServer()                                     # get current server status and send to EC2
    if serverList is None:
        print("Error: No response")
    elif serverList == "Auth Error":
        print("Auth error")
    elif serverList[0] == '':
        with open(os.getenv("JSON"), 'w') as updatePlayerList:
            json.dump([], updatePlayerList, indent=4)
        sftp = client.open_sftp()
        sftp.put(os.getenv("JSON"), os.getenv("OFFSITEJSON"))
        sftp.close()
    else:
        with open(os.getenv("JSON"), 'w') as updatePlayerList:
            json.dump(serverList, updatePlayerList, indent=4)
        sftp = client.open_sftp()
        sftp.put(os.getenv("JSON"), os.getenv("OFFSITEJSON"))
        sftp.close()

    while True:
        # compare old and new serverList
        if serverList:
            oldServerList = serverList
        serverList = listServer()

        if oldServerList is not None and oldServerList != serverList:
            if len(oldServerList) > len(serverList):  # if old server list larger, user left
                for player in oldServerList:
                    if player not in serverList:
                        print(f"Player {player} left")
                        removePlayer(player)

            elif len(serverList) > len(oldServerList):      # if old server list smaller, user joined
                for player in serverList:
                    if player not in oldServerList:
                        print(f"Player {player} joined")
                        addPlayer(player)

            elif len(serverList) == len(oldServerList):     # if server list the same, maybe someone left and someone
                # else joined
                if oldServerList[0] == '' and serverList[0] != '':
                    print(f"Player {serverList[0]} joined")
                    addPlayer(serverList[0])
                elif serverList[0] == '' and oldServerList[0] != '':
                    print(f"Player {oldServerList[0]} left")
                    removePlayer(oldServerList[0])
                else:
                    isNewInOld = numpy.isin(oldServerList, serverList)
                    for i in range(0, len(isNewInOld)):
                        if not isNewInOld[i]:
                            print(f"Player {serverList[i]} joined")
                            addPlayer(serverList[i])
                    isOldInNew = numpy.isin(serverList, oldServerList)
                    for i in range(0, len(isOldInNew)):
                        if not isOldInNew[i]:
                            print(f"Player {oldServerList[i]} left")
                            removePlayer(oldServerList[i])

        # parse any errors or update oled
        if serverList is None:
            msg = "Error: No response"
        elif serverList == "Auth Error":
            msg = serverList
        elif serverList[0] == '':
            msg = f"No players online"
        else:
            msg = f"Players online: {len(serverList)}\n"
            for player in serverList:
                msg = msg + player + f'\n'

        subtleClearScreen()
        writeMessage(msg)
        time.sleep(15)


try:
    fd = open(f"//dev//{DEVICE_NAME}", 'r')
    if not fd:
        print("No open file")
    main()
except KeyboardInterrupt:
    print("\nProgram ended, goodbye!")
    clearScreen()
    fd.close()
    rcon.stop()
except Exception as e:
    print(e)
    clearScreen()
    fd.close()
    rcon.stop()
