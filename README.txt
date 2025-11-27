Contact Info
============

Group Members & Email Addresses:
    Jayadeep Kothapalli  – jsko232@uky.edu
    Harshini Ponnam      – hpo245@uky.edu
    Rudwika Manne        – rma425@uky.edu

Imporatnt Information:
=====================
This project includes additional support files such as security.py
(for authentication & encryption), and the assets/ folder
(fonts, images, sounds, helperCode). These must remain in the same directory
structure for the program to run correctly.


Versioning
==========

GitHub Link:
    https://github.com/jayadeepkp/CS371_Project_Fall2025


General Info
============

This project implements a complete multiplayer Pong game using a
client–server architecture.

The server:
    • Accepts two players (left & right) and any number of spectators  
    • Runs the authoritative game loop (ball, paddles, scoring)  
    • Supports “Play Again” rematches (both players press R)  
    • Tracks wins in a persistent leaderboard (leaderboard.json)  
    • Serves the leaderboard webpage on port 80  
    • Provides user registration, login, password hashing, and  
      encrypted gameplay communication using Fernet  

The client:
    • Connects to the server using TCP  
    • Provides a Tkinter join screen (falls back to CLI if Tk is missing)  
    • Renders the Pong game using Pygame  
    • Sends encrypted paddle movement and rematch signals  
    • Supports full spectator mode (read-only stream)  


Install Instructions
====================

Python Version:
This project requires:

    Python 3.10 or newer

Recommended versions: Python 3.10 – Python 3.12

Older versions of Python may fail to install the "cryptography" package.

1. Create and activate a virtual environment (recommended):

       python3 -m venv venv
       source venv/bin/activate        (macOS/Linux)
       venv\Scripts\Activate.ps1       (Windows PowerShell)

2. Install required libraries:

       pip3 install -r requirements.txt


Running the Server
==================

Run the server from the project root:

    python3 pongServer.py

The server will:
    • Bind to 0.0.0.0:6000 for game clients  
    • Start an HTTP leaderboard on port 80 (may require admin rights)  
    • Wait for 2 players to connect  
    • Ask each player to register or log in

Make sure leaderboard.json, users.json, and fernet.key will be auto-created if missing.

Running the Client
==================

Start the client on another machine (or multiple machines):

    python3 pongClient.py

First two connections become:
    • Player LEFT
    • Player RIGHT

Any additional connections become spectators.

Players must:
    • Register or login once connected  
    • Use Up/Down arrows to move  
    • Press R after a win/lose to start the next round


Controls
========

Players:
    Up Arrow    – Move paddle up
    Down Arrow  – Move paddle down
    R           – After game over, press to signal ready for rematch

Spectators:
    No controls (view only)


Note
==========

- HTTP leaderboard page requires port 80. On some systems
  this may require admin/root privileges. If unavailable,
  the Pong game still works normally.
- Tkinter UI may not appear on minimal environments;
  the client automatically switches to CLI mode.




Sequence Client-Server Model.

+----------------+                     +----------------+
|  PlayerClient  |                     |   PongServer   |
+----------------+                     +----------------+
        |                                         |
        |------------- TCP connect -------------->|
        |                                         |
        |<---- "SCREEN_WIDTH SCREEN_HEIGHT side" -|
        |   (e.g., "640 480 left")               |
        |                                         |
        |         AUTHENTICATION (plaintext)      |
        |     (loop until login/register OK)      |
        |---------------------------------------->|
        |  "register/login username password"     |
        |                                         |
        |<----------------------------------------|
        |   "OK registered" / "OK logged-in"      |
        |   or "ERR ..."                          |
        |   (repeat on error)                     |
        |                                         |
        |       ENCRYPTED GAMEPLAY LOOP           |
        |      (runs every frame at 60 FPS)       |
        |---------------------------------------->|
        |  encrypt("up" / "down" / "")            |
        |                                         |
        |<----------------------------------------|
        |  encrypt("leftY rightY ballX ballY     |
        |           lScore rScore")              |
        |                                         |
        |   (client renders paddles, ball, score)|
        |                                         |
        |      GAME OVER & REMATCH SEQUENCE       |
        |<----------------------------------------|
        | encrypt("... state with WIN_SCORE ...") |
        |   (client shows win message)            |
        |                                         |
        |---- encrypt("ready") after player R --->|
        |                                         |
        |          (server side logic)            |
        |  if left_ready && right_ready:          |
        |      reset scores, paddles, ball        |
        |      start new game                     |
        |                                         |
        |<----------------------------------------|
        |  encrypt(new game state frames...)      |
        |                                         |
        :      (loop continues for next game)     :

==================================================================

+--------------------+                  +----------------+
|  SpectatorClient   |                  |   PongServer   |
+--------------------+                  +----------------+
          |                                      |
          |----------- TCP connect ------------->|
          |                                      |
          |<--- "SCREEN_WIDTH SCREEN_HEIGHT spec"|
          |                                      |
          |     SPECTATOR VIEW LOOP (every frame)|
          |------------------------------------->|
          |  ""   (empty movement line, ignored) |
          |                                      |
          |<-------------------------------------|
          |  "leftY rightY ballX ballY          |
          |      lScore rScore"   (PLAINTEXT)    |
          |                                      |
          | (client updates paddles/ball/score)  |
          |                                      |
          :         (loop repeats)               :