import subprocess
import csv
import argparse
import sys
from ast import literal_eval
from concurrent.futures import ThreadPoolExecutor, as_completed

# ANSI escape sequences for colored output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def start_engine(engine_path):
    return subprocess.Popen(
        engine_path,
        universal_newlines=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # Redirect stderr to avoid printing it
        bufsize=1
    )

def send_command(engine, command):
    engine.stdin.write(command + '\n')

def read_response(engine):
    lines = []
    while True:
        line = engine.stdout.readline().strip()
        lines.append(line)
        if line.startswith('bestmove'):
            break
    return lines

def get_best_move(engine, fen, search_command):
    send_command(engine, "ucinewgame")
    send_command(engine, f'position fen {fen}')
    send_command(engine, search_command)
    response = read_response(engine)
    for line in response:
        if line.startswith('bestmove'):
            return line.split()[1]
    return None

def evaluate_position(engine_path, fen, expected_bestmoves, search_command, hash):
    engine = start_engine(engine_path)
    send_command(engine, "uci")
    send_command(engine, f"setoption name Hash value {hash}")

    engine_bestmove = get_best_move(engine, fen, search_command)

    send_command(engine, 'quit')
    engine.wait()

    is_correct = engine_bestmove in expected_bestmoves
    return fen, expected_bestmoves, engine_bestmove, is_correct

def format_bestmoves(bestmoves):
    if len(bestmoves) == 1:
        return bestmoves[0]
    return " or ".join(bestmoves)

def test_positions(csv_file, engine_path, search_command, hash=64, num_threads=1, num_positions=None):
    correct_count = 0
    total_count = 0

    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        positions = [
            (i + 1, row['position'], literal_eval(row['bestmove']))
            for i, row in enumerate(reader)
            if num_positions is None or i < num_positions
        ]

    total_positions = len(positions)
    incorrect = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(evaluate_position, engine_path, fen, expected_bestmoves, search_command, hash)
            for _, fen, expected_bestmoves in positions
        ]
        for future, (index, fen, expected_bestmoves) in zip(as_completed(futures), positions):
            total_count += 1
            fen, expected_bestmoves, engine_bestmove, is_correct = future.result()
            formatted_bestmoves = format_bestmoves(expected_bestmoves)
            print(f"{index}/{total_positions} FEN: {fen}")
            print(f"Expected best moves: {formatted_bestmoves}", end='')

            if is_correct:
                correct_count += 1
                correctness_msg = f"{GREEN}CORRECT{RESET}"
            else:
                correctness_msg = f"{RED}INCORRECT{RESET}, Engine found: {engine_bestmove}"
                incorrect.append((fen, engine_bestmove))

            print(f", {correctness_msg}")

    with open("incorrect.csv", mode='w', newline='', encoding='utf-8') as outfile:
        fieldnames = ['position', 'engine_move']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for fen, bestmove in incorrect:
            writer.writerow({'position': fen, 'engine_move': bestmove})

    success_percentage = (correct_count / total_count) * 100 if total_count > 0 else 0

    # Summary
    print("\nSummary of Results:")
    print(f"Test suite: {csv_file}")
    print(f"Total positions: {total_positions}")
    print(f"Correctly identified best moves: {correct_count}")
    print(f"Success rate: {success_percentage:.2f}%")

def main():
    parser = argparse.ArgumentParser(description="Test a chess engine against a set of positions.")
    parser.add_argument('--engine', help='The path to the UCI-compatible chess engine executable.')
    parser.add_argument('--depth', type=int, help='The search depth for the chess engine.')
    parser.add_argument('--nodes', type=int, help='The number of nodes for the chess engine to search.')
    parser.add_argument('--hash', default=64, type=int, help='The hash size for the chess engine.')
    parser.add_argument('--csv_file', default='king_safety.csv',
                        help='The path to the CSV file containing FEN positions and best moves.')
    parser.add_argument('--concurrency', default=4, type=int, help='The number of threads to use.')
    parser.add_argument('--num_positions', type=int, help='The number of positions to load from the CSV file.')

    args = parser.parse_args()

    if args.depth and args.nodes:
        print("Please specify either --depth or --nodes, not both.")
        sys.exit(1)

    if args.depth:
        search_command = f'go depth {args.depth}'
    elif args.nodes:
        search_command = f'go nodes {args.nodes}'
    else:
        print("Please specify either --depth or --nodes.")
        sys.exit(1)

    test_positions(args.csv_file, args.engine, search_command, args.hash, args.concurrency, args.num_positions)

if __name__ == '__main__':
    main()
