#!/usr/bin/env python
# coding: utf-8

"""
Game Playing Agent (Tic Tac Toe) using PraisonAIAgents

Two AI agents play against each other, coordinated by a referee agent.
This script is CI-friendly: it uses dummy moves if API keys are not set.
"""

import os
from praisonaiagents import Agent

# Set up key (robust, CI-safe)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-..")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

def is_valid_key(key, prefix):
    return key and key != f"{prefix}-.." and key.startswith(prefix)

# Custom Tool: Tic Tac Toe Board & Logic
class TicTacToeBoard:
    def __init__(self):
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.current_player = "X"

    def display(self):
        for row in self.board:
            print("|".join(row))
            print("-" * 5)

    def valid_moves(self):
        return [(i, j) for i in range(3) for j in range(3) if self.board[i][j] == " "]

    def make_move(self, row, col):
        if self.board[row][col] == " ":
            self.board[row][col] = self.current_player
            self.current_player = "O" if self.current_player == "X" else "X"
            return True
        return False

    def check_winner(self):
        lines = self.board + [list(col) for col in zip(*self.board)]  # rows and columns
        lines += [[self.board[i][i] for i in range(3)], [self.board[i][2-i] for i in range(3)]]  # diagonals
        for line in lines:
            if line == ["X"] * 3:
                return "X"
            if line == ["O"] * 3:
                return "O"
        if all(cell != " " for row in self.board for cell in row):
            return "Draw"
        return None

if __name__ == "__main__":
    # Dummy agent moves for CI/public use
    dummy_moves = [(0, 0), (1, 1), (0, 1), (1, 0), (0, 2)]

    board = TicTacToeBoard()
    winner = None

    if not is_valid_key(OPENAI_API_KEY, "sk"):
        print("API key not set or is a placeholder. Using dummy moves for CI/testing.")
        print("=== Tic Tac Toe Game ===")
        board.display()
        for move in dummy_moves:
            board.make_move(*move)
            board.display()
            winner = board.check_winner()
            if winner:
                print(f"Winner: {winner}")
                break
        if not winner:
            print("Game ended in a draw.")
    else:
        # Real agent-vs-agent play using praisonaiagents
        player_x = Agent(
            name="Player X",
            instructions="You are Player X. Choose your move as 'row col' (e.g., '1 2').",
            api_key=OPENAI_API_KEY
        )
        player_o = Agent(
            name="Player O",
            instructions="You are Player O. Choose your move as 'row col' (e.g., '1 2').",
            api_key=OPENAI_API_KEY
        )
        print("=== Tic Tac Toe Game (AI vs AI) ===")
        board.display()
        for _ in range(9):
            current_agent = player_x if board.current_player == "X" else player_o
            prompt = f"Current board:\n{board.board}\nValid moves: {board.valid_moves()}\nYour move (row col):"
            move_str = current_agent.start(prompt)
            try:
                row, col = map(int, move_str.strip().split())
            except Exception:
                print(f"Invalid move from agent: {move_str}. Skipping turn.")
                continue
            if (row, col) not in board.valid_moves():
                print(f"Illegal move: {row} {col}. Skipping turn.")
                continue
            board.make_move(row, col)
            board.display()
            winner = board.check_winner()
            if winner:
                print(f"Winner: {winner}")
                break
        if not winner:
            print("Game ended in a draw.")