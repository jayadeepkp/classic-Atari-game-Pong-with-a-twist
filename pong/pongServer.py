# =================================================================================================
# Contributing Authors:	    Jayadeep Kothapalli,Harshini Ponnam
# Email Addresses:          jsko232@uky.edu, hpo245@uky.edu
# Date:                     2025-11-23
# Purpose:                  Multi-threaded TCP Pong server.
#                           Accepts two clients as players (left/right), plus any number of
#                           additional spectator clients. Runs authoritative game loop (ball,
#                           paddles, score) and broadcasts state to all connected clients.
#                           Supports "reset" command so players can play multiple games.
# Misc:                     CS 371 Fall 2025 Project
# =================================================================================================

import socket
import threading

import pygame
from assets.code.helperCode import Paddle, Ball

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


# Screen dimensions (must match what clients expect)
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480

# How many points to win
WIN_SCORE = 5

# File to persist leaderboard between server restarts
LEADERBOARD_FILE = "leaderboard.json"

# Protects concurrent access to leaderboard
leaderboard_lock = threading.Lock()

# ---------------------------------------------------------------------------------------------
# Author(s):    Harshini Ponnam 
# Purpose:      Helper functions for loading, saving, and updating the persistent leaderboard.
#               The leaderboard tracks total wins for each player's initials across all games.
# Pre:          leaderboard.json may or may not exist at startup.
# Post:         leaderboard.json is read/written safely; leaderboard dictionary is kept in-sync
#               and protected with a threading lock for multi-threaded access.
# ---------------------------------------------------------------------------------------------

def load_leaderboard():
    """Load leaderboard from disk or return empty dict if not present."""
    try:
        with open(LEADERBOARD_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_leaderboard(board: dict) -> None:
    """Save leaderboard to disk."""
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(board, f)


# In-memory leaderboard: { "HP": 3, "RM": 1, ... }
leaderboard = load_leaderboard()


def record_win(initials: str) -> None:
    """
    Increment win count for the given player's initials and persist to disk.
    """
    if not initials:
        return
    initials = initials.strip().upper()
    with leaderboard_lock:
        leaderboard[initials] = leaderboard.get(initials, 0) + 1
        save_leaderboard(leaderboard)

# ---------------------------------------------------------------------------------------------
# Author(s):    Harshini Ponnam 
# Purpose:      A simple HTTP GET handler that serves a styled HTML leaderboard page at:
#                   http://<server-ip>/           OR
#                   http://<server-ip>/leaderboard
#               Displays all player initials and their accumulated win counts.
# Pre:          leaderboard dictionary must be populated; access is protected by leaderboard_lock.
# Post:         Sends an HTML response showing the current leaderboard.
# ---------------------------------------------------------------------------------------------

class LeaderboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/leaderboard"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        with leaderboard_lock:
            items = sorted(leaderboard.items(), key=lambda kv: kv[1], reverse=True)

        rows = ""
        for initials, wins in items:
            rows += f"<tr><td>{initials}</td><td>{wins}</td></tr>"

        html = f"""
        <html>
        <head>
            <title>CS371 Pong Leaderboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #111; color: #eee; }}
                table {{ border-collapse: collapse; margin: 40px auto; }}
                th, td {{ border: 1px solid #555; padding: 8px 16px; }}
                th {{ background: #333; }}
                h1 {{ text-align: center; }}
            </style>
        </head>
        <body>
            <h1>Pong Leaderboard</h1>
            <table>
                <tr><th>Player Initials</th><th>Wins</th></tr>
                {rows or "<tr><td colspan='2'>No games recorded yet.</td></tr>"}
            </table>
        </body>
        </html>
        """

        html_bytes = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

# ---------------------------------------------------------------------------------------------
# Author(s):    Harshini Ponnam 
# Purpose:      Starts a background HTTP server on port 80 using LeaderboardHandler. Runs
#               concurrently with the main Pong game server without blocking gameplay.
# Pre:          Port 80 must be available (may require administrator privileges on some systems).
# Post:         A persistent leaderboard webpage is accessible while the Pong game is running.
# ---------------------------------------------------------------------------------------------

def start_leaderboard_server():
    """Run a simple HTTP server on port 80 to show the leaderboard."""
    try:
        httpd = HTTPServer(("0.0.0.0", 80), LeaderboardHandler)
        print("[SERVER] Leaderboard HTTP server running on port 80...")
        httpd.serve_forever()
    except Exception as e:
        print(f"[SERVER] Could not start leaderboard HTTP server on port 80: {e}")

# ---------------------------------------------------------------------------------------------
# Author:      Jayadeep Kothapalli
# Purpose:     Handle incoming messages from one client and update movement/reset state.
# Pre:         conn is a connected TCP socket; move_dict is a shared dict with key "value";
#              reset_flag is a shared dict with key "value" used to trigger a game reset.
# Post:        move_dict["value"] is updated based on messages from this client. If a "reset"
#              message is received, reset_flag["value"] is set to True so the main loop can
#              reset the game state.
# ---------------------------------------------------------------------------------------------
def handle_client_input(
    conn: socket.socket,
    move_dict: dict,
    reset_flag: dict,
    name: str
) -> None:
    """
    Thread function to handle incoming messages from a single client.

    Messages:
      "up" / "down" / ""   -> update move_dict["value"]
      "reset"              -> set reset_flag["value"] = True
    """
    try:
        with conn:
            buffer = ""
            while True:
                data = conn.recv(1024)
                if not data:
                    print(f"[SERVER] {name} disconnected.")
                    break
                buffer += data.decode()
                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = line.strip()
                    if msg in ("up", "down", ""):
                        move_dict["value"] = msg
                    elif msg == "reset":
                        reset_flag["value"] = True
    except Exception as e:
        print(f"[SERVER] Exception in handle_client_input for {name}: {e}")


# ---------------------------------------------------------------------------------------------
# Author:      Jayadeep Kothapalli
# Purpose:     Accept additional spectator clients after the two players have connected.
#              Each spectator receives a "spec" config line and is added to the spectators
#              list so they receive state updates, but they do not control any paddles.
# Pre:         server is a bound/listening TCP socket; spectators is a shared list of sockets;
#              spectators_lock is a threading.Lock protecting access to that list.
# Post:        As new spectator clients connect, they are sent a config line and appended to
#              spectators. If the server socket is closed, this loop exits cleanly.
# ---------------------------------------------------------------------------------------------
def accept_spectators(
    server: socket.socket,
    spectators: list,
    spectators_lock: threading.Lock
) -> None:
    while True:
        try:
            conn, addr = server.accept()
        except OSError:
            # Server socket was closed; exit thread
            print("[SERVER] accept_spectators: server socket closed, stopping.")
            break

        print(f"[SERVER] Spectator connected from {addr}")
        try:
            config_spec = f"{SCREEN_WIDTH} {SCREEN_HEIGHT} spec\n".encode()
            conn.sendall(config_spec)
        except Exception as e:
            print(f"[SERVER] Failed to send config to spectator {addr}: {e}")
            conn.close()
            continue

        with spectators_lock:
            spectators.append(conn)
        print(f"[SERVER] Total spectators: {len(spectators)}")


# ---------------------------------------------------------------------------------------------
# Author:      Jayadeep Kothapalli
# Purpose:     Accept two player clients, then any number of spectators, and run the main
#              Pong game loop. Broadcasts state to all connected clients until someone
#              disconnects, then shuts down.
# Pre:         host/port are free to bind. Expects at least two clients to connect for play.
# Post:        After clients disconnect or an error occurs, closes all sockets and quits
#              Pygame cleanly.
# ---------------------------------------------------------------------------------------------
def run_server(host: str = "0.0.0.0", port: int = 6000) -> None:
    """
    Main server logic:
    - Creates a listening socket
    - Accepts two clients (left & right) as players
    - Starts a thread to accept any number of additional spectator clients
    - Sends initial config line: "width height side\n" (side = left/right/spec)
    - Runs authoritative game loop and broadcasts state to all clients
    """
    pygame.init()  # needed for pygame.Rect, etc.
    clock = pygame.time.Clock()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((host, port))
    server.listen(10)  # allow more than 2 pending connections
    print(f"[SERVER] Listening on {host}:{port} ...")

    # Start HTTP leaderboard server in the background
    http_thread = threading.Thread(target=start_leaderboard_server, daemon=True)
    http_thread.start()

    # -------------------------------------------------------------------------
    # Accept left and right players (required for basic two-player game)
    # -------------------------------------------------------------------------
    client_left, addr_left = server.accept()
    print(f"[SERVER] Left player connected from {addr_left}")
    config_left = f"{SCREEN_WIDTH} {SCREEN_HEIGHT} left\n".encode()
    client_left.sendall(config_left)

    client_right, addr_right = server.accept()
    print(f"[SERVER] Right player connected from {addr_right}")
    config_right = f"{SCREEN_WIDTH} {SCREEN_HEIGHT} right\n".encode()
    client_right.sendall(config_right)


    # Ask the server operator for player initials (used in the leaderboard)
    try:
        left_initials = input("Enter initials for LEFT player (e.g., HP): ").strip().upper() or "LEFT"
        right_initials = input("Enter initials for RIGHT player (e.g., RM): ").strip().upper() or "RIGHT"
    except EOFError:
        # In case input is not available (e.g., some environments), fall back to defaults
        left_initials = "LEFT"
        right_initials = "RIGHT"

    # -------------------------------------------------------------------------
    # Prepare shared movement and reset state
    # -------------------------------------------------------------------------
    left_move = {"value": ""}
    right_move = {"value": ""}
    reset_flag = {"value": False}

    # Spectators: additional clients who can watch the game
    spectators: list[socket.socket] = []
    spectators_lock = threading.Lock()

    # Start input threads for the two players
    t_left = threading.Thread(
        target=handle_client_input,
        args=(client_left, left_move, reset_flag, "LEFT"),
        daemon=True,
    )
    t_right = threading.Thread(
        target=handle_client_input,
        args=(client_right, right_move, reset_flag, "RIGHT"),
        daemon=True,
    )
    t_left.start()
    t_right.start()

    # Start an acceptor thread to allow any number of spectator connections
    t_specs = threading.Thread(
        target=accept_spectators,
        args=(server, spectators, spectators_lock),
        daemon=True,
    )
    t_specs.start()

    # -------------------------------------------------------------------------
    # Game objects (server authoritative)
    # -------------------------------------------------------------------------
    paddleHeight = 50
    paddleWidth = 10
    paddleStartPosY = (SCREEN_HEIGHT // 2) - (paddleHeight // 2)

    leftPaddle = Paddle(pygame.Rect(10, paddleStartPosY, paddleWidth, paddleHeight))
    rightPaddle = Paddle(
        pygame.Rect(SCREEN_WIDTH - 20, paddleStartPosY, paddleWidth, paddleHeight)
    )

    ball = Ball(pygame.Rect(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2, 5, 5), -5, 0)

    topWall = pygame.Rect(-10, 0, SCREEN_WIDTH + 20, 10)
    bottomWall = pygame.Rect(-10, SCREEN_HEIGHT - 10, SCREEN_WIDTH + 20, 10)

    lScore = 0
    rScore = 0
    # To avoid counting the same win multiple times before a reset
    winner_recorded = False
    print("[SERVER] Game loop started.")

    try:
        while True:
            # Handle reset request (from either player)
            if reset_flag["value"]:
                print("[SERVER] Reset requested, resetting game state.")
                lScore = 0
                rScore = 0
                leftPaddle.rect.y = paddleStartPosY
                rightPaddle.rect.y = paddleStartPosY
                ball.reset(nowGoing="left")
                reset_flag["value"] = False
                winner_recorded = False

            # Update paddles based on last movement commands
            # Left paddle
            if left_move["value"] == "down":
                if leftPaddle.rect.bottom < SCREEN_HEIGHT - 10:
                    leftPaddle.rect.y += leftPaddle.speed
            elif left_move["value"] == "up":
                if leftPaddle.rect.top > 10:
                    leftPaddle.rect.y -= leftPaddle.speed

            # Right paddle
            if right_move["value"] == "down":
                if rightPaddle.rect.bottom < SCREEN_HEIGHT - 10:
                    rightPaddle.rect.y += rightPaddle.speed
            elif right_move["value"] == "up":
                if rightPaddle.rect.top > 10:
                    rightPaddle.rect.y -= rightPaddle.speed
          
            # If someone has already won, stop ball movement but allow reset
            if lScore >= WIN_SCORE or rScore >= WIN_SCORE:
                # Record the winner once per game (before reset)
                if not winner_recorded:
                    if lScore >= WIN_SCORE:
                        record_win(left_initials)
                        print(f"[SERVER] Game over. Winner: {left_initials}")
                    elif rScore >= WIN_SCORE:
                        record_win(right_initials)
                        print(f"[SERVER] Game over. Winner: {right_initials}")
                    winner_recorded = True
                # No ball movement while game is "frozen" at win state
            else:
                # Ball movement
                ball.updatePos()

                # Ball out of bounds -> score
                if ball.rect.x > SCREEN_WIDTH:
                    lScore += 1
                    ball.reset(nowGoing="left")
                elif ball.rect.x < 0:
                    rScore += 1
                    ball.reset(nowGoing="right")

                # Ball & paddle collisions
                if ball.rect.colliderect(leftPaddle.rect):
                    ball.hitPaddle(leftPaddle.rect.center[1])
                elif ball.rect.colliderect(rightPaddle.rect):
                    ball.hitPaddle(rightPaddle.rect.center[1])

                # Ball & wall collisions
                if ball.rect.colliderect(topWall) or ball.rect.colliderect(bottomWall):
                    ball.hitWall()


            # Prepare state line for all clients
            state_line = (
                f"{leftPaddle.rect.y} {rightPaddle.rect.y} "
                f"{ball.rect.x} {ball.rect.y} {lScore} {rScore}\n"
            )
            data = state_line.encode()

            # Send state to both players
            try:
                client_left.sendall(data)
                client_right.sendall(data)
            except Exception as e:
                print(f"[SERVER] A player disconnected while sending. Error: {e}")
                break

            # Send state to all spectators
            with spectators_lock:
                dead_specs = []
                for spec in spectators:
                    try:
                        spec.sendall(data)
                    except Exception as e:
                        print(f"[SERVER] Spectator send failed, removing: {e}")
                        dead_specs.append(spec)
                # Remove any spectators that errored
                for d in dead_specs:
                    try:
                        d.close()
                    except Exception:
                        pass
                    spectators.remove(d)

            clock.tick(60)  # 60 updates per second

    finally:
        print("[SERVER] Shutting down.")
        try:
            client_left.close()
        except Exception:
            pass
        try:
            client_right.close()
        except Exception:
            pass

        # Close all spectators
        try:
            with spectators_lock:
                for spec in spectators:
                    try:
                        spec.close()
                    except Exception:
                        pass
                spectators.clear()
        except Exception:
            pass

        try:
            server.close()
        except Exception:
            pass

        pygame.quit()
        print("[SERVER] Server shut down.")


if __name__ == "__main__":
    run_server(host="0.0.0.0", port=6000)